import time

import pytest

from app import extract as extract_module
from app.extract import cache_key, extract, extract_many, rule_candidates
from app.extraction_providers import ProviderError
from app.gazetteer import landmark_for, road_for
from app.schemas import IncomingReport


class FakeProvider:
    """Records calls and returns controlled JSON, like a recorded provider fixture."""

    name = "fake"

    def __init__(self, response=None, error=None, delay=0.0, model="fake-model-1"):
        self.response, self.error, self.delay, self.model = response, error, delay, model
        self.calls = 0

    def available(self):
        return True

    def extract(self, request):
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        return self.response(request) if callable(self.response) else dict(self.response)


def llm_json(**overrides):
    base = {"category": None, "category_confidence": 0.9, "locality": None, "road": None, "landmark": None, "duration_hours": None,
            "households": None, "road_blocked": False, "health_risk": False, "near_school_or_hospital": False, "in_scope": True, "severity": 2}
    base.update(overrides)
    return base


def _unique(text: str) -> str:
    # The cache is keyed by text; unique text keeps tests independent of each other.
    return f"{text} [{time.perf_counter_ns()}]"


# --- Rules-only extraction -------------------------------------------------------------------
@pytest.mark.parametrize("text, category, geo, locality", [
    ("Caller reports sewage overflowing near Kukatpally Government School, Road No. 5.", "overflow", "exact", "Kukatpally"),
    ("@HMWSSB drain overflowing outside my house at Rd No 5 in Kukatpalli! #Hyderabad", "overflow", "road", "Kukatpally"),
    ("Neighbours pls note: open manhole opposite Miyapur Zilla Parishad School. School kids pass here every day.", "manhole", "exact", "Miyapur"),
    ("Residents complain of sewage flooding the road in Uppal area.", "road_flooding", "locality", "Uppal"),
    ("Grievance: sewer pipeline burst. Location: Station Road, Secunderabad.", "damaged_pipeline", "road", "Secunderabad"),
    ("Field note: storm drain choked on Film Nagar Road, Jubilee Hills.", "drain_blockage", "road", "Jubilee Hills"),
    ("Colony group: unbearable sewage smell in Madhapur.", "foul_smell", "locality", "Madhapur"),
    ("Sharing location — sewage entering houses near Rambagh Colony Park.", "sewage_in_house", "exact", "Attapur"),
    ("Sewage overflowing near my house, please help.", "overflow", "none", None),
])
def test_rule_extraction_table(text, category, geo, locality):
    result = extract(_unique(text), provider=None)
    assert result.category == category
    assert result.geo_quality == geo
    assert result.locality == locality
    assert result.extraction_mode == "rules_fallback"
    if geo != "none":
        assert result.lat is not None and result.lon is not None
    else:
        assert result.lat is None


def test_blocked_road_is_not_a_blockage_category():
    result = extract(_unique("Tagging @HMWSSB — sewage overflowing on Lalapet Road, Tarnaka. Road is blocked."), provider=None)
    assert result.category == "overflow" and result.road_blocked


@pytest.mark.parametrize("text", [
    "Garbage pickup has not happened for three days near Ameerpet Vegetable Market.",
    "@HMWSSB water pressure is very low in KPHB today, tanks not filling.",
    "Congratulations! Win a free phone now, click this link to claim your prize.",
    "Streetlight not working near LB Nagar Metro Station for a week.",
])
def test_out_of_scope(text):
    result = extract(_unique(text), provider=None)
    assert not result.in_scope and result.category is None


def test_explicit_values_and_flags():
    result = extract(_unique("Portal complaint — sewer overflow on Road No. 5, Kukatpally. About 36 houses affected. Going on for 18 hours. Kids falling sick. Vehicles cannot pass."), provider=None)
    assert result.households == 36
    assert result.duration_hours == 18
    assert result.health_risk and result.road_blocked
    assert result.severity >= 4


def test_open_manhole_beside_school_is_severe_and_sensitive():
    result = extract(_unique("Open manhole right next to the school gate on Hafeezpet Road, Miyapur."), provider=None)
    assert result.category == "manhole" and result.severity == 5 and result.near_sensitive == "school"


def test_landmark_only_report_resolves_locality_and_road():
    result = extract(_unique("Manhole overflowing opposite Kukatpally Government School"), provider=None)
    landmark = landmark_for("Kukatpally Government School")
    assert (result.locality, result.road, result.geo_quality) == ("Kukatpally", "Road No. 5", "exact")
    assert (result.lat, result.lon) == (landmark.lat, landmark.lon)


def test_rule_candidates_expose_explicit_claims():
    rules = rule_candidates("Sewer overflow near Kukatpally Government School, 15 houses affected, road blocked")
    assert rules.candidates.locality_candidates == ["Kukatpally"]
    assert rules.candidates.landmark_candidates == ["Kukatpally Government School"]
    assert rules.candidates.explicit_claims["households"] == 15


# --- Device pins ------------------------------------------------------------------------------
def test_device_pin_refines_road_location():
    road = road_for("Kukatpally", "Road No. 5")
    pin = (road.start[0] + 0.0001, road.start[1] + 0.0001)
    result = extract(_unique("Sewer overflow on Road No. 5, Kukatpally"), gps=pin, provider=None)
    assert result.geo_quality == "exact" and (result.lat, result.lon) == pin


def test_far_device_pin_is_ignored():
    result = extract(_unique("Sewer overflow on Road No. 5, Kukatpally"), gps=(17.36, 78.47), provider=None)
    assert result.geo_quality == "road"
    assert any("pin ignored" in note for note in result.reconciliation_notes)


# --- Hybrid path with provider fixtures -------------------------------------------------------
def test_valid_llm_materially_enriches_ambiguous_report():
    text = _unique("Gutter water spreading everywhere near Botanical Garden Gate, cannot walk")
    rules_only = extract(text, provider=None)
    assert not rules_only.in_scope  # rules alone do not recognise 'gutter water'
    provider = FakeProvider(llm_json(category="road_flooding", in_scope=True, severity=3, road_blocked=True))
    result = extract(text, provider=provider)
    assert result.extraction_mode == "hybrid_validated" and result.provider == "fake"
    assert result.in_scope and result.category == "road_flooding" and result.road_blocked
    assert result.field_provenance["in_scope"] == "llm"
    assert (result.locality, result.geo_quality) == ("Kondapur", "exact")  # coordinates from gazetteer


def test_llm_selects_valid_candidate_for_typo():
    text = _unique("sewage overflowing near kondapur area hospitl gate")
    provider = FakeProvider(llm_json(category="overflow", locality="Kondapur", landmark="Kondapur Area Hospital", severity=3))
    result = extract(text, provider=provider)
    assert result.landmark == "Kondapur Area Hospital" and result.geo_quality == "exact"


def test_invented_locality_is_rejected():
    text = _unique("Sewage overflowing on Road No. 5, Kukatpally")
    provider = FakeProvider(llm_json(category="overflow", locality="Atlantis", severity=3))
    result = extract(text, provider=provider)
    assert result.locality == "Kukatpally"
    assert any("Atlantis" in note for note in result.reconciliation_notes)


def test_llm_coordinates_fail_strict_validation_and_fall_back():
    text = _unique("Sewage overflowing on Road No. 5, Kukatpally")
    provider = FakeProvider(llm_json(category="overflow", lat=17.1, lon=78.1))
    result = extract(text, provider=provider)
    assert result.extraction_mode == "rules_fallback"
    assert "schema validation failed" in result.fallback_reason
    assert result.road == "Road No. 5"


def test_malformed_or_unavailable_provider_falls_back():
    text = _unique("Drain blockage near the culvert on Film Nagar Road, Jubilee Hills")
    result = extract(text, provider=FakeProvider(error=ProviderError("invalid JSON")))
    assert result.extraction_mode == "rules_fallback" and result.fallback_reason == "invalid JSON"
    assert result.category == "drain_blockage"


def test_explicit_number_beats_llm_number():
    text = _unique("Sewer overflow on Station Road, Secunderabad, 15 houses affected")
    result = extract(text, provider=FakeProvider(llm_json(category="overflow", households=40, severity=3)))
    assert result.households == 15
    assert any("households" in note for note in result.reconciliation_notes)


def test_llm_cannot_manufacture_numbers():
    text = _unique("Sewer overflow on Station Road, Secunderabad, many families affected")
    result = extract(text, provider=FakeProvider(llm_json(category="overflow", households=30, severity=3)))
    assert result.households is None


def test_open_manhole_survives_llm_reinterpretation():
    text = _unique("Open manhole beside Miyapur Zilla Parishad School, water overflowing")
    result = extract(text, provider=FakeProvider(llm_json(category="overflow", severity=3)))
    assert result.category == "manhole" and result.severity == 5 and result.near_sensitive == "school"


def test_cache_is_reused_and_keyed_by_model_and_schema():
    text = _unique("Sewer overflow on Road No. 5, Kukatpally")
    provider = FakeProvider(llm_json(category="overflow", severity=3))
    extract(text, provider=provider)
    extract(text, provider=provider)
    assert provider.calls == 1
    other_model = FakeProvider(llm_json(category="overflow", severity=3), model="fake-model-2")
    extract(text, provider=other_model)
    assert other_model.calls == 1
    assert cache_key(text, "phone", "fake", "a") != cache_key(text, "phone", "fake", "b")
    assert cache_key(text, "phone", "fake", "a") != cache_key(text, "social", "fake", "a")


def test_slow_provider_is_bounded_by_batch_deadline(monkeypatch):
    monkeypatch.setattr(extract_module, "LLM_BATCH_DEADLINE_SECONDS", 0.2)
    reports = [IncomingReport(id=f"r{index}", source="phone", source_handle=f"phone_test_{index:03d}", raw_text=_unique("Sewer overflow on Road No. 5, Kukatpally"), created_at="2026-09-29T10:00:00+00:00") for index in range(3)]
    started = time.monotonic()
    results, stats = extract_many(reports, provider=FakeProvider(llm_json(category="overflow", severity=3), delay=1.0))
    assert time.monotonic() - started < 0.9
    assert all(result.extraction_mode == "rules_fallback" for result in results.values())
    assert stats.reasons == {"batch latency budget exceeded": 3}


def test_no_key_mode_reports_provenance():
    result = extract(_unique("Sewer overflow on Road No. 5, Kukatpally"))  # default provider, no key in tests
    assert result.extraction_mode == "rules_fallback"
    assert result.fallback_reason in {"no provider credentials configured", "extraction mode is rules-only"}
