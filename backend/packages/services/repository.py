"""Persists a pipeline run to the DocStore/BlobStore and serves it to the API.

Keys (spec §M40, with the roof key fixed so a ward's roofs can be listed in rank order):

* ward_context: PK ``<city>#<ward_id>``, SK ``ctx#<version>``, GSI ``city#<city>`` by rank
* roof_context: PK ``ward#<ward_id>``, SK ``roof#<building_id>``, GSI ``ward#<ward_id>`` by rank
* config: PK ``config#<city>``, SK ``run#latest`` (run manifest, forecast, hotspots pointer)
"""

from __future__ import annotations

import json
from typing import Any

import geopandas as gpd

from packages.adapters.blobstore import BlobStore
from packages.adapters.docstore import DocStore, Index, Table
from packages.core.errors import NotFoundError
from packages.pipeline.m15_heattype import classify_wards
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
        }
        self._docs.put(
            Table.CONFIG,
            f"config#{city}",
            "run#latest",
            json.loads(json.dumps(manifest, default=str)),
        )

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
