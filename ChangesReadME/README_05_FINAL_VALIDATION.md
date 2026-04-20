# README_05: Final Validation, Tests & Pre-Submission Checklist

## Priority: MEDIUM
## What this does: Adds comprehensive tests, end-to-end validation, and a pre-submission check
## Depends on: All previous READMEs

---

## Part A: Expand Test Suite

### Current test coverage:
- 9 tests, all in `tests/test_eca.py`
- No tests for `aar.py`, `sensitivity.py`, or `visualize.py`
- No integration tests (full pipeline from YAML → AAR → ECA → figures)

### New test file: `tests/test_aar.py`

```python
"""Tests for AAR record building."""

import pytest
from pathlib import Path
from src.aar import build_aar_records, AARCoreRecord, AVAILABILITY_SCORES

class TestAARBuilder:

    def test_builds_correct_record_count(self):
        """Should produce countries × provider-GPU combos records (minus China no-region cases)."""
        records = build_aar_records(
            Path("data/countries.yaml"),
            Path("data/providers.yaml"),
            Path("data/gpus.yaml"),
        )
        # 10 countries × 4 provider-GPU combos (2 providers × 2 GPUs) = 40
        # Minus any that have no region match
        assert len(records) >= 30  # Conservative lower bound
        assert len(records) <= 50

    def test_tier3_override_to_unavailable(self):
        """Tier 3 countries should have availability overridden to Unavailable."""
        records = build_aar_records(
            Path("data/countries.yaml"),
            Path("data/providers.yaml"),
            Path("data/gpus.yaml"),
        )
        china_records = [r for r in records if r.country_iso == "CHN"]
        for r in china_records:
            assert r.availability_class == "Unavailable"
            assert r.availability_score == 0.0

    def test_all_records_have_required_fields(self):
        """Every record should have non-null values for critical fields."""
        records = build_aar_records(
            Path("data/countries.yaml"),
            Path("data/providers.yaml"),
            Path("data/gpus.yaml"),
        )
        for r in records:
            assert r.country_name
            assert r.country_iso
            assert r.provider
            assert r.gpu_class
            assert r.peak_tflops_bf16_dense > 0
            assert r.on_demand_usd_per_gpu_hr > 0
            assert r.ppp_factor > 0
            assert r.bis_tier in (1, 2, 3)

    def test_availability_scores_match_classes(self):
        """Availability score should match the class mapping."""
        records = build_aar_records(
            Path("data/countries.yaml"),
            Path("data/providers.yaml"),
            Path("data/gpus.yaml"),
        )
        for r in records:
            expected = AVAILABILITY_SCORES.get(r.availability_class, 0.0)
            assert r.availability_score == expected, (
                f"{r.country_iso}/{r.provider}/{r.gpu_class}: "
                f"class={r.availability_class} but score={r.availability_score}"
            )

    def test_nigeria_not_local(self):
        """Nigeria should route to a non-local region."""
        records = build_aar_records(
            Path("data/countries.yaml"),
            Path("data/providers.yaml"),
            Path("data/gpus.yaml"),
        )
        nga = [r for r in records if r.country_iso == "NGA"]
        assert len(nga) > 0
        for r in nga:
            assert r.is_local_region == False

    def test_usa_always_local(self):
        """USA should always have a local region."""
        records = build_aar_records(
            Path("data/countries.yaml"),
            Path("data/providers.yaml"),
            Path("data/gpus.yaml"),
        )
        usa = [r for r in records if r.country_iso == "USA"]
        for r in usa:
            assert r.is_local_region == True
```

### New test file: `tests/test_integration.py`

```python
"""End-to-end integration tests: YAML → AAR → ECA → output files."""

import pytest
from pathlib import Path
import csv

from src.aar import build_aar_records, records_to_csv
from src.eca import load_aar_csv, compute_eca, results_to_csv


class TestFullPipeline:

    def test_full_pipeline_runs_without_error(self, tmp_path):
        """The complete AAR → ECA pipeline should run without exceptions."""
        # Step 1: Build AAR
        records = build_aar_records(
            Path("data/countries.yaml"),
            Path("data/providers.yaml"),
            Path("data/gpus.yaml"),
        )
        aar_path = tmp_path / "aar.csv"
        records_to_csv(records, aar_path)
        assert aar_path.exists()

        # Step 2: Compute ECA
        aar_data = load_aar_csv(aar_path)
        eca_results = compute_eca(aar_data, budget_usd=10_000, reference_hours=720)
        eca_path = tmp_path / "eca.csv"
        results_to_csv(eca_results, eca_path)
        assert eca_path.exists()

        # Step 3: Verify output structure
        with open(eca_path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) > 0
        assert "eca_scenario_a" in rows[0]
        assert "eca_continuous_scenario_a" in rows[0]

    def test_usa_always_ranks_first(self):
        """USA should have the highest ECA for any provider+GPU combo."""
        records = build_aar_records(
            Path("data/countries.yaml"),
            Path("data/providers.yaml"),
            Path("data/gpus.yaml"),
        )
        aar_path = Path("/tmp/test_aar.csv")
        records_to_csv(records, aar_path)
        aar_data = load_aar_csv(aar_path)
        results = compute_eca(aar_data, budget_usd=10_000, reference_hours=720)

        # Group by provider+GPU
        from collections import defaultdict
        groups = defaultdict(list)
        for r in results:
            groups[(r.provider, r.gpu_class)].append(r)

        for key, group in groups.items():
            sorted_group = sorted(group, key=lambda x: -x.eca_scenario_a)
            assert sorted_group[0].country_iso == "USA", (
                f"USA not first for {key}: first is {sorted_group[0].country_iso}"
            )

    def test_tier3_always_zero(self):
        """Tier 3 countries should have ECA=0 under ALL scenarios."""
        records = build_aar_records(
            Path("data/countries.yaml"),
            Path("data/providers.yaml"),
            Path("data/gpus.yaml"),
        )
        aar_path = Path("/tmp/test_aar.csv")
        records_to_csv(records, aar_path)
        aar_data = load_aar_csv(aar_path)
        results = compute_eca(aar_data)

        tier3 = [r for r in results if r.bis_tier == 3]
        assert len(tier3) > 0
        for r in tier3:
            assert r.eca_scenario_a == 0.0
            assert r.eca_scenario_b_mid == 0.0
            assert r.eca_scenario_c == 0.0
```

---

## Part B: Pre-Submission Validation Script

Create `src/validate_submission.py` — a final check that everything is consistent before you submit:

```bash
python -m src.validate_submission --config data/ --outputs outputs/
```

### What it checks:

1. **Data freshness**: All `pricing_retrieval_date` values in providers.yaml are within 90 days
2. **Data verification**: `data_verified_date` in countries.yaml is within 90 days
3. **Output completeness**: All expected files exist in outputs/
4. **Cross-consistency**: GPU names in providers.yaml match gpus.yaml
5. **Country coverage**: At least 3 countries per BIS tier
6. **FLOP/s convention**: Confirms gpus.yaml uses dense BF16 non-sparse values
7. **No placeholder data**: Checks that no YAML comments contain "illustrative" or "verify" (these should be resolved by now)
8. **Test suite passes**: Runs pytest and reports results
9. **Figures generated**: All 6 expected PNG files exist and are non-empty

### Output format:

```
=== PRE-SUBMISSION VALIDATION ===

[PASS] Data freshness: All pricing within 90 days
[PASS] Data verification: All countries verified within 90 days
[PASS] Output completeness: All 6 figures + 3 tables exist
[PASS] Cross-consistency: All GPU classes in providers.yaml exist in gpus.yaml
[PASS] Country coverage: 4 Tier 1, 5 Tier 2, 1 Tier 3
[PASS] FLOP/s convention: All values are dense BF16 non-sparse
[WARN] Placeholder language: data/countries.yaml line 8 contains "illustrative"
[PASS] Test suite: 22/22 tests passed
[PASS] Figures generated: 6/6 files exist

RESULT: 8 passed, 1 warning, 0 failures
```

---

## Part C: Updated README.md (Project Root)

After all changes, update the project's public-facing README.md to reflect the full pipeline:

```markdown
## Quick Start

### 1. Verify data against live sources
python -m src.verify_data --config data/ --output outputs/verification_report.json

### 2. Build AAR records
python -m src.aar --config data/ --output outputs/tables/aar_records.csv

### 3. Compute ECA (single budget)
python -m src.eca --aar outputs/tables/aar_records.csv --budget 10000 --hours 720

### 4. Compute ECA (budget sweep)
python -m src.eca --aar outputs/tables/aar_records.csv --budgets 5000,10000,25000,50000 --hours 720

### 5. Run sensitivity analysis
python -m src.sensitivity --aar outputs/tables/aar_records.csv

### 6. Generate figures
python -m src.visualize --results outputs/tables/ --output outputs/figures/

### 7. Run all tests
pytest tests/ -v

### 8. Pre-submission validation
python -m src.validate_submission --config data/ --outputs outputs/
```

---

## Part D: Final File Manifest

After all READMEs are implemented, the project should contain:

```
access-accounting/
├── CLAUDE.md                          # Updated project spec
├── README.md                          # Updated public README
├── requirements.txt                   # Added: requests, beautifulsoup4
├── data/
│   ├── README.md                      # Existing (no change)
│   ├── countries.yaml                 # UPDATED: verified values, data_verified_date
│   ├── providers.yaml                 # UPDATED: verified pricing, pricing_type, fixed regions
│   └── gpus.yaml                      # UPDATED: clarifying comments on dense vs sparse
├── src/
│   ├── __init__.py
│   ├── aar.py                         # UPDATED: is_local_region, routing fields
│   ├── eca.py                         # UPDATED: formula clarity, continuous metric, budget sweep
│   ├── sensitivity.py                 # MINOR: budget sweep integration
│   ├── verify_data.py                 # NEW: verification agent
│   ├── validate_submission.py         # NEW: pre-submission checklist
│   └── visualize.py                   # UPDATED: 6 chart types
├── tests/
│   ├── test_eca.py                    # UPDATED: new tests for continuous, sweep
│   ├── test_aar.py                    # NEW: AAR builder tests
│   └── test_integration.py            # NEW: end-to-end pipeline tests
├── outputs/
│   ├── tables/
│   │   ├── aar_records.csv            # Regenerated
│   │   ├── eca_results.csv            # Regenerated
│   │   ├── eca_budget_sweep.csv       # NEW
│   │   └── sensitivity.csv            # Regenerated
│   ├── figures/
│   │   ├── compounding_gap_h100_sxm5.png   # UPDATED
│   │   ├── compounding_gap_a100_sxm4.png   # NEW
│   │   ├── budget_sweep.png                # NEW
│   │   ├── continuous_vs_discrete.png      # NEW
│   │   ├── sensitivity_heatmap.png         # UPDATED
│   │   └── provider_comparison.png         # UPDATED
│   └── verification_report.json       # NEW
└── change-plan/                       # These READMEs (can delete after implementation)
    ├── README_00_MASTER.md
    ├── README_01_DATA_VERIFICATION.md
    ├── README_02_FORMULA_FIX.md
    ├── README_03_VISUALIZATION.md
    ├── README_04_AAR_ENHANCEMENTS.md
    └── README_05_FINAL_VALIDATION.md
```
