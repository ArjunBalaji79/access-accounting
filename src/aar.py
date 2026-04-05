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

    # Economic layer
    on_demand_usd_per_gpu_hr: float
    reserved_usd_per_gpu_hr: Optional[float]
    spot_usd_per_gpu_hr: Optional[float]
    ppp_factor: float
    gdp_per_capita_usd: float
    rd_spend_per_researcher_usd: Optional[float]

    # Legal layer
    bis_tier: int  # 1, 2, or 3
    tpp_cap: Optional[int]

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


def load_yaml(path: Path) -> list[dict]:
    with open(path) as f:
        return yaml.safe_load(f)


def find_best_region(
    provider_entry: dict,
    country_iso: str,
) -> Optional[dict]:
    """Find the best region for a country from a provider's region list.
    
    Priority: (1) region IN the country, (2) any GA region, (3) any region.
    Returns the region dict or None if no regions exist.
    """
    regions = provider_entry.get("regions", [])
    
    # First: exact country match
    for r in regions:
        if r["region_country_iso"] == country_iso:
            return r

    # Second: any GA region (fallback for countries without local region)
    ga_regions = [r for r in regions if r["availability_class"] == "GA"]
    if ga_regions:
        return ga_regions[0]

    # Third: any region at all
    if regions:
        return regions[0]

    return None


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

            region = find_best_region(prov_entry, country["iso_alpha3"])
            if region is None:
                continue

            avail_class = region["availability_class"]

            # For Tier 3 / prohibited countries, override availability
            if country["bis_tier"] == 3:
                avail_class = "Unavailable"

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
                on_demand_usd_per_gpu_hr=region["on_demand_usd_per_gpu_hr"],
                reserved_usd_per_gpu_hr=region.get("reserved_usd_per_gpu_hr"),
                spot_usd_per_gpu_hr=region.get("spot_usd_per_gpu_hr"),
                ppp_factor=country["ppp_factor"],
                gdp_per_capita_usd=country["gdp_per_capita_usd"],
                rd_spend_per_researcher_usd=country.get("rd_spend_per_researcher_usd"),
                bis_tier=country["bis_tier"],
                tpp_cap=country.get("tpp_cap"),
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
