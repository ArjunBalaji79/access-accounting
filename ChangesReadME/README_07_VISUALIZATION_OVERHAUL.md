# README_07: Visualization Overhaul — Paper-Ready Figures

## Priority: HIGH — replaces README_03 entirely
## What this does: Deletes all existing chart code and rebuilds from scratch
## Philosophy: Every figure must answer a specific question a TAIGR reviewer would ask

---

## The Problem With The Current Charts

The existing 6 charts were built to validate the pipeline, not to make an argument in a paper. A TAIGR reviewer will look at each figure and ask: "What claim does this support? Why should I care?" Most of the current charts fail this test:

- **H100 compounding gap**: 5 of 10 countries are blank (zero bars). The chart's own evidence undermines its claim.
- **Provider comparison**: Shows that provider choice barely matters — which IS a finding, but the chart doesn't frame it as one. Azure appears for only one country, making it look like broken data.
- **Budget sweep**: Analytically interesting but visually cluttered. 10 overlapping lines with similar slopes.
- **Discrete vs continuous**: A methods point, not a paper point. Belongs in supplementary material at best.
- **Four shades of blue** across all charts: Hard to distinguish in print. Fails the "photocopy test" — would a black-and-white printout be readable?

---

## Design Principles for ICML Workshop Figures

1. **One figure, one claim.** If you can't state what the figure proves in one sentence, it doesn't belong.
2. **Use A100 as the primary GPU.** At $10K budget, A100 makes every country visible. H100 results go in supplementary or as a panel.
3. **Color encodes BIS tier, not layer.** Tier 1 = blue, Tier 2 = amber/orange, Tier 3 = red. This is the framework's most novel dimension. Make it visually dominant.
4. **Max 5 countries per chart when possible.** The pilot is Germany, India, Nigeria. Add USA as baseline and one interesting case (Singapore or Brazil). 10 countries crammed into one chart is noisy.
5. **Print-safe.** Must work in grayscale. Use hatching, markers, or varying line dash patterns alongside color.
6. **8-page workshop paper.** You get 3-4 figures max. Every one must earn its place.

---

## Proposed Figure Set (4 figures)

### Figure 1: "The Compounding Gap" — THE hero figure

**Claim it supports:** Access gaps compound multiplicatively across layers. Economic disadvantage alone understates the true gap.

**Chart type:** Horizontal waterfall / stacked reduction chart for 5 countries

**Countries:** USA (baseline), Germany (Tier 1 but not US), India (Tier 2, low PPP), Nigeria (Tier 2, lowest PPP, no local region), China (Tier 3, blocked)

**GPU:** A100 SXM4 (all countries have nonzero values)

**Design:**

```
For each country, show a single horizontal bar that starts at the
"nominal" ECA value (what $10K buys at face-value pricing) and gets
progressively reduced by each constraint layer:

USA:     ██████████████████████████████████████████████████  100% (2,808 TFLOP/s)
Germany: ████████████████████████████████████░░░░░░░░░░░░░░   78% (2,184) — PPP adjustment
India:   █████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   22% (624)  — PPP
India†:  ████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   11% (312)  — + Legal (Scenario B)
Nigeria: ███░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   11% (312)  — PPP
Nigeria†:█░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░    6% (156)  — + Legal (Scenario B)
China:   ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░    0%        — Tier 3 blocked
```

**Implementation details:**
- Horizontal bars, not vertical. Easier to label, easier to read country names.
- Each country gets TWO bars: (1) "After PPP" — economic gap only, (2) "After PPP + Legal (Scenario B mid)" — full compounding. The visual gap between these two bars IS the legal layer effect.
- USA gets one bar (baseline — PPP=1, Tier 1, δ=1).
- Germany gets one bar (PPP adjustment is the only reduction — Tier 1 so legal doesn't further reduce).
- Color the filled portion by BIS tier: blue for Tier 1, amber for Tier 2, red for Tier 3.
- The "lost" portion (gray fill) represents the access that PPP/legal constraints remove.
- Right-align percentage labels: "78% of US", "22% of US", etc.
- Add a small icon or symbol for non-local routing (Nigeria).
- NO grid lines, NO tick marks on y-axis. Clean.

**matplotlib approach:**
```python
fig, ax = plt.subplots(figsize=(10, 5))
# Use barh() with two colors: filled = accessible, gray = lost
# Stack: gray first (full width), then colored on top (accessible portion)
```

**Title:** "Effective Compute Access under $10,000 budget — A100 SXM4 / AWS"
**Subtitle/caption:** "Each bar shows the share of US-baseline access remaining after PPP and legal adjustments. Scenario B assumes partial TPP cap consumption for Tier 2 countries."

---

### Figure 2: "The Budget Threshold" — where countries "turn on"

**Claim it supports:** The access gap is not just a ratio — there are hard budget thresholds below which access drops to zero for frontier GPUs.

**Chart type:** Step function / threshold chart

**Design:** Show H100 (frontier GPU) only. X-axis is budget ($5K to $50K). Y-axis is number of affordable training runs (discrete, integers). One line per country.

The key visual insight: the step function. Each country has a specific budget threshold where they can first afford 1 run. For USA that's ~$2,800. For India it's ~$10,900. For Nigeria it's ~$14,200. Below the threshold: zero. Above: it climbs in discrete steps.

```
Runs │
  3  │            ┌─────── USA
     │    ┌───────┘
  2  │    │           ┌─── Germany
     │────┘     ┌─────┘
  1  │          │         ┌── India
     │    ──────┘   ──────┘         ┌── Nigeria
  0  │────────────────────────────────────────
     $5K        $10K       $15K      $20K    $25K
```

**Implementation details:**
- Use `plt.step()` not `plt.plot()` — the step function is the point.
- 5 countries max: USA, Germany, India, Nigeria, China (flat at zero).
- Annotate the threshold budget for each country with a small vertical tick and label.
- Color by BIS tier.
- This figure tells a story the A100 chart can't: at frontier GPU pricing, there are hard walls where purchasing power makes access binary, not gradual.

**Title:** "Budget thresholds for frontier compute access — H100 SXM5 / AWS"
**Caption:** "Step function showing discrete training runs affordable at each budget level. Vertical annotations mark the minimum budget for ≥1 run."

---

### Figure 3: "Rank Stability" — the robustness argument

**Claim it supports:** Access gap rankings are stable regardless of which affordability normalization method you use.

**Keep the existing sensitivity heatmap (image 6) but improve it:**

The current heatmap is the closest to paper-ready. Changes needed:

1. **Use A100 data** so all countries have nonzero ECA values and the ranking differences are meaningful (not just "who has zero").
2. **Show only 5-7 countries** — the full 10 creates visual noise. Drop China (always last, always zero — not interesting for rank analysis). Drop USA (always first — not interesting either). Show the middle 6-8 where rank instability actually occurs.
3. **Add a second panel** showing the actual ECA values (not just ranks) so the reader can see that a rank change from 3→5 might correspond to a tiny ECA difference.
4. **Replace the continuous color scale with a discrete 3-color coding:**
   - Green: same rank as PPP baseline (stable)
   - Yellow: ±1 position (minor shift)
   - Orange/red: ±2 or more positions (noteworthy instability)
5. **Keep the Kendall's τ in the title** — reviewers love seeing a formal correlation measure.

**Title:** "Rank stability of ECA across normalization methods — A100 SXM4 / AWS"

---

### Figure 4: "The A100 Equalizer" — cheaper GPUs narrow but don't close the gap

**Claim it supports:** Shifting to cheaper GPU classes reduces the absolute gap but preserves the ordinal ranking and the compounding structure.

**Chart type:** Paired dot plot / dumbbell chart

**Design:** For each country, show two dots connected by a line:
- Left dot: ECA with H100 (at $25K budget so all countries are nonzero)
- Right dot: ECA with A100 (at $10K budget — the standard reference)

```
Nigeria  ●────────────────────────●
India    ●──────────────────────────────●
Brazil        ●──────────────────────────────●
Singapore          ●──────────────────────────────────●
Germany                    ●────────────────────────────────────●
USA                                ●────────────────────────────────────────●
         ├──────────┼──────────┼──────────┼──────────┼──────────┤
         0       1,000     2,000     3,000     4,000     5,000
                            ECA (TFLOP/s)
```

Each country gets one line connecting its H100 ($25K) dot and its A100 ($10K) dot. The gap between Nigeria's dots and USA's dots shows the persistent inequality. The fact that A100 dots are generally closer together than H100 dots shows the narrowing effect.

**Implementation:**
```python
# Dumbbell chart using hlines + scatter
for i, country in enumerate(countries):
    ax.hlines(y=i, xmin=h100_eca, xmax=a100_eca, color='gray', linewidth=1)
    ax.scatter(h100_eca, i, color=tier_color, marker='s', s=60, label='H100 $25K' if i==0 else '')
    ax.scatter(a100_eca, i, color=tier_color, marker='o', s=60, label='A100 $10K' if i==0 else '')
```

**Title:** "GPU class effect: cheaper hardware narrows but does not close the access gap"

---

## Charts to DROP (do not include in paper)

| Current Chart | Why Drop It |
|--------------|-------------|
| Provider comparison | Shows provider doesn't matter much — mention this as a text finding, not a figure. Azure data is too sparse for visual. |
| Discrete vs continuous | Methods point. Mention in text: "We note that floor division creates discrete plateaus; a continuous variant is available in the reference implementation." One sentence, no figure. |
| H100 compounding gap (4-bar version) | Too many zeros. The claim is better made with A100 (Figure 1) + H100 threshold (Figure 2). |

---

## Supplementary / Appendix Figures (if workshop allows appendix)

These are useful but not main-body:

- **Full 10-country A100 compounding gap** (the current image 2 — cleaned up)
- **Budget sweep line chart** (current image 1 — cleaned up, fewer countries)
- **Cross-provider comparison** for countries where it matters (if Azure data improves)
- **LaTeX table** of all AAR-Core records (Table 2 in the paper)

---

## Style Specification for ALL Figures

### Typography
```python
plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['Helvetica Neue', 'Arial', 'DejaVu Sans'],
    'font.size': 10,
    'axes.titlesize': 12,
    'axes.labelsize': 11,
    'xtick.labelsize': 9,
    'ytick.labelsize': 9,
    'legend.fontsize': 9,
    'figure.dpi': 300,
})
```

### Color Palette (BIS tier encoding, consistent across ALL figures)
```python
TIER_COLORS = {
    1: '#2166AC',   # Steel blue — trusted, stable
    2: '#D6604D',   # Muted red-orange — constrained
    3: '#4D4D4D',   # Dark gray — blocked/prohibited
}

# For fills/backgrounds (lighter versions)
TIER_FILLS = {
    1: '#92C5DE',
    2: '#F4A582',
    3: '#BABABA',
}
```

### Grayscale fallback
Every chart must work in grayscale. In addition to color:
- Tier 1: solid fill, no pattern
- Tier 2: diagonal hatch pattern (45-degree lines)
- Tier 3: cross-hatch or dotted fill

```python
import matplotlib.patches as mpatches
# For hatching in matplotlib:
# Tier 1: no hatch
# Tier 2: hatch='///'
# Tier 3: hatch='xxx'
```

### Layout
- `figsize=(7, 4)` for single-column ICML workshop figures
- `figsize=(14, 4)` for full-width figures (use sparingly)
- Always `bbox_inches='tight'` on `savefig()`
- Remove top and right spines: `ax.spines['top'].set_visible(False)` etc.
- Minimal grid: `ax.yaxis.grid(True, alpha=0.3, linestyle=':')`

### Source attribution
Every figure gets a small source line:
```python
fig.text(0.5, -0.02,
    'Source: AWS Capacity Blocks pricing (Apr 2026), World Bank ICP 2024, BIS 90 FR 4544',
    ha='center', fontsize=7, color='#888888')
```

---

## Implementation: New `src/visualize.py`

Delete the existing `visualize.py` content entirely. Replace with a new module that generates only these 4 figures (plus optionally the supplementary ones behind a `--supplementary` flag).

```python
"""
Publication figures for Access Accounting (TAIGR @ ICML 2026).

Generates 4 main figures + optional supplementary figures.
All figures use consistent BIS-tier color encoding.

Usage:
    python -m src.visualize --results outputs/tables/ --output outputs/figures/
    python -m src.visualize --results outputs/tables/ --output outputs/figures/ --supplementary
"""
```

### CLI:
```python
parser.add_argument("--results", type=Path, default=Path("outputs/tables/"))
parser.add_argument("--output", type=Path, default=Path("outputs/figures/"))
parser.add_argument("--supplementary", action="store_true", help="Also generate appendix figures")
parser.add_argument("--format", default="png", choices=["png", "pdf", "svg"],
                    help="Output format (pdf recommended for LaTeX)")
```

### Output files:
```
outputs/figures/
  fig1_compounding_gap.pdf
  fig2_budget_threshold.pdf
  fig3_rank_stability.pdf
  fig4_gpu_class_effect.pdf
  # If --supplementary:
  figS1_full_country_waterfall.pdf
  figS2_budget_sweep_lines.pdf
```

### Key function signatures:

```python
def fig1_compounding_gap(eca_data, output_path, countries=None, gpu_class="A100_SXM4", provider="aws"):
    """Horizontal waterfall showing PPP + legal compounding for 5 countries."""

def fig2_budget_threshold(sweep_data, output_path, countries=None, gpu_class="H100_SXM5", provider="aws"):
    """Step function showing discrete affordable runs vs budget."""

def fig3_rank_stability(sensitivity_data, output_path, gpu_class="A100_SXM4", provider="aws"):
    """Improved heatmap with stability coloring and actual ECA values."""

def fig4_gpu_class_effect(eca_data_h100, eca_data_a100, output_path, countries=None, provider="aws"):
    """Dumbbell chart comparing H100 ($25K) vs A100 ($10K) access."""
```

---

## Summary: What Each Figure Argues

| Figure | One-sentence claim | Section it supports |
|--------|-------------------|-------------------|
| Fig 1 | Access gaps compound: PPP alone understates the gap by 2-3x; adding legal constraints doubles it again | Section 4 (Pilot results) |
| Fig 2 | Below ~$11K, Indian researchers cannot run a single frontier training job — access is binary, not gradual | Section 3 (Motivation — why access accounting matters) |
| Fig 3 | Gap rankings are stable (τ > 0.7) across three normalization methods — the framework is robust | Section 5 (Sensitivity analysis) |
| Fig 4 | Cheaper GPUs narrow the absolute gap but preserve the ranking — the structural inequality persists across hardware generations | Section 4 (Pilot results, GPU class comparison) |
