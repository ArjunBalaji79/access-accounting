"""
Access Availability Record (AAR) builder.

Constructs AAR-Core records from country, provider, and GPU config files.
Each record represents one (country, provider, region, GPU) tuple.
"""

import argparse
import csv
import itertools
from dataclasses import dataclass, asdict, fields
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class AARCoreRecord:
    """One AAR-Core record: a single (country, provider, GPU, region) tuple."""

    # Identifiers
    country_name: str
    country_iso: str
    provider: str
    region_code: str
    gpu_class: str

    # Physical layer
    gpu_full_name: str
    peak_tflops_bf16_dense: float
    availability_class: str  # GA / Limited / Waitlisted / Unavailable
    availability_score: float  # GA=1.0, Limited=0.5, Waitlisted=0.1, Unavailable=0.0
    # Region locality (README_04): exposes when a country has no local cloud
    # region and is routed to the nearest available one (e.g. NGA → eu-west-1).
    is_local_region: bool
    routing_country_iso: str
    routing_notes: str

    # Economic layer
    on_demand_usd_per_gpu_hr: float
    reserved_usd_per_gpu_hr: Optional[float]
    spot_usd_per_gpu_hr: Optional[float]
    ppp_factor: float
    gdp_per_capita_usd: float
    rd_spend_per_researcher_usd: Optional[float]

    # Legal layer — chip export controls
    bis_tier: int  # 1, 2, or 3
    tpp_cap: Optional[int]

    # Legal layer — data sovereignty (README_06)
    # Records the most restrictive cross-border data-transfer regime that
    # applies in the researcher's jurisdiction. This is ORTHOGONAL to BIS
    # tier (which restricts chip supply): sovereignty restricts whether the
    # researcher may legally send their data to the cloud region that is
    # physically available. It is recorded here but intentionally NOT
    # folded into the ECA score, because whether it binds depends on the
    # workload's data type (public text vs. personal/government data),
    # which is outside AAR-Core's scope.
    data_sovereignty_class: str  # none / cross_border_restricted / localization_required / transfer_prohibited
    data_sovereignty_source: str  # statute / regulation citation

    # Metadata
    pricing_url: str
    pricing_retrieval_date: str
    data_source_type: str = "Provider public page + World Bank ICP + BIS regulatory text"
    verification_status: str = "Self-reported"


AVAILABILITY_SCORES = {
    "GA": 1.0,
    "Limited": 0.5,
    "Waitlisted": 0.1,
    "Unavailable": 0.0,
}

# Data-sovereignty suggestive weights. These are NOT used in the ECA
# computation (see docstring on AARCoreRecord); they are kept here for
# descriptive analysis and potential future work that introduces a
# workload-type parameter. Ordering: higher = less restrictive.
SOVEREIGNTY_SCORES = {
    "none": 1.0,
    "cross_border_restricted": 0.7,
    "localization_required": 0.2,
    "transfer_prohibited": 0.0,
}

VALID_SOVEREIGNTY_CLASSES = set(SOVEREIGNTY_SCORES.keys())


def load_yaml(path: Path) -> list[dict]:
    with open(path) as f:
        return yaml.safe_load(f)


def find_best_region_with_locality(
    provider_entry: dict,
    country_iso: str,
) -> Optional[tuple[dict, bool, str, str]]:
    """Find the best region for a country, preserving locality information.

    Priority: (1) region IN the country, (2) any GA region, (3) any region.
    Returns a tuple ``(region_dict, is_local, routing_country_iso, routing_notes)``
    or ``None`` if no regions exist.
    """
    regions = provider_entry.get("regions", [])
    provider_name = provider_entry.get("provider", "provider").upper()

    for r in regions:
        if r["region_country_iso"] == country_iso:
            return r, True, country_iso, ""

    ga_regions = [r for r in regions if r["availability_class"] == "GA"]
    if ga_regions:
        fallback = ga_regions[0]
        routing_iso = fallback["region_country_iso"]
        note = (
            f"No local {provider_name} region; routed to "
            f"{fallback['region_code']} ({routing_iso})"
        )
        return fallback, False, routing_iso, note

    if regions:
        fallback = regions[0]
        routing_iso = fallback["region_country_iso"]
        note = (
            f"No local or GA region; routed to "
            f"{fallback['region_code']} ({routing_iso})"
        )
        return fallback, False, routing_iso, note

    return None


def find_best_region(provider_entry: dict, country_iso: str) -> Optional[dict]:
    """Backwards-compatible wrapper that returns only the region dict."""
    result = find_best_region_with_locality(provider_entry, country_iso)
    return result[0] if result is not None else None


def build_aar_records(
    countries_path: Path,
    providers_path: Path,
    gpus_path: Path,
) -> list[AARCoreRecord]:
    """Build AAR-Core records for all (country, provider-GPU) combinations."""

    countries = load_yaml(countries_path)
    providers = load_yaml(providers_path)
    gpus_list = load_yaml(gpus_path)

    # Index GPUs by name
    gpus = {g["name"]: g for g in gpus_list}

    records = []

    for country in countries:
        for prov_entry in providers:
            gpu_name = prov_entry["gpu_class"]
            gpu = gpus.get(gpu_name)
            if gpu is None:
                continue

            result = find_best_region_with_locality(prov_entry, country["iso_alpha3"])
            if result is None:
                continue
            region, is_local, routing_iso, routing_note = result

            avail_class = region["availability_class"]
            sovereignty_class = country.get("data_sovereignty_class", "none")
            sovereignty_source = country.get("data_sovereignty_source", "")
            if sovereignty_class not in VALID_SOVEREIGNTY_CLASSES:
                raise ValueError(
                    f"{country['iso_alpha3']}: invalid data_sovereignty_class "
                    f"'{sovereignty_class}' (expected one of {sorted(VALID_SOVEREIGNTY_CLASSES)})"
                )

            # Tier 3 / prohibited countries: override availability and attach a
            # regulatory routing note so the AAR CSV shows the legal block.
            if country["bis_tier"] == 3:
                avail_class = "Unavailable"
                routing_note = "Tier 3: export prohibited"
                is_local = False
            elif not is_local and sovereignty_class != "none":
                # Compounding constraint: non-local routing + data transfer law
                # — flag in the routing note so the AAR CSV makes the
                # interaction visible without changing any scores.
                routing_note += (
                    f"; data sovereignty ({sovereignty_class}) may further "
                    f"restrict use of non-local region"
                )

            record = AARCoreRecord(
                country_name=country["name"],
                country_iso=country["iso_alpha3"],
                provider=prov_entry["provider"],
                region_code=region["region_code"],
                gpu_class=gpu_name,
                gpu_full_name=gpu["full_name"],
                peak_tflops_bf16_dense=gpu["peak_tflops_bf16_dense"],
                availability_class=avail_class,
                availability_score=AVAILABILITY_SCORES.get(avail_class, 0.0),
                is_local_region=is_local,
                routing_country_iso=routing_iso,
                routing_notes=routing_note,
                on_demand_usd_per_gpu_hr=region["on_demand_usd_per_gpu_hr"],
                reserved_usd_per_gpu_hr=region.get("reserved_usd_per_gpu_hr"),
                spot_usd_per_gpu_hr=region.get("spot_usd_per_gpu_hr"),
                ppp_factor=country["ppp_factor"],
                gdp_per_capita_usd=country["gdp_per_capita_usd"],
                rd_spend_per_researcher_usd=country.get("rd_spend_per_researcher_usd"),
                bis_tier=country["bis_tier"],
                tpp_cap=country.get("tpp_cap"),
                data_sovereignty_class=sovereignty_class,
                data_sovereignty_source=sovereignty_source,
                pricing_url=prov_entry["pricing_url"],
                pricing_retrieval_date=prov_entry["pricing_retrieval_date"],
            )
            records.append(record)

    return records


def records_to_csv(records: list[AARCoreRecord], output_path: Path) -> None:
    """Write AAR records to CSV."""
    if not records:
        return
    fieldnames = [f.name for f in fields(AARCoreRecord)]
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            writer.writerow(asdict(r))


def main():
    parser = argparse.ArgumentParser(description="Build AAR-Core records")
    parser.add_argument("--config", type=Path, default=Path("data/"),
                        help="Directory containing countries.yaml, providers.yaml, gpus.yaml")
    parser.add_argument("--output", type=Path, default=Path("outputs/tables/aar_records.csv"))
    parser.add_argument("--format", choices=["csv", "latex"], default="csv")
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)

    records = build_aar_records(
        args.config / "countries.yaml",
        args.config / "providers.yaml",
        args.config / "gpus.yaml",
    )

    print(f"Built {len(records)} AAR-Core records")
    print(f"Countries: {len(set(r.country_iso for r in records))}")
    print(f"Providers: {len(set(r.provider for r in records))}")
    print(f"GPU classes: {len(set(r.gpu_class for r in records))}")

    records_to_csv(records, args.output)
    print(f"Written to {args.output}")


if __name__ == "__main__":
    main()
