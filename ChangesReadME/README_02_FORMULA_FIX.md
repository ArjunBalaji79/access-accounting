# README_02: ECA Formula Alignment & Continuous Metric

## Priority: CRITICAL
## What this does: Fixes the ECA formula to match the paper's intended design, adds a continuous metric
## Depends on: README_01 (verified data)

---

## Problem 1: Formula Mismatch Between Paper and Code

### Current state in the code (eca.py line 179):
```python
eca_base = eca_e * eca_phys  # multiplication
```

### Current state in the paper:
```
ECA = min(ECA_Phys, ECA_E) × δ
```

### Why `min()` is wrong:
- `ECA_Phys` is a dimensionless 0-1 score (GA=1.0, Limited=0.5, etc.)
- `ECA_E` is in TFLOP/s (e.g., 2968.5)
- `min(1.0, 2968.5)` = 1.0 always — the physical score would dominate and the economic dimension would be lost
- The `min()` was probably an error in the paper draft

### Why multiplication is correct:
- `ECA_E × α × δ` = TFLOP/s × availability_fraction × legal_fraction
- Units: TFLOP/s × dimensionless × dimensionless = TFLOP/s ✓
- Semantics: "Your accessible compute, scaled down by availability constraints and legal constraints"
- This is what the code already does

### Changes to make in `src/eca.py`:

**1. Rename variables for clarity** (make the code match the paper's intended notation):

In the `compute_eca()` function, rename:
```python
# OLD (confusing):
eca_phys = avail_score
eca_base = eca_e * eca_phys

# NEW (clear):
alpha = avail_score  # availability modifier α ∈ {1.0, 0.5, 0.1, 0.0}
eca_base = eca_e * alpha  # ECA_E × α
```

**2. Update the module docstring** at the top of eca.py:

```python
"""
Effective Compute Access (ECA) computation.

ECA formula:
    ECA(c, b) = ECA_E(c, b) × α(availability) × δ(legal_scenario)

Where:
    ECA_E = floor(budget / (price × H / norm)) × peak_TFLOP/s
    α = availability modifier (GA=1.0, Limited=0.5, Waitlisted=0.1, Unavailable=0.0)
    δ = legal scenario multiplier (Scenario A=1.0, B=parameterized, C=0.0)
"""
```

**3. Update the `ECAResult` dataclass** — rename `availability_score` to `alpha_availability` for paper alignment:

```python
# In ECAResult dataclass:
alpha_availability: float  # was: availability_score
```

Update all references throughout the file.

---

## Problem 2: Floor Division Creates Misleading Plateaus

### Current state:
At $10K budget, H100 pricing:
- Germany (PPP 0.78): runs = 10000 / (3.933 × 720 / 0.78) = 2.75 → floor = 2 chips
- Japan (PPP 0.69): runs = 10000 / (3.933 × 720 / 0.69) = 2.44 → floor = 2 chips
- UK (PPP 0.79): runs = 10000 / (3.933 × 720 / 0.79) = 2.79 → floor = 2 chips

All three get ECA = 2 × 989.5 = 1979.0 despite meaningfully different purchasing power.

### Solution: Add a continuous ECA metric alongside the discrete one

**Add a new field to ECAResult:**

```python
# Continuous ECA — does NOT use floor(), shows true gradient
eca_continuous_tflops: float  # runs_per_budget × peak_TFLOP/s × alpha × delta
```

**Compute it in `compute_eca()`:**

```python
# Existing discrete metric (keep as-is):
affordable_chips = math.floor(runs)
eca_e = affordable_chips * peak_tflops

# NEW continuous metric:
eca_continuous_e = runs * peak_tflops  # no floor
eca_continuous = eca_continuous_e * alpha * delta_a
```

**Add continuous versions for all three scenarios:**

```python
eca_continuous_scenario_a: float
eca_continuous_scenario_b_mid: float
```

### Why both metrics matter:
- **Discrete ECA** (with floor) answers: "How many complete training runs can you actually execute?" — relevant for governance and practical capacity planning
- **Continuous ECA** (no floor) answers: "What is the gradient of the access gap?" — relevant for policy analysis and reveals purchasing power differences that the discrete metric hides

The paper should present both and explain why. This is a paper-side discussion point, but the code needs to compute both.

---

## Problem 3: India/Nigeria Get ECA = 0 for H100

### Current state:
With $10K budget and H100 at $3.933/hr:
- India (PPP 0.26): adjusted cost per run = $3.933 × 720 / 0.26 = $10,891 — exceeds $10K budget
- Nigeria (PPP 0.20): adjusted cost per run = $3.933 × 720 / 0.20 = $14,159 — exceeds $10K budget

`floor(10000/10891)` = 0 chips. ECA = 0. This is mathematically correct.

### Solution: Add multi-budget sweep

**Add a new function to `src/eca.py`:**

```python
def compute_eca_budget_sweep(
    records: list[dict],
    budgets: list[float] = [5_000, 10_000, 25_000, 50_000, 100_000],
    reference_hours: int = 720,
    normalization_method: str = "ppp",
) -> list[ECAResult]:
    """Run ECA for multiple budget levels. Returns results for all (country, budget) combinations."""
    all_results = []
    for budget in budgets:
        results = compute_eca(records, budget, reference_hours, normalization_method)
        all_results.extend(results)
    return all_results
```

**Add a CLI flag:**

```python
parser.add_argument("--budgets", type=str, default="10000",
                    help="Comma-separated budget values, e.g. '5000,10000,25000,50000'")
```

**Save multi-budget output to:**
```
outputs/tables/eca_budget_sweep.csv
```

---

## Changes Summary

| File | Change |
|------|--------|
| `src/eca.py` | Rename variables (α, δ), fix docstring, add continuous ECA fields, add budget sweep function |
| `src/eca.py` | Add `eca_continuous_tflops`, `eca_continuous_scenario_a`, `eca_continuous_scenario_b_mid` to ECAResult |
| `tests/test_eca.py` | Add tests for continuous metric, budget sweep, edge cases |

## New Tests to Add in `tests/test_eca.py`:

```python
def test_continuous_eca_shows_gradient(self):
    """Continuous ECA should differentiate countries that discrete ECA lumps together."""
    usa = make_record()
    germany = make_record(country_iso="DEU", country_name="Germany", ppp_factor=0.78, gdp_per_capita=52824, bis_tier=1)
    japan = make_record(country_iso="JPN", country_name="Japan", ppp_factor=0.69, gdp_per_capita=33950, bis_tier=1)
    results = compute_eca([usa, germany, japan], budget_usd=10_000, reference_hours=720)
    deu = next(r for r in results if r.country_iso == "DEU")
    jpn = next(r for r in results if r.country_iso == "JPN")
    # Discrete: both get floor(~2.x) = 2 chips → same ECA
    assert deu.affordable_chips == jpn.affordable_chips  # both 2
    # Continuous: Germany > Japan because PPP 0.78 > 0.69
    assert deu.eca_continuous_scenario_a > jpn.eca_continuous_scenario_a

def test_zero_discrete_nonzero_continuous(self):
    """Countries that can't afford 1 full run should still show nonzero continuous ECA."""
    usa = make_record()
    india = make_record(country_iso="IND", country_name="India", ppp_factor=0.26, gdp_per_capita=2485, bis_tier=2)
    results = compute_eca([usa, india], budget_usd=10_000, reference_hours=720)
    ind = next(r for r in results if r.country_iso == "IND")
    assert ind.affordable_chips == 0  # Can't afford 1 run
    assert ind.eca_continuous_scenario_a > 0  # But continuous shows partial capacity

def test_budget_sweep_produces_multiple_results(self):
    """Budget sweep should produce len(countries) × len(budgets) results."""
    records = [make_record()]
    results = compute_eca_budget_sweep(records, budgets=[10_000, 25_000])
    assert len(results) == 2  # 1 country × 2 budgets
```
