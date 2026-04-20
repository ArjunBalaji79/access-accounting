"""End-to-end integration tests: YAML → AAR → ECA → output files."""

import csv
from collections import defaultdict
from pathlib import Path

import pytest

from src.aar import build_aar_records, records_to_csv
from src.eca import (
    compute_eca,
    compute_eca_budget_sweep,
    load_aar_csv,
    results_to_csv,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def aar_csv_path(tmp_path_factory) -> Path:
    """Build AAR once per test module and write it to a shared tmp CSV."""
    records = build_aar_records(
        DATA_DIR / "countries.yaml",
        DATA_DIR / "providers.yaml",
        DATA_DIR / "gpus.yaml",
    )
    out = tmp_path_factory.mktemp("aar") / "aar.csv"
    records_to_csv(records, out)
    return out


class TestFullPipeline:

    def test_pipeline_runs_without_error(self, tmp_path, aar_csv_path):
        aar_data = load_aar_csv(aar_csv_path)
        eca_results = compute_eca(aar_data, budget_usd=10_000, reference_hours=720)
        eca_out = tmp_path / "eca.csv"
        results_to_csv(eca_results, eca_out)
        assert eca_out.exists()

        with open(eca_out) as f:
            rows = list(csv.DictReader(f))
        assert rows, "ECA CSV should not be empty"
        required_cols = {
            "eca_scenario_a",
            "eca_continuous_scenario_a",
            "eca_nominal_tflops",
            "alpha_availability",
        }
        assert required_cols.issubset(rows[0].keys())

    def test_usa_always_ranks_first(self, aar_csv_path):
        aar_data = load_aar_csv(aar_csv_path)
        results = compute_eca(aar_data, budget_usd=10_000, reference_hours=720)

        groups = defaultdict(list)
        for r in results:
            groups[(r.provider, r.gpu_class)].append(r)

        for key, group in groups.items():
            first = sorted(group, key=lambda x: -x.eca_scenario_a)[0]
            assert first.country_iso == "USA", (
                f"USA not first for {key}: first is {first.country_iso}"
            )

    def test_tier3_always_zero(self, aar_csv_path):
        aar_data = load_aar_csv(aar_csv_path)
        results = compute_eca(aar_data, budget_usd=10_000, reference_hours=720)
        tier3 = [r for r in results if r.bis_tier == 3]
        assert tier3
        for r in tier3:
            assert r.eca_scenario_a == 0.0
            assert r.eca_scenario_b_mid == 0.0
            assert r.eca_scenario_c == 0.0
            assert r.eca_continuous_scenario_a == 0.0

    def test_budget_sweep_end_to_end(self, tmp_path, aar_csv_path):
        aar_data = load_aar_csv(aar_csv_path)
        sweep = compute_eca_budget_sweep(
            aar_data, budgets=[5_000, 25_000, 100_000],
        )
        out = tmp_path / "sweep.csv"
        results_to_csv(sweep, out)
        assert out.exists()
        # 3 budgets × per-record count.
        assert len(sweep) == 3 * len(aar_data)

    def test_continuous_matches_scenario_a_for_usa_ga(self, aar_csv_path):
        """For a country where floor(runs) ≈ runs, discrete and continuous
        should be close. USA with H100 at $10K: runs ≈ 3.53 → chips = 3.
        Continuous ECA ≈ 3.53 × 989.5 ≈ 3492; discrete ≈ 3 × 989.5 = 2968.5.
        Check continuous ≥ discrete always (floor never exceeds raw runs)."""
        aar_data = load_aar_csv(aar_csv_path)
        results = compute_eca(aar_data, budget_usd=10_000, reference_hours=720)
        for r in results:
            assert r.eca_continuous_scenario_a >= r.eca_scenario_a - 0.5  # rounding tolerance
