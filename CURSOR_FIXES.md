# Audit Fixes — Access Accounting (ICML 2026)

This README lists every change needed to resolve the audit findings. It is written for Cursor: each section has a clear **File**, **Find**, and **Replace** so you can apply changes in sequence with Cmd/Ctrl+F or by asking Cursor's agent to apply them.

There are **5 required changes** (4 in the paper, 1 in the repo) and **1 optional housekeeping change**.

---

## Before you start

Run this once to capture a known-good baseline, so you can confirm nothing else moves:

```bash
python -m src.aar --config data/ --output /tmp/aar_before.csv
python -m src.eca --aar /tmp/aar_before.csv --budget 10000 --normalization ppp --output /tmp/eca_before.csv
md5sum /tmp/aar_before.csv /tmp/eca_before.csv
```

Keep those checksums. After all changes, re-run and confirm the checksums are **identical** (the repo change is labeling-only; no computed value should move).

---

## Change 1 — Paper abstract: "16:1" → "18:1"

**File:** paper `.tex` source (abstract section)

**Find:**
```
producing a 9:1 disparity from economic constraints alone that widens
to 16:1 when partial export control compounding is assumed
```

**Replace with:**
```
producing a 9:1 disparity from economic constraints alone that widens
to 18:1 when partial export control compounding is assumed
```

**Why:** `US A100 Scenario A ÷ Nigeria A100 Scenario B mid = 2808 ÷ 156 = 18.00`. Both values are in `outputs/tables/eca_results.csv`. "16:1" is not derivable from any defined scenario.

**Verify after edit:**
```bash
awk -F',' '$3=="aws" && $5=="A100_SXM4" && $8=="ppp" && ($2=="USA" || $2=="NGA") {print $1, "scen_a="$21, "scen_b_mid="$23}' outputs/tables/eca_results.csv
# Expected:
#   United States scen_a=2808.0 scen_b_mid=2808.0
#   Nigeria       scen_a=312.0  scen_b_mid=156.0
#   2808 / 156 = 18.0
```

---

## Change 2 — Paper §7 Conclusion: "16:1" → "18:1"

**File:** paper `.tex` source (§7 Conclusion)

**Find:**
```
a 9:1 disparity between
U.S. and Nigerian researchers from economic constraints
alone, widening to 16:1 when export control compounding
is assumed
```

**Replace with:**
```
a 9:1 disparity between
U.S. and Nigerian researchers from economic constraints
alone, widening to 18:1 when export control compounding
is assumed
```

**Why:** Second occurrence of the same claim as Change 1. Must match.

---

## Change 3 — Paper Table 3, Germany row, GCP column: "$1.620" → "$1.470"

**File:** paper `.tex` source (Table 3, cross-provider pricing)

**Find (the Germany row of Table 3):**
```
Germany       & \$1.475 & \$1.620 & \$6.923
```
*(Your exact LaTeX may use different column separators — search for "Germany" near "1.620" in Table 3 and update the middle value.)*

**Replace with:**
```
Germany       & \$1.475 & \$1.470 & \$6.923
```

**Why:** Germany has no local GCP region. The AAR builder routes it to the first GA region (`us-central1`), priced at $1.47. The $1.620 figure corresponds to `europe-west4`, which is never selected for Germany by the repo's own routing logic. Confirmed in `outputs/tables/aar_records.csv`.

**Verify after edit:**
```bash
awk -F',' 'NR==1 || ($1=="Germany" && $3=="gcp" && $5=="A100_SXM4") {print $1, $4, $13}' outputs/tables/aar_records.csv
# Expected:
#   Germany gcp us-central1 1.47
```

---

## Change 4 — Paper Table 3, Nigeria row, GCP column: "$1.620" → "$1.470"

**File:** paper `.tex` source (Table 3, cross-provider pricing)

**Find (the Nigeria row of Table 3):**
```
Nigeria       & \$1.475 & \$1.620 & \$4.648
```

**Replace with:**
```
Nigeria       & \$1.475 & \$1.470 & \$4.648
```

**Why:** Same fallback logic as Germany. Nigeria has no local GCP region; routes to `us-central1` at $1.47.

**Verify after edit:**
```bash
awk -F',' 'NR==1 || ($1=="Nigeria" && $3=="gcp" && $5=="A100_SXM4") {print $1, $4, $13}' outputs/tables/aar_records.csv
# Expected:
#   Nigeria gcp us-central1 1.47
```

---

## Sanity check on surrounding text (no edit required)

After Changes 3 and 4, the sentence immediately following Table 3 still reads correctly:

> "AWS and GCP price A100 GPU-hours within a narrow $1.47 to $1.62 band globally."

Do **not** edit this sentence. The $1.62 upper bound still holds because Japan (`asia-northeast1`) and Singapore (`asia-southeast1`) remain in that range.

---

## Change 5 — Repo `data/providers.yaml`: label AWS A100 as Capacity Blocks

**File:** `data/providers.yaml`

**Find (lines 110–118 approximately):**
```yaml
# --- A100 SXM4 (p4d.24xlarge = 8x A100) ---
# Source: https://aws.amazon.com/ec2/pricing/on-demand/

- provider: aws
  gpu_class: A100_SXM4
  instance_type: p4d.24xlarge
  gpus_per_instance: 8
  pricing_type: on_demand
```

**Replace with:**
```yaml
# --- A100 SXM4 (p4d.24xlarge = 8x A100) ---
# Source: https://aws.amazon.com/ec2/capacityblocks/pricing/
# Per-GPU rate $1.475 is the AWS Capacity Blocks rate for p4d.24xlarge
# ($11.80/hr / 8 GPUs). Standard On-Demand p4d is ~$4.10/GPU-hr; the
# Capacity Blocks rate is used here for parity with the H100 entry above
# (both are Capacity Blocks), since Capacity Blocks is the comparable
# short-duration ML-training rate for this hardware class.

- provider: aws
  gpu_class: A100_SXM4
  instance_type: p4d.24xlarge
  gpus_per_instance: 8
  pricing_type: capacity_blocks
```

Then, further down in the same block (the `pricing_url` line that follows the AWS A100 regions list, ~line 178):

**Find:**
```yaml
  pricing_url: "https://aws.amazon.com/ec2/pricing/on-demand/"
  pricing_retrieval_date: "2026-04-30"
```

**Replace with:**
```yaml
  pricing_url: "https://aws.amazon.com/ec2/capacityblocks/pricing/"
  pricing_retrieval_date: "2026-04-30"
```

⚠️ Only the AWS A100 block's `pricing_url` should change. The GCP and Azure entries further down have their own `pricing_url` lines — leave those alone. Use Cursor's "find next" and confirm you are editing the line directly following the AWS A100 regions, **not** the GCP or Azure entries.

**Why:** The $1.475 per-GPU-hour rate is the AWS Capacity Blocks rate, not the standard on-demand rate (which is ~$4.10/GPU-hr). The H100 entry above is already correctly labeled `capacity_blocks`; this brings the A100 entry into parity. No computed value changes.

**Verify after edit:**
```bash
grep -A 3 "gpu_class: A100_SXM4" data/providers.yaml | head -8
# Expected under the `- provider: aws` block:
#   pricing_type: capacity_blocks
```

---

## Change 6 (OPTIONAL) — Repo `outputs/tables/aar_records.csv` regeneration

After Change 5, regenerate the output tables so they reflect the new label. **This is optional** — the only field that moves is `pricing_url` in `aar_records.csv`. No numerical value changes.

```bash
python -m src.aar --config data/ --output outputs/tables/aar_records.csv
python -m src.eca --aar outputs/tables/aar_records.csv --budget 10000 --normalization ppp --output outputs/tables/eca_results.csv
```

Commit the regenerated CSVs if you want the repo's outputs to be internally consistent with the new label, or skip if you prefer to minimize the diff.

---

## Final verification

After all 5 required changes:

```bash
# 1. Repo: re-run tests and confirm all pass
python -m pytest tests/ -q
# Expected: 33 passed

# 2. Repo: regenerate outputs and confirm key values unchanged
python -m src.aar --config data/ --output /tmp/aar_after.csv
python -m src.eca --aar /tmp/aar_after.csv --budget 10000 --normalization ppp --output /tmp/eca_after.csv

# 3. Confirm numerical outputs identical (only pricing_url should differ in AAR)
diff <(cut -d',' -f1-22,24- /tmp/aar_before.csv) <(cut -d',' -f1-22,24- /tmp/aar_after.csv)
# Expected: no output (files match except column 23, pricing_url)

diff /tmp/eca_before.csv /tmp/eca_after.csv
# Expected: no output (ECA results byte-identical)

# 4. Paper: grep for any remaining "16:1"
grep -n "16:1" *.tex
# Expected: no output

# 5. Paper: grep for any remaining "1.620" or "1.62" in Table 3 region
grep -n "1\.620\|\\\\\$1\.62" *.tex
# Expected: no output, OR only Japan row (Japan's GCP price IS legitimately $1.62)
```

---

## What this README deliberately does NOT change

The audit also flagged 6 lower-priority items as WARN (not FAIL). None are required for this submission round:

1. **A100 40GB vs 80GB label mismatch** — requires a pricing decision, not a label fix. Defer.
2. **Azure A100 eastus = $4.648 may be stale** — Azure is explicitly excluded from the headline analysis; doesn't affect any conclusion.
3. **Nigeria / Brazil / Singapore PPP fallback to 2021 ICP** — already documented in `countries.yaml` comments and acknowledged in §6 Limitations.
4. **GCP accelerator-only vs VM-bundled SKU** — paper already explains this methodological choice in §4.1.
5. **AWS standard on-demand reference** — once Change 5 is applied, the `pricing_type` field makes the methodology transparent.
6. **China Table 2 "Chips = 0"** — defensible under a "post-all-constraints" reading of the Chips column; consistent with ECA_A = 0 for China. No change.

If a reviewer raises any of these during review, they become candidates for the camera-ready revision — not the initial submission.
