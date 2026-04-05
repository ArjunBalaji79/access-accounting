# Data Sourcing Guide

Every data input in this project must be publicly verifiable. This document specifies exactly where to find each value and how to record it.

## countries.yaml

Each country entry requires:

### Required Fields

| Field | Source | URL |
|-------|--------|-----|
| `name` | — | Country name |
| `iso_alpha3` | ISO 3166-1 | Standard code |
| `bis_tier` | BIS AI Diffusion IFR (90 FR 4544) | [Federal Register](https://www.federalregister.gov/documents/2025/01/15/2025-00636/framework-for-artificial-intelligence-diffusion) |
| `tpp_cap` | BIS IFR Supplement 2 | Same document; 790M TPP for Tier 2 cumulative 2025-2027; null for Tier 1; 0 for Tier 3 |
| `ppp_factor` | World Bank ICP 2024 | [World Bank Data](https://data.worldbank.org/indicator/PA.NUS.PPPC.RF) — Use "PPP conversion factor, GDP (LCU per international $)" |
| `gdp_per_capita_usd` | World Bank WDI | [World Bank Data](https://data.worldbank.org/indicator/NY.GDP.PCAP.CD) |
| `rd_spend_per_researcher_usd` | UNESCO UIS | [UNESCO Data](http://data.uis.unesco.org/) — indicator: GERD per researcher (FTE) |

### How to Get PPP Factors

1. Go to https://data.worldbank.org/indicator/PA.NUS.PPPC.RF
2. Select country, download most recent year available
3. Record as `ppp_factor` — this is LCU per international dollar
4. For ECA computation, the affordability adjustment is: `ppp_adjusted_cost = nominal_cost_usd * (ppp_factor_country / ppp_factor_usa)`
5. Since USA PPP factor ≈ 1.0, this simplifies in practice

**Important**: The paper uses PPP conversion factor as a *proxy* for purchasing power of a local-currency research budget. It is NOT a claim that cloud prices are set in local currency. Document this assumption.

### Country Selection Rationale

Expand beyond the paper's 3-country pilot. Target 10 countries covering:
- **Tier 1 (3-4)**: USA, Germany, Japan, UK — major research economies
- **Tier 2 (4-5)**: India, Brazil, UAE, Singapore, Nigeria — range of economic development levels
- **Tier 3 (1-2)**: China, Russia — restricted access cases

This gives variation on all three layers simultaneously.

## providers.yaml

Each provider-region-GPU entry requires:

| Field | Source | How to Find |
|-------|--------|-------------|
| `provider` | — | aws / gcp / azure |
| `region_code` | Provider docs | e.g., `us-east-1`, `europe-west1` |
| `region_country_iso` | — | Map region to ISO country code |
| `gpu_class` | Provider instance docs | e.g., H100 SXM5, A100 SXM4 |
| `instance_type` | Provider docs | e.g., p5.48xlarge, a3-highgpu-8g |
| `gpus_per_instance` | Provider docs | Usually 8 |
| `on_demand_price_usd_per_gpu_hr` | Provider pricing page | Divide instance price by GPUs per instance |
| `reserved_price_usd_per_gpu_hr` | Provider pricing page | 1-year committed; null if unavailable |
| `spot_price_usd_per_gpu_hr` | Provider pricing page | null if unavailable |
| `availability_class` | Provider region-product matrix | GA / Limited / Waitlisted / Unavailable |
| `pricing_url` | — | Exact URL where you found the price |
| `pricing_retrieval_date` | — | ISO 8601 date you accessed the page |

### AWS Pricing Sources
- **H100 (p5 instances)**: https://aws.amazon.com/ec2/capacityblocks/pricing/
- **A100 (p4d instances)**: https://aws.amazon.com/ec2/pricing/on-demand/
- **Region availability**: https://aws.amazon.com/about-aws/global-infrastructure/regional-product-services/

### GCP Pricing Sources
- **H100/A100 (a3/a2 instances)**: https://cloud.google.com/compute/gpus-pricing
- **Region availability**: https://cloud.google.com/compute/docs/gpus/gpu-regions-zones

### Azure Pricing Sources
- **H100 (ND H100 v5)**: https://azure.microsoft.com/en-us/pricing/details/virtual-machines/linux/
- **Region availability**: https://azure.microsoft.com/en-us/explore/global-infrastructure/products-by-region/

### Mapping Countries to Regions

For each country, identify the **closest accessible provider region**:
- If a provider has a region IN the country → use that
- If not → use the nearest region the country can legally access
- Document latency/sovereignty implications as a note

Example:
- Nigeria (no AWS region) → EU-West (Ireland) is closest accessible
- India → AP-South (Mumbai) is local
- Germany → EU-Central (Frankfurt) is local

## gpus.yaml

Each GPU entry requires:

| Field | Source | How to Find |
|-------|--------|-------------|
| `name` | NVIDIA | e.g., "H100 SXM5 80GB" |
| `form_factor` | NVIDIA datasheet | SXM or PCIe — always use SXM for ECA |
| `memory_gb` | NVIDIA datasheet | e.g., 80 |
| `peak_flops_bf16_dense` | NVIDIA datasheet | **Dense BF16, no sparsity** — this is critical |
| `peak_flops_bf16_sparse` | NVIDIA datasheet | Record for reference but do NOT use in ECA |
| `datasheet_url` | NVIDIA | Exact URL |
| `tpp_value` | BIS IFR | Total Processing Performance value if defined; else null |

### NVIDIA Datasheet URLs
- **H100**: https://www.nvidia.com/en-us/data-center/h100/
- **A100**: https://www.nvidia.com/en-us/data-center/a100/
- **H200**: https://www.nvidia.com/en-us/data-center/h200/
- **B100/B200**: Check current NVIDIA data center product pages

### FLOP/s Convention (from paper)
> All peak FLOP/s values are taken from vendor datasheets at dense (non-sparse) BF16 precision for the SXM form factor. Sparsity is excluded to avoid inflated comparisons across chip generations where sparsity support varies.

This means:
- H100 SXM5: 989.5 TFLOP/s (dense BF16) — NOT 1,979 TFLOP/s (sparse)
- A100 SXM4: 312 TFLOP/s (dense BF16) — NOT 624 TFLOP/s (sparse)

Verify these numbers against current datasheets before using.

## Data Validation Checklist

Before running the pipeline, verify:
- [ ] Every pricing value has a URL and retrieval date
- [ ] PPP factors are from the same ICP year for all countries
- [ ] FLOP/s values are dense BF16, SXM, no sparsity
- [ ] BIS tiers match the IFR text (even though rescinded, use as design case)
- [ ] At least 8 countries spanning all 3 BIS tiers
- [ ] At least 2 cloud providers
- [ ] At least 2 GPU classes (H100 + A100 minimum)
- [ ] No proprietary data — every field traceable to a public URL
