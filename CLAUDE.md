# Access Accounting: Empirical Validation Pipeline

## Project Purpose
This project empirically validates the Access Accounting framework proposed for TAIGR @ ICML 2026. It computes Effective Compute Access (ECA) scores across countries, cloud providers, and GPU classes using strictly public data, producing the tables, figures, and sensitivity analyses needed to demonstrate the framework's feasibility and policy relevance.

The end product is:
1. **Reproducible ECA tables** (like Table 2 in the paper, but expanded)
2. **Sensitivity analysis** across affordability normalization methods
3. **Visualizations** showing compounding access gaps
4. **A reference implementation** released alongside the paper

## Architecture

```
access-accounting/
├── CLAUDE.md                  # This file — project overview
├── README.md                  # Public-facing repo README
├── requirements.txt           # Python dependencies
├── data/
│   ├── README.md              # Data sourcing documentation
│   ├── countries.yaml         # Country configs (PPP, BIS tier, etc.)
│   ├── providers.yaml         # Cloud provider pricing by region
│   └── gpus.yaml              # GPU specs (FLOP/s, form factor)
├── src/
│   ├── __init__.py
│   ├── aar.py                 # Access Availability Record builder
│   ├── eca.py                 # Effective Compute Access computation
│   ├── sensitivity.py         # Sensitivity analysis across normalizations
│   └── visualize.py           # Chart generation
├── notebooks/
│   └── pilot_analysis.ipynb   # Interactive walkthrough of full pilot
├── outputs/
│   ├── tables/                # Generated LaTeX/CSV tables
│   └── figures/               # Generated plots
└── tests/
    └── test_eca.py            # Unit tests for ECA math
```

## Key Concepts

### Access Availability Record (AAR)
A structured record for one (country, provider, GPU) tuple with fields across three layers:
- **Physical**: GPU availability class (GA/Limited/Waitlisted/Unavailable)
- **Economic**: On-demand price, PPP-adjusted cost, runs-per-budget
- **Legal**: BIS tier, TPP cap, legal scenario (A/B/C)

### Effective Compute Access (ECA)
Composite metric:
```
ECA(country, budget) = min(ECA_Phys, ECA_E) × δ(legal_scenario)
```
Where:
- `ECA_Phys` = availability class score (GA=1.0, Limited=0.5, Waitlisted=0.1, Unavailable=0.0)
- `ECA_E = floor(budget / (price_per_gpu_hr × H × PPP_factor)) × peak_FLOP_s`
- `δ` = legal scenario multiplier (A=1.0, B=parameterized, C=0.0)
- `H` = reference run duration in hours (default: 720)

### Three Legal Scenarios
- **Scenario A (Unconstrained)**: δ = 1.0 — no legal cap binding
- **Scenario B (Partially constrained)**: δ ∈ (0, 1) — cap exists, consumption unknown
- **Scenario C (Prohibited/consumed)**: δ → 0

## Data Sources (All Public)

| Data                | Source                                          | How to Obtain                              |
|---------------------|-------------------------------------------------|--------------------------------------------|
| GPU pricing         | AWS EC2 Capacity Blocks, GCP, Azure public pages| Manual collection from pricing pages       |
| PPP factors         | World Bank ICP 2024                             | World Bank API or CSV download             |
| GDP per capita      | World Bank WDI                                  | World Bank API                             |
| R&D spend per researcher | UNESCO UIS                                 | UNESCO data portal                         |
| GPU specs (FLOP/s)  | NVIDIA datasheets                               | Public product pages                       |
| BIS export tiers    | Federal Register 90 FR 4544                     | BIS regulatory text                        |
| GPU region availability | Provider region-product matrices             | AWS/GCP/Azure public docs                  |

**Critical rule**: No proprietary data. Every input must have a public URL citation.

## Execution Steps

### Step 1: Populate data files
Fill `data/countries.yaml`, `data/providers.yaml`, and `data/gpus.yaml` with real public data. See `data/README.md` for exact sourcing instructions and required fields.

### Step 2: Run the AAR builder
```bash
python -m src.aar --config data/ --output outputs/tables/aar_records.csv
```
Generates one AAR-Core record per (country, provider, GPU) tuple.

### Step 3: Run ECA computation
```bash
python -m src.eca --aar outputs/tables/aar_records.csv --budget 10000 --hours 720 --output outputs/tables/eca_results.csv
```
Computes ECA under all three legal scenarios for each record.

### Step 4: Run sensitivity analysis
```bash
python -m src.sensitivity --aar outputs/tables/aar_records.csv --budget 10000 --output outputs/tables/sensitivity.csv
```
Reruns ECA with three normalization methods: PPP, GDP-per-capita, R&D-spend-per-researcher.

### Step 5: Generate figures
```bash
python -m src.visualize --results outputs/tables/ --output outputs/figures/
```
Produces:
- `compounding_gap.png` — bar chart showing how gaps widen layer by layer
- `sensitivity_heatmap.png` — heatmap of ECA ranks across normalization methods
- `provider_comparison.png` — cross-provider ECA for same country

### Step 6: Generate LaTeX tables
```bash
python -m src.aar --config data/ --output outputs/tables/table2_expanded.tex --format latex
```

## What "Empirical Proof" Means Here

This is NOT a machine learning experiment. There is no train/test split, no model accuracy, no statistical inference. The empirical contribution is:

1. **Feasibility proof**: The framework can be populated entirely from public data
2. **Robustness check**: Access gap rankings are stable across normalization methods
3. **Compounding demonstration**: Layer-by-layer decomposition shows multiplicative gaps
4. **Reproducibility**: Anyone can re-run with updated pricing/PPP data

The strength of the evidence comes from:
- Coverage (many countries × providers × GPUs)
- Transparency (every input has a URL)
- Robustness (sensitivity analysis across methods)
- NOT from p-values or statistical tests

## Style and Code Conventions

- Python 3.10+
- Type hints on all functions
- Docstrings with parameter descriptions
- YAML for config (not JSON — more readable for policy researchers)
- All monetary values in USD unless explicitly noted
- All FLOP/s values dense BF16, SXM form factor, no sparsity
- ISO 3166-1 alpha-3 country codes
- ISO 8601 dates
