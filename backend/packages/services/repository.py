"""Persists a pipeline run to the DocStore/BlobStore and serves it to the API.

Keys (spec §M40, with the roof key fixed so a ward's roofs can be listed in rank order):

* ward_context: PK ``<city>#<ward_id>``, SK ``ctx#<version>``, GSI ``city#<city>`` by rank
* roof_context: PK ``ward#<ward_id>``, SK ``roof#<building_id>``, GSI ``ward#<ward_id>`` by rank
* config: PK ``config#<city>``, SK ``run#latest`` (run manifest, forecast, hotspots pointer)
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import geopandas as gpd

from packages.adapters.blobstore import BlobStore
from packages.adapters.docstore import DocStore, Index, Table
from packages.core.enums import ValueClass
from packages.core.envelope import ValueEnvelope
from packages.core.errors import NotFoundError
from packages.core.timeutil import utc_now
from packages.pipeline.m15_heattype import classify_wards
from packages.pipeline.m38_tiles import build_dlst_pmtiles
from packages.pipeline.runner import PipelineRun

__all__ = ["Repository"]


def _rank_key(rank: int | None) -> str:
    return f"{rank:05d}" if rank is not None else "99999"


class Repository:
    def __init__(self, docs: DocStore, blobs: BlobStore) -> None:
        self._docs = docs
        self._blobs = blobs

    # ------------------------------------------------------------------ write
    def persist(self, run: PipelineRun, heatdome: dict[str, Any] | None = None) -> None:
        city = run.city.slug
        scores = run.require(run.priority, "M9").by_ward()
        types = {t.ward_id: t for t in classify_wards(run.contexts, run.params)}
        n = max(len(run.contexts), 1)
        for ctx in run.contexts:
            s = scores[ctx.ward_id]
            t = types[ctx.ward_id]
            doc = {
                "ward_context": ctx.to_doc(),
                "priority": {
                    "priority": s.priority,
                    "need": s.need,
                    "rank": s.rank,
                    "rank_interval": s.rank_interval,
                    "top_k_share": s.top_k_share,
                    "components": s.components,
                    "variables_used": s.variables_used,
                    "score_confidence": s.score_confidence,
                    "flags": s.flags,
                    "unscored_reason": s.unscored_reason,
                    "priority_pct": (1 - (s.rank - 1) / max(n - 1, 1)) if s.rank else None,
                },
                "heat_type": {
                    "type": t.heat_type.value,
                    "confidence": t.confidence,
                    "evidence": t.evidence,
                    "missing": list(t.missing),
                },
            }
            self._docs.put(
                Table.WARD_CONTEXT,
                f"{city}#{ctx.ward_id}",
                f"ctx#{ctx.context_version}",
                doc,
                index=Index(f"city#{city}", _rank_key(s.rank)),
            )
        ranked = {
            a.building_id: i
            for i, a in enumerate(
                sorted(run.roof_assessments, key=lambda a: (-a.benefit.base, a.building_id)), 1
            )
        }
        assess = {a.building_id: a for a in run.roof_assessments}
        for roof in run.roof_contexts:
            a = assess[roof.building_id]
            doc = {
                "roof_context": roof.to_doc(),
                "assessment": a.to_dict(),
                "benefit_rank": ranked[roof.building_id],
            }
            self._docs.put(
                Table.ROOF_CONTEXT,
                f"ward#{roof.ward_id}",
                f"roof#{roof.building_id}",
                doc,
                index=Index(f"ward#{roof.ward_id}", f"{ranked[roof.building_id]:07d}"),
            )
        wards4326 = run.require(run.wards, "M1+2").wards
        out = wards4326.merge(
            __import__("pandas").DataFrame(
                {"ward_id": list(scores), "rank": [scores[w].rank for w in scores]}
            ),
            on="ward_id",
        )
        self._blobs.put_text(
            f"curated/{city}/wards.geojson", out.to_json(), content_type="application/geo+json"
        )
        heat = run.require(run.heat, "M6")
        hs = heat.hotspots
        if len(hs):
            self._blobs.put_text(
                f"curated/{city}/hotspots.geojson",
                gpd.GeoDataFrame(hs, crs=hs.crs).to_crs(4326).to_json(),
                content_type="application/geo+json",
            )
        manifest = {
            "city": city,
            "run_id": run.run_id,
            "context_version": run.context_version,
            "steps": run.steps,
            "reference": heat.reference.method,
            "scenes": [
                {
                    "id": s.scene_id,
                    "date": s.acquired.isoformat(),
                    "valid_pixel_pct": s.valid_pixel_pct,
                }
                for s in run.require(run.stack, "M3+4").scenes
            ],
            "sensitivity": run.priority.sensitivity,  # type: ignore[union-attr]
            "normalisation": run.priority.normalisation,  # type: ignore[union-attr]
            "forecast": heatdome,
            "grid_pixel_area_m2": run.require(run.grid, "M1+2").pixel_area_m2,
            "layers": self._persist_layers(run),
            "model_card": run.drivers.model_card if run.drivers else None,
            "fire_as_of": run.fire_as_of.isoformat() if run.fire_as_of else None,
        }
        self._docs.put(
            Table.CONFIG,
            f"config#{city}",
            "run#latest",
            json.loads(json.dumps(manifest, default=str)),
        )
        self._persist_environment(run)
        if heatdome:
            self.store_forecast(city, heatdome)

    # ------------------------------------------------------------------ extras (M16, M22-M24)
    def _persist_layers(self, run: PipelineRun) -> dict[str, Any]:
        """Map layers served as blobs: ΔLST PMTiles, facilities, protected areas."""
        city = run.city.slug
        layers: dict[str, Any] = {}
        heat = run.require(run.heat, "M6")
        tiles = build_dlst_pmtiles(run.require(run.grid, "M1+2"), heat.dlst_c)
        self._blobs.put(
            f"curated/{city}/dlst.pmtiles", tiles.data, content_type="application/octet-stream"
        )
        layers["dlst"] = {
            "key": f"curated/{city}/dlst.pmtiles",
            "vmin": round(tiles.vmin, 2),
            "vmax": round(tiles.vmax, 2),
            "min_zoom": tiles.min_zoom,
            "max_zoom": tiles.max_zoom,
            "bounds": [round(v, 5) for v in tiles.bounds_lonlat],
        }
        for name, gdf in (
            ("facilities", run.inputs.facilities),
            ("protected_areas", run.inputs.protected_areas),
        ):
            if gdf is not None:
                self._blobs.put_text(
                    f"curated/{city}/{name}.geojson",
                    gdf.to_json(),
                    content_type="application/geo+json",
                )
                layers[name] = {"key": f"curated/{city}/{name}.geojson"}
        return layers

    def _persist_environment(self, run: PipelineRun) -> None:
        city = run.city.slug
        if run.drivers is not None:
            for wid, wd in run.drivers.wards.items():
                self._docs.put(
                    Table.ENVIRONMENT,
                    f"drivers#{city}",
                    wid,
                    {
                        "ward_id": wid,
                        "status": wd.status,
                        "drivers": wd.drivers,
                        "unobserved": run.drivers.model_card["unobserved"],
                        "model_card": run.drivers.model_card,
                        "wording": "associated with — correlational, not causal",
                    },
                )
        for uid, trend in run.trends.items():
            self._docs.put(Table.ENVIRONMENT, f"soil#{city}", uid, trend.to_dict())
        for pa in run.habitat:
            self._docs.put(Table.ENVIRONMENT, f"habitat#{city}", pa.pa_id, pa.to_dict())
        for ev in run.fire_events:
            self._docs.put(
                Table.ENVIRONMENT,
                f"fire#{city}",
                f"{ev.acq_date}#{ev.acq_time}#{ev.event_id}",
                ev.to_dict(),
            )

    def drivers(self, city: str, ward_id: str) -> dict[str, Any]:
        doc = self._docs.get(Table.ENVIRONMENT, f"drivers#{city}", ward_id)
        if doc is None:
            raise NotFoundError(f"no driver attribution for ward '{ward_id}'")
        return doc

    def soil(self, city: str, unit_id: str) -> dict[str, Any]:
        doc = self._docs.get(Table.ENVIRONMENT, f"soil#{city}", unit_id)
        if doc is None:
            raise NotFoundError(f"no trend series for '{unit_id}'")
        return doc

    def protected_areas(self, city: str) -> list[dict[str, Any]]:
        return self._docs.query(Table.ENVIRONMENT, f"habitat#{city}")

    def fire_events(self, city: str, since: str | None = None) -> list[dict[str, Any]]:
        rows = self._docs.query(Table.ENVIRONMENT, f"fire#{city}", sk_gte=since)
        return rows

    # ------------------------------------------------------------------ M43 forecast
    def store_forecast(self, city: str, forecast: dict[str, Any]) -> None:
        """Keep the forecast history and patch ``heat.heatdome_*`` on every latest ward context."""
        issued = forecast.get("issued_at") or utc_now().isoformat()
        self._docs.put(Table.FORECASTS, f"city#{city}", str(issued), forecast)
        manifest = self._docs.get(Table.CONFIG, f"config#{city}", "run#latest")
        if manifest is not None:
            self._docs.update_paths(
                Table.CONFIG, f"config#{city}", "run#latest", {"forecast": forecast}
            )
        risk = forecast.get("risk", "unavailable")
        processed = utc_now().date()
        for doc in self._docs.query_index(Table.WARD_CONTEXT, f"city#{city}"):
            ctx = doc["ward_context"]
            sk = f"ctx#{ctx['context_version']}"
            if risk == "unavailable":
                risk_env = ValueEnvelope.unavailable("m43_heatdome", "forecast source unavailable")
                ref_env = None
            else:
                risk_env = ValueEnvelope.of(
                    risk,
                    ValueClass.DERIVED,
                    "m43_heatdome; forecast signal, not an official warning",
                    observed=str(issued)[:10],
                    processed=processed.isoformat(),
                    stale_after=(processed + timedelta(days=2)).isoformat(),
                    confidence=0.5 if forecast.get("low_confidence") else 0.7,
                )
                ref_env = ValueEnvelope.of(
                    str(issued), ValueClass.DERIVED, "m43_heatdome forecast issued_at"
                )
            updates = {"ward_context.heat.heatdome_risk": risk_env.to_json_dict()}
            if ref_env is not None:
                updates["ward_context.heat.heatdome_ref"] = ref_env.to_json_dict()
            self._docs.update_paths(Table.WARD_CONTEXT, f"{city}#{ctx['ward_id']}", sk, updates)

    def forecast_history(self, city: str, limit: int = 30) -> list[dict[str, Any]]:
        return self._docs.query(Table.FORECASTS, f"city#{city}", descending=True, limit=limit)

    # ------------------------------------------------------------------ read
    def manifest(self, city: str) -> dict[str, Any]:
        doc = self._docs.get(Table.CONFIG, f"config#{city}", "run#latest")
        if doc is None:
            raise NotFoundError(f"no analysis has been run for '{city}'; run the pipeline first")
        return doc

    def wards(self, city: str) -> list[dict[str, Any]]:
        rows = self._docs.query_index(Table.WARD_CONTEXT, f"city#{city}")
        if not rows:
            raise NotFoundError(f"no analysis has been run for '{city}'")
        return rows

    def ward(self, city: str, ward_id: str) -> dict[str, Any]:
        doc = self._docs.latest(Table.WARD_CONTEXT, f"{city}#{ward_id}", sk_prefix="ctx#")
        if doc is None:
            raise NotFoundError(f"ward '{ward_id}' not found")
        return doc

    def roofs(self, ward_id: str, top: int | None = None) -> list[dict[str, Any]]:
        return self._docs.query_index(Table.ROOF_CONTEXT, f"ward#{ward_id}", limit=top)

    def roof(self, ward_id: str, building_id: str) -> dict[str, Any]:
        doc = self._docs.get(Table.ROOF_CONTEXT, f"ward#{ward_id}", f"roof#{building_id}")
        if doc is None:
            raise NotFoundError(f"building '{building_id}' not found")
        return doc

    def blob_json(self, key: str) -> dict[str, Any]:
        return json.loads(self._blobs.get_text(key))  # type: ignore[no-any-return]
