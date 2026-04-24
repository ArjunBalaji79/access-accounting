# Access Accounting

**A Framework for Measuring and Reporting AI Compute Availability for Governance**



---

## Overview

Policymakers use compute as a governance lever — through export controls, public compute programs, and international frameworks — but no standardized methodology exists for measuring **who can actually access what compute**. This project provides:

1. **Access Availability Record (AAR)** — a structured reporting schema for compute access across physical, economic, and legal dimensions
2. **Effective Compute Access (ECA)** — a composite metric revealing how access gaps compound across layers
3. **A reference implementation** computing AAR and ECA from public data

## Quick Start

```bash
pip install -r requirements.txt

# Step 1: Verify inputs against live sources
#   - Fetches World Bank PPP/GDP indicators
#   - Spot-checks AWS/GCP pricing
#   - Writes outputs/verification_report.json
python -m src.verify_data --config data/ --output outputs/verification_report.json

# Step 2: Build AAR-Core records (adds is_local_region / routing notes)
python -m src.aar --config data/ --output outputs/tables/aar_records.csv

# Step 3: Compute ECA at a single budget
python -m src.eca --aar outputs/tables/aar_records.csv --budget 10000 --hours 720

# Step 4: Compute ECA across a budget sweep (for the budget_sweep figure)
python -m src.eca --aar outputs/tables/aar_records.csv \
    --budgets 5000,10000,25000,50000,100000 --hours 720

# Step 5: Sensitivity analysis across PPP / GDP / R&D normalizations
python -m src.sensitivity --aar outputs/tables/aar_records.csv

# Step 6: Generate all six figures
python -m src.visualize --results outputs/tables/ --output outputs/figures/

# Step 7: Run the full test suite (AAR + ECA + integration)
pytest tests/ -v

# Step 8: Pre-submission checklist (freshness, completeness, conventions)
python -m src.validate_submission --config data/ --outputs outputs/
```

## Methodology Notes

The ECA formula implemented here is:

```
ECA(c, b) = ECA_E(c, b) × α(availability) × δ(legal_scenario)
```

- `ECA_E = floor(budget / (price × H / norm)) × peak_TFLOP/s` (discrete form)
- `α ∈ {1.0, 0.5, 0.1, 0.0}` for {GA, Limited, Waitlisted, Unavailable}
- `δ` is 1.0 for Scenario A, {0.3, 0.5, 0.7} for Scenario B low/mid/high,
  and 0.0 for Scenario C (prohibited)

Each ECA row additionally reports:

- `eca_continuous_scenario_*` — the same formula without `floor()`, exposing
  the PPP gradient that the discrete metric plateaus.
- `eca_nominal_tflops` — the pre-PPP/α/δ baseline used by the 4-bar
  compounding-gap chart.

GPU FLOP/s throughout the pipeline use **dense BF16, SXM, no sparsity**
(H100 = 989.5 TFLOP/s; A100 = 312 TFLOP/s). See `data/gpus.yaml` for the
NVIDIA datasheet footnote that distinguishes dense vs. sparse rows.

### Data Sovereignty (descriptive)

Each AAR-Core record also reports a `data_sovereignty_class` drawn from
publicly-available statutory text (e.g. GDPR Art. 46-49, UK GDPR,
Japan APPI Art. 28, India DPDP Act 2023 Sec. 16, China PIPL Art. 38-40).
Values: `none`, `cross_border_restricted`, `localization_required`,
`transfer_prohibited`.

This field is **intentionally excluded from the ECA score**: whether a
data-transfer regime binds depends on the workload's data type (public
text vs. personal/government/critical-infrastructure data), which sits
outside the AAR-Core schema. The field surfaces an access dimension
that export controls alone do not capture — a Tier 1 country with no
chip restriction may still face binding transfer restrictions on
sensitive workloads — and the 4-bar compounding-gap charts mark
countries with `†` where non-local routing compounds with a
cross-border transfer regime.

## Data Sources

All inputs are publicly verifiable. See `data/README.md` for exact sourcing instructions.

| Data | Source |
|------|--------|
| GPU pricing | AWS/GCP/Azure public pricing pages |
| PPP factors | World Bank ICP 2024 |
| GPU specs | NVIDIA official datasheets |
| BIS export tiers | Federal Register 90 FR 4544 |

