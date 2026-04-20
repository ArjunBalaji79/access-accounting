# Access Accounting — Change Plan for ICML 2026 Submission

## Date: April 30, 2026
## Project: access-accounting (TAIGR @ ICML 2026)

---

## What This Is

This folder contains 5 detailed READMEs, each describing a specific set of changes to make to the codebase before the paper is submitted. They are designed to be fed to Claude Code in order.

## Execution Order — THIS MATTERS

```
README_01 → README_02 → README_03 → README_04 → README_05
   ↓            ↓            ↓            ↓            ↓
 Verify      Fix ECA      Fix charts    Enhance      Add tests
 & fix       formula      & add new     AAR with     & final
 all data    alignment    visuals       locality     validation
                                        flags
```

**README_01 must run first** because it builds the verification agent, fetches live data, and updates the YAML files. Every subsequent README depends on correct data.

## What Was Found During Audit

### Two Critical Mismatches (paper vs code)

1. **H100 FLOP/s**: The background PDF says 1,979 TFLOP/s for dense BF16. The code uses 989.5 TFLOP/s. NVIDIA's datasheet footnote says "Shown with sparsity. Specifications 1/2 lower without sparsity." **The code is correct at 989.5. The paper must be updated** (paper-side fix, not code).

2. **ECA formula**: The paper says `ECA = min(ECA_Phys, ECA_E) × δ`. The code computes `eca_base = eca_e * eca_phys` (multiplication, not min). **The multiplication is the correct approach** — `min()` of a 0-1 score and a TFLOP/s number is dimensionally nonsensical. The paper formula should be updated to match the code (paper-side fix), but the code also needs a small fix for clarity — see README_02.

### Data Verification Status

| Data Point | Status | Detail |
|-----------|--------|--------|
| H100 dense BF16 FLOP/s | ✅ Verified | 989.5 TFLOP/s — code is correct |
| A100 dense BF16 FLOP/s | ✅ Verified | 312 TFLOP/s — code is correct |
| AWS H100 pricing ($3.933) | ✅ Verified | Confirmed from live Capacity Blocks page as of April 20, 2026. Uniform across most regions. Exception: US West (N. California) = $4.916 |
| GCP H100 pricing | ⚠️ Needs live verification | Values in YAML are "illustrative" |
| PPP factors | ⚠️ Needs live verification | YAML says "illustrative based on ICP 2024" — must fetch real values from World Bank API |
| GDP per capita | ⚠️ Needs live verification | Same — must fetch from World Bank API |
| R&D per researcher | ⚠️ Needs live verification | UNESCO UIS data — may be harder to automate |
| BIS tier assignments | ✅ Correct | Matches Federal Register 90 FR 4544 text |
| Region availability classes | ⚠️ Needs manual spot-check | GA/Limited/Waitlisted status changes frequently |

### Visualization Issues Found

1. **India and Nigeria show ECA = 0 for H100** at $10K budget — mathematically correct but visually weak. Need multi-budget charts.
2. **Floor division creates plateaus** — Germany, Japan, UK all show identical ECA despite different PPP. Need continuous "runs affordable" metric alongside.
3. **Compounding gap chart** uses `eca_economic_tflops` for "Economic only" bar but this doesn't actually exclude availability — it's the same as Scenario A for GA countries. The layered decomposition needs fixing.

## Paper-Side Changes (NOT in these READMEs)

These changes must be made in the LaTeX/PDF — they cannot be automated:

1. Change all mentions of "1,979 TFLOP/s" for H100 dense BF16 to "989.5 TFLOP/s"
2. Update the ECA formula from `min(ECA_Phys, ECA_E) × δ` to `ECA_E × α(availability) × δ(legal)`
3. Acknowledge floor-division plateau effect as a known property of the discrete metric
4. Explain the PPP interpretation clearly and consistently (higher real cost for lower-PPP countries when cloud is priced in USD)

## Files That Will Be Modified

```
MODIFIED:
  data/countries.yaml          — Updated with verified PPP, GDP values
  data/providers.yaml          — Updated with verified pricing, fixed regions
  data/gpus.yaml               — Add notes clarifying dense vs sparse convention
  src/eca.py                   — Fix formula, add continuous metric, improve variable naming
  src/aar.py                   — Add is_local_region flag, routing_notes
  src/sensitivity.py           — Minor: budget sweep support
  src/visualize.py             — New charts: multi-budget, continuous, A100 primary
  tests/test_eca.py            — New tests for continuous metric, edge cases

NEW:
  src/verify_data.py           — Verification agent (World Bank API, AWS/GCP scraping)
  outputs/verification_report.json  — Machine-readable verification output
```
