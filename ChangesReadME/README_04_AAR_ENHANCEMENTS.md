# README_04: AAR Enhancements — Region Locality & Routing

## Priority: MEDIUM
## What this does: Adds region locality tracking and improves Nigeria/Sub-Saharan Africa handling
## Depends on: README_01 (verified data)

---

## Problem: Nigeria's Non-Local Routing is Invisible

### Current state:
Nigeria has no AWS region in Sub-Saharan Africa. The `find_best_region()` function in `aar.py` silently falls back to `eu-west-1` (Ireland) — the closest GA region. The resulting AAR record looks the same as if Nigeria had a local region.

This masks a physical access constraint that the paper explicitly discusses: latency, data sovereignty, and infrastructure gaps for countries without local cloud regions.

### Fix: Add locality fields to AARCoreRecord

**Add these fields to the `AARCoreRecord` dataclass in `src/aar.py`:**

```python
@dataclass
class AARCoreRecord:
    # ... existing fields ...

    # Physical layer — NEW FIELDS
    is_local_region: bool  # True if the region is IN the country, False if routed elsewhere
    routing_country_iso: str  # ISO3 of the country where the region actually is
    routing_notes: str  # Human-readable note about the routing (empty if local)
```

### Changes to `find_best_region()`:

Rename to `find_best_region_with_locality()` and return locality info:

```python
def find_best_region_with_locality(
    provider_entry: dict,
    country_iso: str,
) -> Optional[tuple[dict, bool, str, str]]:
    """Find the best region for a country. Returns (region_dict, is_local, routing_iso, routing_notes)."""
    regions = provider_entry.get("regions", [])

    # First: exact country match
    for r in regions:
        if r["region_country_iso"] == country_iso:
            return r, True, country_iso, ""

    # Second: any GA region (fallback for countries without local region)
    ga_regions = [r for r in regions if r["availability_class"] == "GA"]
    if ga_regions:
        fallback = ga_regions[0]
        routing_iso = fallback["region_country_iso"]
        note = f"No local {provider_entry['provider'].upper()} region; routed to {fallback['region_code']} ({routing_iso})"
        return fallback, False, routing_iso, note

    # Third: any region at all
    if regions:
        fallback = regions[0]
        routing_iso = fallback["region_country_iso"]
        note = f"No local or GA region; routed to {fallback['region_code']} ({routing_iso})"
        return fallback, False, routing_iso, note

    return None
```

### Update `build_aar_records()`:

```python
result = find_best_region_with_locality(prov_entry, country["iso_alpha3"])
if result is None:
    continue
region, is_local, routing_iso, routing_note = result

# ... existing record building ...
record = AARCoreRecord(
    # ... existing fields ...
    is_local_region=is_local,
    routing_country_iso=routing_iso,
    routing_notes=routing_note,
)
```

---

## Country-to-Region Mapping Reference

For the current 10 countries, the expected mappings are:

| Country | AWS Local Region? | Closest AWS Region | routing_notes |
|---------|-------------------|-------------------|---------------|
| USA | ✅ Yes | us-east-1 (N. Virginia) | |
| Germany | ✅ Yes | eu-central-1 (Frankfurt) | |
| Japan | ✅ Yes | ap-northeast-1 (Tokyo) | |
| UK | ✅ Yes | eu-west-2 (London) | |
| India | ✅ Yes | ap-south-1 (Mumbai) | |
| Brazil | ✅ Yes | sa-east-1 (São Paulo) | |
| UAE | ❌ No | me-south-1 (Bahrain) | "No local AWS region; routed to me-south-1 (BHR)" |
| Singapore | ✅ Yes | ap-southeast-1 | |
| Nigeria | ❌ No | eu-west-1 (Ireland) | "No local AWS region; routed to eu-west-1 (IRL)" |
| China | ❌ No (blocked) | N/A — Tier 3 | "Tier 3: export prohibited" |

**Note:** UAE routes to Bahrain (me-south-1), which is very close geographically but still not "in-country." This is a meaningful distinction for data sovereignty purposes. The code should detect this correctly.

---

## Impact on Downstream Code

### ECA computation:
The `is_local_region` field could optionally feed into a latency penalty modifier in future versions. For now, it's purely informational — the ECA computation does not change. But having the field in the AAR record makes the physical access constraint visible in the data.

### Visualization:
The compounding gap chart could use a marker (asterisk, different shade) for countries routed to non-local regions, highlighting the physical infrastructure gap.

Add to `fig_compounding_gap()`:
```python
# After drawing bars, add locality markers
for i, r in enumerate(filtered):
    if not r.get("is_local_region", True):
        ax.annotate("*", xy=(i, 5), fontsize=14, ha="center", color="gray")

# Add footnote
ax.text(0.02, -0.12, "* No local cloud region — routed to nearest available region",
        transform=ax.transAxes, fontsize=8, color="gray")
```

### CSV output:
The new fields should appear in the AAR CSV output. Update `records_to_csv()` — no code change needed if using `dataclass.fields()`, since the new fields are already part of the dataclass.

---

## Tests to Add

```python
def test_nigeria_routes_to_ireland(self):
    """Nigeria should be flagged as non-local, routing to Ireland."""
    # Build records and check Nigeria's AAR
    records = build_aar_records(
        Path("data/countries.yaml"),
        Path("data/providers.yaml"),
        Path("data/gpus.yaml"),
    )
    nga_aws_h100 = [r for r in records
                     if r.country_iso == "NGA" and r.provider == "aws" and r.gpu_class == "H100_SXM5"]
    assert len(nga_aws_h100) >= 1
    r = nga_aws_h100[0]
    assert r.is_local_region == False
    assert r.routing_country_iso in ("IRL", "GBR")  # Ireland or UK fallback
    assert len(r.routing_notes) > 0

def test_usa_is_local(self):
    """USA should always have a local region."""
    records = build_aar_records(...)
    usa_records = [r for r in records if r.country_iso == "USA"]
    for r in usa_records:
        assert r.is_local_region == True
        assert r.routing_notes == ""
```
