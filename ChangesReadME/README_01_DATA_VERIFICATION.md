# README_01: Data Verification & YAML Fixes

## Priority: CRITICAL — Run this first
## What this does: Builds a verification agent, fetches live data, updates YAMLs

---

## Part A: Build the Verification Agent

Create a new file `src/verify_data.py` that programmatically verifies every data point in the YAML files against live sources. This script should be runnable as:

```bash
python -m src.verify_data --config data/ --output outputs/verification_report.json
```

### A1: World Bank API Verification

The World Bank v2 API is free, no key required. Use it to verify PPP and GDP data.

**Endpoints to hit:**

```
# Price level ratio (PPP/exchange rate), indexed to US=1.0
# This is indicator PA.NUS.PPPC.RF
# This is what the project uses as "ppp_factor"
GET https://api.worldbank.org/v2/country/{iso2}/indicator/PA.NUS.PPPC.RF?date=2020:2024&format=json&per_page=50

# GDP per capita, current USD
GET https://api.worldbank.org/v2/country/{iso2}/indicator/NY.GDP.PCAP.CD?date=2020:2024&format=json&per_page=50
```

**Country ISO-2 codes to query:**
```python
COUNTRY_MAP = {
    "USA": "US", "DEU": "DE", "JPN": "JP", "GBR": "GB",
    "IND": "IN", "BRA": "BR", "ARE": "AE", "SGP": "SG",
    "NGA": "NG", "CHN": "CN"
}
```

**What the script should do:**

1. For each country in `countries.yaml`, fetch the most recent available year from the World Bank API for both indicators.
2. Compare fetched values against what's in the YAML.
3. Flag any mismatch where the difference exceeds 10%.
4. Output a JSON report with structure:

```json
{
  "verification_date": "2026-04-30T...",
  "results": [
    {
      "country_iso": "IND",
      "field": "ppp_factor",
      "yaml_value": 0.26,
      "live_value": 0.27,
      "live_source": "World Bank PA.NUS.PPPC.RF",
      "live_year": 2023,
      "pct_diff": 3.8,
      "status": "OK"
    },
    ...
  ],
  "summary": {
    "total_checks": 20,
    "passed": 17,
    "warnings": 2,
    "failures": 1
  }
}
```

**Important API notes:**
- Use `requests` library (add to requirements.txt)
- The API returns JSON with structure: `[pagination_info, [data_records]]`
- Each data record has fields: `country.id`, `country.value`, `date` (year), `value` (the number)
- Some countries may not have 2024 data yet — fall back to 2023, then 2022
- UAE ISO-2 is "AE", not "UAE"
- Rate limit: be polite, add 0.5s sleep between requests
- If the API returns null for a value, log it as "DATA_UNAVAILABLE" not as a failure

**PPP factor clarification — VERY IMPORTANT:**

The project uses `PA.NUS.PPPC.RF` (price level ratio, US=1.0 baseline). This is NOT the same as `PA.NUS.PPP` (LCU per international dollar — this gives values like 22.88 for India in rupees). Make sure the script uses the correct indicator. The values in countries.yaml should be decimals between 0 and ~1.2, with USA = 1.0.

If the World Bank data for the most recent year differs significantly from the YAML "illustrative" values, the script should also print a recommendation like:

```
RECOMMENDATION: Update data/countries.yaml India ppp_factor from 0.26 to 0.27 (World Bank 2023)
```

### A2: AWS Pricing Verification

Scrape the AWS Capacity Blocks pricing page to verify GPU pricing.

**URL:** `https://aws.amazon.com/ec2/capacityblocks/pricing/`

**What to extract:**
- All p5.48xlarge rows: region, effective hourly rate per accelerator
- All p4d.24xlarge rows (if present): region, effective hourly rate per accelerator

**Approach:**
1. Use `requests` + `BeautifulSoup` (add `beautifulsoup4` to requirements.txt) to fetch the page
2. Parse the pricing tables for p5 (H100) and p4d (A100) sections
3. Extract per-accelerator hourly rates by region
4. Compare against `providers.yaml` values

**Known findings from manual verification (April 20, 2026):**
- H100 (p5.48xlarge) is $3.933/GPU-hr across most regions — CONFIRMED
- Exception: US West (N. California) = $4.916/GPU-hr — the YAML doesn't account for this
- p4d.24xlarge (A100) may NOT be listed on Capacity Blocks page — it may only be on the On-Demand pricing page (`https://aws.amazon.com/ec2/pricing/on-demand/`). If so, note this in the report.

**Regions listed on the Capacity Blocks page for p5.48xlarge (as of April 20, 2026):**
```
US East (N. Virginia), US East (Ohio), US West (Oregon), US West (N. California),
Asia Pacific (Tokyo), Asia Pacific (Jakarta), Asia Pacific (Mumbai), Australia (Sydney),
Europe (London), Europe (Stockholm), South America (São Paulo)
```

**Regions in our YAML that are NOT on the Capacity Blocks page:**
- `eu-west-1` (Ireland) — used as Nigeria's fallback region
- `eu-central-1` (Frankfurt) — used for Germany

These regions may have H100 via On-Demand pricing at a DIFFERENT rate, or may not have H100 at all. The script should flag this and try to verify from the On-Demand pricing page.

### A3: GCP Pricing Verification

**URL:** `https://cloud.google.com/compute/gpus-pricing`

This page is harder to scrape (dynamic content). The script should:
1. Try to fetch and parse the page
2. If scraping fails, flag all GCP values as "UNVERIFIED — requires manual check" and print the URL for the operator to visit
3. GCP prices DO vary by region (unlike AWS Capacity Blocks), so region-level verification matters

### A4: GPU Spec Verification

The GPU specs are already verified, but the script should still confirm:

```python
VERIFIED_GPU_SPECS = {
    "H100_SXM5": {
        "peak_tflops_bf16_dense": 989.5,  # NVIDIA datasheet, footnote: specs 1/2 without sparsity
        "peak_tflops_bf16_sparse": 1979.0,
        "source": "NVIDIA H100 datasheet — dense BF16 Tensor Core (non-sparse)",
        "verification_note": "1979 is WITH sparsity. 989.5 is WITHOUT. Paper convention = no sparsity."
    },
    "A100_SXM4": {
        "peak_tflops_bf16_dense": 312.0,
        "peak_tflops_bf16_sparse": 624.0,
        "source": "NVIDIA A100 datasheet",
        "verification_note": "No ambiguity — 312 dense BF16 is well-established."
    }
}
```

Compare against `gpus.yaml` and flag any discrepancy.

---

## Part B: Update YAML Files Based on Verification

After running the verification agent, update the YAML files with confirmed values. **Only change values that the verification agent flags as mismatched.** Preserve all comments and structure.

### B1: countries.yaml Changes

For each country, if the World Bank API returns a value that differs from the YAML by more than 5%:
- Update the value
- Add a comment with the source year: `# World Bank PA.NUS.PPPC.RF 2023`
- Change `notes` to include verification date

**Also add a new field to each country entry:**

```yaml
data_verified_date: "2026-04-30"  # ISO 8601 date of last verification
```

### B2: providers.yaml Changes

**Specific fixes to make regardless of verification results:**

1. **Add missing regions** that ARE on the Capacity Blocks page but missing from YAML:
   - `ap-southeast-3` (Jakarta, IDN) — $3.933 for H100
   - `ap-northeast-2` (Seoul, KOR) — check if listed
   - `ap-southeast-2` (Sydney, AUS) — $3.933 for H100

2. **Fix or remove phantom regions** that are NOT on the Capacity Blocks page:
   - If `eu-west-1` (Ireland) is NOT on the Capacity Blocks page for H100, check if it's available via On-Demand. If it IS available at a different price, update the price. If NOT available for H100, change availability_class to "Unavailable" and add a note.
   - Same check for `eu-central-1` (Frankfurt).

3. **Update pricing_retrieval_date** to today's date for all verified entries.

4. **Add a pricing_type field** to distinguish Capacity Blocks vs On-Demand:
   ```yaml
   pricing_type: "capacity_blocks"  # or "on_demand"
   ```
   This matters because the paper needs to be clear about which pricing tier it uses.

### B3: gpus.yaml Changes

No value changes needed (already verified). But add clarifying comments:

```yaml
# VERIFICATION NOTE (2026-04-30):
# NVIDIA H100 datasheet lists BF16 Tensor Core at 1,979 TFLOP/s.
# Footnote: "Shown with sparsity. Specifications 1/2 lower without sparsity."
# Dense BF16 (no sparsity) = 989.5 TFLOP/s. This is what ECA uses.
# Source: https://resources.nvidia.com/en-us-gpu-resources/h100-datasheet-24306
```

---

## Part C: Update requirements.txt

Add the new dependencies:

```
pyyaml>=6.0
matplotlib>=3.7
numpy>=1.24
pytest>=7.0
requests>=2.31
beautifulsoup4>=4.12
```

---

## Validation After Changes

After running the verification agent and updating YAMLs, re-run the full pipeline to make sure nothing breaks:

```bash
python -m pytest tests/ -v
python -m src.aar --config data/ --output outputs/tables/aar_records.csv
python -m src.eca --aar outputs/tables/aar_records.csv --budget 10000 --hours 720
```

All tests should still pass, and the ECA output should now reflect verified data values.
