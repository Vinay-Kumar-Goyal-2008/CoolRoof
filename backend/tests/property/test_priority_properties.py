"""Property tests: M9 monotonicity (raising exposure never lowers priority)."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from packages.core.context import DataQuality, LocationSection, WardContext
from packages.core.enums import UnitType, ValueClass
from packages.core.envelope import ValueEnvelope
from packages.core.params import load_params
from packages.pipeline.m09_priority import score_wards

# The property does not depend on the sensitivity analysis, so keep it cheap.
PARAMS = load_params().with_overrides(
    {"P-W-DIRICHLET": {"draws": 20, "concentration": 10.0, "seed": 1}}
)


def _ctx(ward: str, values: tuple[float, float, float, float, float]) -> WardContext:
    dlst, pers, exposed, ndvi, roof = values

    def env(v: float) -> ValueEnvelope:
        return ValueEnvelope.of(v, ValueClass.DERIVED, "prop")

    return WardContext(
        ward_id=ward,
        boundary_version="p",
        context_version="v",
        run_id="r",
        location=LocationSection(
            city="p",
            state="P",
            centroid=(0, 0),
            area_km2=1.0,
            unit_type=UnitType.WARD,
            name=ward,
            name_hi=ward,
        ),
        heat={"mean_dlst_c": env(dlst), "persistence": env(pers)},
        population={"exposed_population": env(exposed)},
        environment={"ndvi_mean": env(ndvi)},
        built_environment={"eligible_roof_area_m2": env(roof)},
        data_quality=DataQuality(context_confidence=1.0),
    )


ward_values = st.tuples(
    st.floats(-5, 8),
    st.floats(0, 1),
    st.floats(0, 50_000),
    st.floats(0, 0.8),
    st.floats(0, 500_000),
)


@settings(max_examples=60, deadline=None)
@given(st.lists(ward_values, min_size=3, max_size=8), st.floats(1, 50_000))
def test_raising_exposure_never_lowers_priority(rows: list, bump: float) -> None:  # type: ignore[type-arg]
    contexts = [_ctx(f"W{i}", v) for i, v in enumerate(rows)]
    before = score_wards(contexts, PARAMS).by_ward()["W0"].priority
    bumped = list(rows)
    d, p, e, n, r = bumped[0]
    bumped[0] = (d, p, e + bump, n, r)
    after = score_wards([_ctx(f"W{i}", v) for i, v in enumerate(bumped)], PARAMS).by_ward()
    assert before is not None and after["W0"].priority is not None
    assert after["W0"].priority >= before - 1e-9
