# README_06: Data Sovereignty Constraint Field

## Priority: MEDIUM
## What this does: Adds a data sovereignty field to AAR-Core that captures cross-border data transfer restrictions
## Depends on: README_04 (region locality flags — the sovereignty field interacts with routing)

---

## Why This Matters

The current AAR captures whether you can BUY chips (export controls) but not whether you can USE the assigned cloud region given your data. A German researcher with GDPR-protected health data may be unable to send it to a US cloud region even though Germany is Tier 1 with no chip restrictions. A Nigerian researcher routed to Ireland may face data protection compliance barriers under the NDPA that make the routing practically unusable.

Data sovereignty is an independent legal constraint that compounds with — but is separate from — BIS export controls. Without this field, the framework has a blind spot: it can score a country as "accessible" when a significant class of research workloads (anything involving personal data, government data, or sector-regulated data) is actually blocked.

### Where it fits conceptually

```
Export controls:     Can you BUY the chip?        (supply-side, BIS)
Data sovereignty:    Can you SEND your data there? (demand-side, national data protection law)

These are orthogonal:
  - Germany: BIS Tier 1 (unrestricted) + GDPR (restricted cross-border transfer)
  - Singapore: BIS Tier 2 (capped) + PDPA (conditional cross-border transfer)
  - USA: BIS Tier 1 (unrestricted) + None (no federal data localization law)
```

---

## Part A: Data Model Changes

### A1: Add field to `AARCoreRecord` in `src/aar.py`

Add this field to the dataclass, in the Legal layer section:

```python
@dataclass
class AARCoreRecord:
    # ... existing fields ...

    # Legal layer — existing
    bis_tier: int  # 1, 2, or 3
    tpp_cap: Optional[int]

    # Legal layer — NEW
    data_sovereignty_class: str
    # Values:
    #   "none"                    — No data localization or transfer restrictions
    #   "cross_border_restricted" — Transfer permitted with conditions (e.g. GDPR adequacy/SCCs)
    #   "localization_required"   — Processing/storage must remain in-country
    #   "transfer_prohibited"     — Cross-border transfer of covered data prohibited
    #
    # Records the MOST RESTRICTIVE legal constraint on transferring research data
    # to cloud compute regions outside the researcher's country.
    # Derived from applicable national data protection law at time of filing.
    # Examples: GDPR Art. 46-49, India DPDP Act 2023, China PIPL Art. 38-40.

    data_sovereignty_source: str
    # The specific law or regulation. E.g. "GDPR Art. 46-49", "NDPA 2023", "PIPL Art. 38-40"

    # ... existing metadata fields ...
```

### A2: Add sovereignty scores mapping

Add a mapping similar to `AVAILABILITY_SCORES`:

```python
SOVEREIGNTY_SCORES = {
    "none": 1.0,
    "cross_border_restricted": 0.7,   # Usable with compliance effort (SCCs, adequacy decisions)
    "localization_required": 0.2,     # Only local regions usable — severely limits options
    "transfer_prohibited": 0.0,      # Cannot send data to any foreign region
}
```

**Important design note:** These scores are NOT used in ECA computation in this version. They are recorded for future use and for descriptive analysis. The paper should present data sovereignty as a *reported constraint* in the AAR, not as a calibrated multiplier in ECA. The reason: unlike availability class (which has a clear operational meaning — can you provision the instance?), sovereignty constraints depend on the *type of data* the researcher is using, which varies per project. A researcher training on public text data faces no sovereignty constraint; the same researcher in the same country working with patient records faces a hard one.

The AAR records the *country-level regime* (what law applies). Whether it binds for a specific workload is context-dependent and noted in the paper as a limitation.

### A3: Add field to `countries.yaml`

Add these two fields to each country entry in `data/countries.yaml`:

```yaml
# === TIER 1 COUNTRIES ===

- name: United States
  iso_alpha3: USA
  bis_tier: 1
  # ... existing fields ...
  data_sovereignty_class: "none"
  data_sovereignty_source: "No federal data localization law; sectoral rules (HIPAA, FERPA) may apply to specific data types but do not impose blanket cross-border restrictions"

- name: Germany
  iso_alpha3: DEU
  bis_tier: 1
  # ... existing fields ...
  data_sovereignty_class: "cross_border_restricted"
  data_sovereignty_source: "GDPR Art. 46-49; transfers outside EU/EEA require adequacy decision, SCCs, or BCRs; Schrems II (C-311/18) invalidated Privacy Shield for US transfers"

- name: Japan
  iso_alpha3: JPN
  bis_tier: 1
  # ... existing fields ...
  data_sovereignty_class: "cross_border_restricted"
  data_sovereignty_source: "APPI Art. 28; cross-border transfer requires consent or equivalent protection finding; Japan has EU adequacy decision"

- name: United Kingdom
  iso_alpha3: GBR
  bis_tier: 1
  # ... existing fields ...
  data_sovereignty_class: "cross_border_restricted"
  data_sovereignty_source: "UK GDPR Art. 46-49; post-Brexit adequacy from EU; similar transfer mechanism requirements as GDPR"

# === TIER 2 COUNTRIES ===

- name: India
  iso_alpha3: IND
  bis_tier: 2
  # ... existing fields ...
  data_sovereignty_class: "cross_border_restricted"
  data_sovereignty_source: "DPDP Act 2023 Sec. 16(1); central govt may restrict transfer to specified countries; implementing rules pending as of 2026; RBI data localization mandate applies to payment data"

- name: Brazil
  iso_alpha3: BRA
  bis_tier: 2
  # ... existing fields ...
  data_sovereignty_class: "cross_border_restricted"
  data_sovereignty_source: "LGPD Art. 33; transfer requires adequacy finding, SCCs, or consent; ANPD has not yet issued adequacy list"

- name: United Arab Emirates
  iso_alpha3: ARE
  bis_tier: 2
  # ... existing fields ...
  data_sovereignty_class: "cross_border_restricted"
  data_sovereignty_source: "Federal Decree-Law No. 45/2021 (PDPL) Art. 22; cross-border transfer requires adequate protection or consent; DIFC and ADGM free zones have separate regimes"

- name: Singapore
  iso_alpha3: SGP
  bis_tier: 2
  # ... existing fields ...
  data_sovereignty_class: "cross_border_restricted"
  data_sovereignty_source: "PDPA 2012 Sec. 26; transfer permitted if recipient jurisdiction has comparable protection or contractual safeguards in place"

- name: Nigeria
  iso_alpha3: NGA
  bis_tier: 2
  # ... existing fields ...
  data_sovereignty_class: "cross_border_restricted"
  data_sovereignty_source: "NDPA 2023 Sec. 43; cross-border transfer requires adequacy assessment by NDPC or consent; implementing regulations still developing"

# === TIER 3 COUNTRIES ===

- name: China
  iso_alpha3: CHN
  bis_tier: 3
  # ... existing fields ...
  data_sovereignty_class: "localization_required"
  data_sovereignty_source: "PIPL Art. 38-40 + CSL Art. 37 + DSL Art. 31; critical/personal data must undergo security assessment for export; CII operators must store data domestically; CAC security assessment required for transfers exceeding volume thresholds"
```

### A4: Classification rationale

The classifications above follow this logic:

| Class | Test | Countries |
|-------|------|-----------|
| `none` | No federal/national law imposes blanket cross-border data transfer restrictions | USA |
| `cross_border_restricted` | Law exists, permits transfer with conditions (consent, adequacy, SCCs) | DEU, JPN, GBR, IND, BRA, ARE, SGP, NGA |
| `localization_required` | Law requires certain data categories to be stored/processed domestically | CHN |
| `transfer_prohibited` | Law prohibits cross-border transfer of covered data categories entirely | (None in current country set — would apply to e.g. Russia for certain data categories) |

**Note:** Most countries fall into `cross_border_restricted`. The key differentiator is how *burdensome* the compliance pathway is — GDPR's SCC mechanism is well-established, while Nigeria's NDPA implementing rules are still developing. The AAR records the regime category, not the compliance difficulty. The paper can discuss this nuance qualitatively.

---

## Part B: Update AAR Builder Logic

### B1: Update `build_aar_records()` in `src/aar.py`

Add sovereignty fields when constructing each record:

```python
record = AARCoreRecord(
    # ... existing fields ...
    data_sovereignty_class=country.get("data_sovereignty_class", "none"),
    data_sovereignty_source=country.get("data_sovereignty_source", ""),
    # ... existing metadata fields ...
)
```

### B2: Interaction with region locality (from README_04)

When a country is routed to a non-local region AND has `data_sovereignty_class != "none"`, the AAR record should flag this as a compounding constraint. Update `routing_notes` to mention it:

In `find_best_region_with_locality()` (or wherever the routing note is constructed), add:

```python
# After determining routing...
if not is_local and country.get("data_sovereignty_class", "none") != "none":
    routing_note += f"; data sovereignty ({country['data_sovereignty_class']}) may further restrict use of non-local region"
```

This makes the interaction between physical routing and data sovereignty visible in the AAR record without changing the ECA computation.

---

## Part C: How Data Sovereignty Interacts with ECA (Future Work)

**For this submission:** Data sovereignty is an AAR-Core descriptive field. It does NOT modify the ECA score. The paper should state this explicitly and explain why:

> "Data sovereignty constraints are workload-dependent: a researcher training on publicly available text faces no transfer restriction, while a researcher using patient health records may face a hard block under the same national law. The AAR records the applicable regime; translating regime to effective constraint requires workload metadata that is outside the scope of AAR-Core."

**For future work (flag in the paper's discussion/limitations section):**

A future version could introduce a workload-type parameter to the ECA computation:

```python
# NOT for this submission — conceptual only
def compute_eca_with_sovereignty(
    record, budget, hours,
    workload_data_type: str = "public",  # "public" | "personal" | "government" | "critical_infrastructure"
):
    if workload_data_type == "public":
        sovereignty_modifier = 1.0  # No constraint
    elif record.data_sovereignty_class == "localization_required" and not record.is_local_region:
        sovereignty_modifier = 0.0  # Cannot use non-local region
    elif record.data_sovereignty_class == "cross_border_restricted" and not record.is_local_region:
        sovereignty_modifier = 0.7  # Usable but with compliance overhead
    # ... etc
```

This is a good Section 6 (Discussion/Future Work) paragraph.

---

## Part D: Tests

Add to `tests/test_aar.py`:

```python
def test_all_countries_have_sovereignty_field(self):
    """Every AAR record should have a data sovereignty classification."""
    records = build_aar_records(
        Path("data/countries.yaml"),
        Path("data/providers.yaml"),
        Path("data/gpus.yaml"),
    )
    valid_classes = {"none", "cross_border_restricted", "localization_required", "transfer_prohibited"}
    for r in records:
        assert r.data_sovereignty_class in valid_classes, (
            f"{r.country_iso}: invalid sovereignty class '{r.data_sovereignty_class}'"
        )
        assert len(r.data_sovereignty_source) > 0, (
            f"{r.country_iso}: missing sovereignty source citation"
        )

def test_china_has_localization_required(self):
    """China should be classified as localization_required due to PIPL/CSL/DSL."""
    records = build_aar_records(
        Path("data/countries.yaml"),
        Path("data/providers.yaml"),
        Path("data/gpus.yaml"),
    )
    chn = [r for r in records if r.country_iso == "CHN"]
    for r in chn:
        assert r.data_sovereignty_class == "localization_required"

def test_usa_has_no_sovereignty_restriction(self):
    """USA should be classified as 'none' (no federal data localization law)."""
    records = build_aar_records(
        Path("data/countries.yaml"),
        Path("data/providers.yaml"),
        Path("data/gpus.yaml"),
    )
    usa = [r for r in records if r.country_iso == "USA"]
    for r in usa:
        assert r.data_sovereignty_class == "none"

def test_sovereignty_compounding_note_for_nigeria(self):
    """Nigeria routed to non-local region with sovereignty restriction should have compounding note."""
    records = build_aar_records(
        Path("data/countries.yaml"),
        Path("data/providers.yaml"),
        Path("data/gpus.yaml"),
    )
    nga = [r for r in records if r.country_iso == "NGA"]
    for r in nga:
        if not r.is_local_region and r.data_sovereignty_class != "none":
            assert "data sovereignty" in r.routing_notes.lower(), (
                f"Nigeria non-local routing should mention data sovereignty constraint"
            )
```

---

## Part E: Visualization Impact

### Compounding gap chart annotation

In `src/visualize.py`, the compounding gap chart should annotate countries that have sovereignty constraints compounding with non-local routing. Add a marker (e.g., a dagger symbol `†`) next to country names where both `is_local_region == False` and `data_sovereignty_class != "none"`:

```python
# In fig_compounding_gap(), when building x-axis labels:
labels = []
for r in filtered:
    name = r["country_name"]
    if not r.get("is_local_region", True) and r.get("data_sovereignty_class", "none") != "none":
        name += " †"
    labels.append(name)

# Add footnote:
ax.text(0.02, -0.15,
    "† Non-local cloud region + cross-border data transfer restrictions apply",
    transform=ax.transAxes, fontsize=8, color="gray", style="italic")
```

### Sensitivity heatmap

No change needed — sovereignty is not part of the ECA score in this version, so it doesn't affect rankings.

---

## Part F: Paper Implications

This field gives you a new paragraph in the paper's contribution section. Suggested framing:

> "AAR-Core includes a data sovereignty classifier that records the most restrictive cross-border data transfer constraint applicable in the researcher's jurisdiction. This field is derived from publicly available statutory text (e.g., GDPR Art. 46–49, India DPDP Act 2023 Sec. 16, China PIPL Art. 38–40) and captures a constraint dimension that existing compute access measurements do not address. While export controls restrict chip supply, data sovereignty restricts the demand side: whether a researcher can legally transfer their data to the available compute region. These constraints are orthogonal — a Tier 1 country with no chip restrictions may nonetheless face binding data transfer restrictions that limit which cloud regions are usable for sensitive workloads."

This also strengthens your Nigeria case study: Nigeria faces all four constraint layers simultaneously (no local region, low purchasing power, Tier 2 chip cap, AND cross-border data transfer restrictions for the fallback region).
