"""Tests for AAR record building."""

from pathlib import Path

import pytest

from src.aar import AVAILABILITY_SCORES, SOVEREIGNTY_SCORES, build_aar_records

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def records() -> list:
    return build_aar_records(
        DATA_DIR / "countries.yaml",
        DATA_DIR / "providers.yaml",
        DATA_DIR / "gpus.yaml",
    )


class TestAARBuilder:

    def test_builds_plausible_record_count(self, records):
        """10 countries × (2 providers × 2 GPUs) = up to 40 records."""
        assert 30 <= len(records) <= 60

    def test_tier3_override_to_unavailable(self, records):
        chn = [r for r in records if r.country_iso == "CHN"]
        assert chn, "Expected CHN records"
        for r in chn:
            assert r.availability_class == "Unavailable"
            assert r.availability_score == 0.0

    def test_all_records_have_required_fields(self, records):
        for r in records:
            assert r.country_name
            assert r.country_iso
            assert r.provider
            assert r.gpu_class
            assert r.peak_tflops_bf16_dense > 0
            assert r.on_demand_usd_per_gpu_hr > 0
            assert r.ppp_factor > 0
            assert r.bis_tier in (1, 2, 3)

    def test_availability_scores_match_classes(self, records):
        for r in records:
            expected = AVAILABILITY_SCORES.get(r.availability_class, 0.0)
            assert r.availability_score == expected, (
                f"{r.country_iso}/{r.provider}/{r.gpu_class}: "
                f"class={r.availability_class} but score={r.availability_score}"
            )

    def test_nigeria_not_local(self, records):
        """Nigeria has no local AWS region; should be flagged as non-local."""
        nga = [r for r in records if r.country_iso == "NGA"]
        assert nga
        for r in nga:
            assert r.is_local_region is False
            assert r.routing_notes  # non-empty human-readable note

    def test_usa_always_local(self, records):
        usa = [r for r in records if r.country_iso == "USA"]
        assert usa
        for r in usa:
            assert r.is_local_region is True
            assert r.routing_country_iso == "USA"
            assert r.routing_notes == ""

    def test_china_routing_note_reflects_tier3(self, records):
        chn = [r for r in records if r.country_iso == "CHN"]
        assert chn
        for r in chn:
            assert "Tier 3" in r.routing_notes

    def test_tflops_values_match_dense_convention(self, records):
        """H100 should use 989.5 (dense), A100 should use 312.0."""
        for r in records:
            if r.gpu_class == "H100_SXM5":
                assert r.peak_tflops_bf16_dense == pytest.approx(989.5)
            elif r.gpu_class == "A100_SXM4":
                assert r.peak_tflops_bf16_dense == pytest.approx(312.0)


class TestDataSovereignty:
    """Tests for the data sovereignty field introduced by README_06."""

    def test_all_countries_have_sovereignty_field(self, records):
        """Every AAR record should have a valid sovereignty class + citation."""
        valid = set(SOVEREIGNTY_SCORES.keys())
        for r in records:
            assert r.data_sovereignty_class in valid, (
                f"{r.country_iso}: invalid sovereignty class "
                f"'{r.data_sovereignty_class}'"
            )
            assert r.data_sovereignty_source, (
                f"{r.country_iso}: missing data_sovereignty_source citation"
            )

    def test_china_has_localization_required(self, records):
        """China (PIPL / CSL / DSL) should be 'localization_required'."""
        chn = [r for r in records if r.country_iso == "CHN"]
        assert chn, "Expected CHN records"
        for r in chn:
            assert r.data_sovereignty_class == "localization_required"
            assert "PIPL" in r.data_sovereignty_source

    def test_usa_has_no_sovereignty_restriction(self, records):
        """USA has no federal data localization law → 'none'."""
        usa = [r for r in records if r.country_iso == "USA"]
        assert usa
        for r in usa:
            assert r.data_sovereignty_class == "none"

    def test_sovereignty_compounding_note_for_nigeria(self, records):
        """Nigeria routes to a non-local region AND has a sovereignty regime,
        so the routing_notes should mention the compounding data-sovereignty
        constraint (README_06 §B2)."""
        nga = [r for r in records if r.country_iso == "NGA"]
        assert nga
        for r in nga:
            if not r.is_local_region and r.data_sovereignty_class != "none":
                assert "data sovereignty" in r.routing_notes.lower(), (
                    f"Nigeria non-local routing should mention data sovereignty "
                    f"— got routing_notes={r.routing_notes!r}"
                )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
