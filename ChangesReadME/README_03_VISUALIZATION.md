# README_03: Visualization Fixes & New Charts

## Priority: HIGH
## What this does: Fixes existing charts, adds multi-budget and continuous views
## Depends on: README_01 (verified data), README_02 (continuous metric + budget sweep)

---

## Problem 1: Compounding Gap Chart Has Wrong Decomposition

### Current state:
The chart shows three bars per country:
1. "Economic only" — uses `eca_economic_tflops` (= affordable_chips × peak_TFLOP/s)
2. "+ Physical" — uses `eca_scenario_a` (= eca_e × alpha × 1.0)
3. "+ Legal (Scenario B)" — uses `eca_scenario_b_mid` (= eca_e × alpha × 0.5)

**The problem:** For any GA country (alpha=1.0), bars 1 and 2 are identical because `eca_scenario_a = eca_e × 1.0 = eca_e`. The "physical" layer appears to have zero effect on most countries, which is misleading.

Also, Tier 1 countries show bars 2 and 3 as identical (because delta=1.0 for all scenarios when Tier 1). The chart only shows meaningful compounding for Tier 2 countries with Limited/Waitlisted availability.

### Fix:
Restructure the chart to show true layer-by-layer decomposition:

```python
# Bar 1: Pure economic (what budget buys at nominal price, no PPP adjustment, no availability, no legal)
pure_nominal = math.floor(budget / (price * H)) * peak_tflops

# Bar 2: + PPP adjustment (purchasing power applied)
with_ppp = eca_e  # affordable_chips after PPP × peak_TFLOP/s

# Bar 3: + Availability constraint
with_availability = eca_e * alpha

# Bar 4: + Legal constraint (Scenario B mid)
with_legal = eca_e * alpha * delta_b_mid
```

This shows four layers:
- Nominal → PPP: purchasing power gap
- PPP → Availability: infrastructure gap
- Availability → Legal: regulatory gap

**To implement this**, add `eca_nominal_tflops` to `ECAResult`:
```python
# In compute_eca(), add:
nominal_chips = math.floor(budget_usd / (price * reference_hours))
eca_nominal_tflops = nominal_chips * peak_tflops
```

Then update `fig_compounding_gap()` to use four bars instead of three.

### New chart function signature:

```python
def fig_compounding_gap(
    eca_data: list[dict],
    output_path: Path,
    gpu_class: str = "H100_SXM5",
    provider: str = "aws",
) -> None:
```

**Design notes:**
- Use four bars per country: "Nominal", "+ PPP", "+ Availability", "+ Legal (B)"
- Colors: from light to dark, suggesting compounding restriction
- Sort countries by their nominal ECA (highest first), NOT by Scenario A
- Add percentage annotations showing how much each layer reduces access
- Use a secondary y-axis or annotation showing "X% of US access" for each country

---

## Problem 2: India/Nigeria Show as Blank Bars

### Fix: Add A100-primary chart

The A100 at $1.475/hr makes all countries visible even at $10K:
- India: floor(10000 / (1.475 × 720 / 0.26)) ≈ 2 chips
- Nigeria: floor(10000 / (1.475 × 720 / 0.20)) ≈ 1 chip

**Create a new figure:** `compounding_gap_a100.png`

This should be generated alongside the H100 version. In the paper, the A100 chart can be the primary visual (where all countries have non-zero bars), with the H100 chart as a secondary "this is where the gap becomes total" visual.

### Fix: Add multi-budget chart

**New function:**

```python
def fig_budget_sweep(
    sweep_data: list[dict],
    output_path: Path,
    gpu_class: str = "H100_SXM5",
    provider: str = "aws",
    countries: list[str] = None,  # If None, show all
) -> None:
    """
    Line chart: x-axis = budget ($5K to $100K), y-axis = ECA (TFLOP/s)
    One line per country. Shows where each country "turns on" (first nonzero ECA).
    """
```

**Design:**
- X-axis: Budget in USD (log or linear scale, $5K to $100K)
- Y-axis: ECA (TFLOP/s) under Scenario A
- One line per country, colored by BIS tier (Tier 1 = blue, Tier 2 = orange, Tier 3 = red)
- Vertical dashed lines at notable budgets ($10K = typical grant, $50K = major grant)
- The visual story: India "turns on" at ~$11K, Nigeria at ~$14K. At $25K they're both visible but far below US/Germany.

**Save as:** `outputs/figures/budget_sweep.png`

---

## Problem 3: No Continuous Metric Visualization

### New chart: Continuous ECA comparison

**New function:**

```python
def fig_continuous_vs_discrete(
    eca_data: list[dict],
    output_path: Path,
    gpu_class: str = "H100_SXM5",
    provider: str = "aws",
) -> None:
    """
    Side-by-side comparison showing how discrete (floor) and continuous
    ECA tell different stories. Reveals the plateau problem.
    """
```

**Design:**
- Two panels side by side (use `plt.subplots(1, 2, figsize=(16, 6))`)
- Left panel: Discrete ECA (current bar chart) — shows plateaus
- Right panel: Continuous ECA — shows true gradient
- Highlight with annotations where countries are "tied" in discrete but different in continuous
- Title: "Discrete vs. Continuous ECA — Why Both Matter"

**Save as:** `outputs/figures/continuous_vs_discrete.png`

---

## Problem 4: Sensitivity Heatmap Needs Better Labeling

### Current state:
The heatmap works well but Japan's rank jumps from 3 (PPP) to 6 (GDP) — this is the most interesting finding and it should be highlighted.

### Fix:
- Add cell-level annotations showing not just rank but also the actual ECA value
- Highlight cells where rank shifts by 2+ positions (add a border or marker)
- Add a row below showing Kendall's τ for each method pair

---

## New Figure List

After all changes, `src/visualize.py` should generate:

| Figure | File | Description |
|--------|------|-------------|
| 1 | `compounding_gap_h100.png` | 4-bar decomposition: Nominal → PPP → Availability → Legal (H100) |
| 2 | `compounding_gap_a100.png` | Same but for A100 — primary visual where all countries are visible |
| 3 | `budget_sweep.png` | Line chart: ECA vs budget ($5K-$100K) per country |
| 4 | `continuous_vs_discrete.png` | Side-by-side panels showing plateau problem |
| 5 | `sensitivity_heatmap.png` | Improved heatmap with rank-shift highlighting |
| 6 | `provider_comparison.png` | Cross-provider bars (keep existing, minor style updates) |

### Update the `main()` function in visualize.py:

```python
def main():
    # ... existing arg parsing ...

    # Load data
    eca_data = load_eca_csv(eca_path)

    # Generate all figures
    for gpu in ["H100_SXM5", "A100_SXM4"]:
        fig_compounding_gap(eca_data, output / f"compounding_gap_{gpu.lower()}.png", gpu_class=gpu)

    fig_provider_comparison(eca_data, output / "provider_comparison.png")
    fig_continuous_vs_discrete(eca_data, output / "continuous_vs_discrete.png")

    # Budget sweep (needs sweep data)
    sweep_path = results / "eca_budget_sweep.csv"
    if sweep_path.exists():
        sweep_data = load_eca_csv(sweep_path)
        fig_budget_sweep(sweep_data, output / "budget_sweep.png")

    # Sensitivity
    if sens_path.exists():
        sens_data = load_sensitivity_csv(sens_path)
        fig_sensitivity_heatmap(sens_data, output / "sensitivity_heatmap.png")
```

---

## Style Conventions for All Charts

- Font: use `plt.rcParams['font.family'] = 'sans-serif'`
- DPI: 200 for all saved figures
- Use `bbox_inches="tight"` on all `savefig()` calls
- Color scheme: consistent BIS tier coloring across all charts
  - Tier 1: `#4C78A8` (steel blue)
  - Tier 2: `#F58518` (amber)
  - Tier 3: `#E45756` (coral red)
- Add figure titles that are paper-ready (not just debug labels)
- Add source attribution in small text at bottom: "Source: AWS/GCP public pricing, World Bank ICP 2024, BIS 90 FR 4544"
