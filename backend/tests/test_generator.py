import re
from collections import Counter
from datetime import datetime

from app.generator import OUT_OF_SCOPE, SOURCE_TEMPLATES, generate_baseline, generate_batch
from app.schemas import IncomingReport
from conftest import FIXED_NOW


def _by_truth(batch):
    groups = {}
    for item in batch:
        groups.setdefault(item.truth_incident, []).append(item.report)
    return groups


def test_batch_is_deterministic():
    first = generate_batch(100, now=FIXED_NOW)
    second = generate_batch(100, now=FIXED_NOW)
    assert [(item.report.model_dump(), item.truth_incident) for item in first] == [(item.report.model_dump(), item.truth_incident) for item in second]


def test_different_seed_changes_wording_not_composition():
    first, second = generate_batch(100, now=FIXED_NOW), generate_batch(100, now=FIXED_NOW, seed=43)
    assert [item.report.raw_text for item in first] != [item.report.raw_text for item in second]
    assert Counter(item.truth_incident for item in first) == Counter(item.truth_incident for item in second)


def test_batch_composition():
    batch = generate_batch(100, now=FIXED_NOW)
    groups = _by_truth(batch)
    assert len(batch) == 100
    in_scope = [item for item in batch if not item.truth_incident.startswith("OUT-")]
    assert len(in_scope) == 96
    assert len({item.truth_incident for item in in_scope}) == 17
    assert sum(1 for key in groups if key.startswith("OUT-")) == len(OUT_OF_SCOPE) == 4


def test_hero_properties():
    hero = _by_truth(generate_batch(100, now=FIXED_NOW))["TRUTH-HERO"]
    assert len(hero) == 47
    assert len({report.source_handle for report in hero}) >= 31
    times = sorted(datetime.fromisoformat(report.created_at) for report in hero)
    assert 16 <= (times[-1] - times[0]).total_seconds() / 3600 <= 19
    # Near-exact reposts from the same handle.
    texts = Counter((report.source_handle, report.raw_text.replace(" Please act!", "")) for report in hero)
    assert sum(count - 1 for count in texts.values()) == 8


def test_special_cases():
    groups = _by_truth(generate_batch(100, now=FIXED_NOW))
    danger = groups["TRUTH-DANGER"]
    assert len(danger) == 3 and all("manhole" in report.raw_text.lower() for report in danger)
    inflated = groups["TRUTH-INFLATED"]
    assert len(inflated) >= 8 and len({report.source_handle for report in inflated}) == 1


def test_template_variety_per_source():
    # 6 structures x >=6 issue phrases per category x 4+ location forms: far above 30 per source.
    for source, templates in SOURCE_TEMPLATES.items():
        assert len(templates) * 6 * 4 >= 30, source
    texts = Counter(item.report.source for item in generate_baseline(300, now=FIXED_NOW))
    assert set(texts) == set(SOURCE_TEMPLATES)


def test_handles_are_synthetic_and_no_pii():
    for item in generate_batch(100, now=FIXED_NOW) + generate_baseline(300, now=FIXED_NOW):
        assert re.fullmatch(r"(phone|social|whatsapp|news|official|field)_[a-z]+_\d{3}", item.report.source_handle)
        assert not re.search(r"\d{10}", item.report.raw_text)


def test_pipeline_input_type_has_no_truth_field():
    assert "truth_incident" not in IncomingReport.model_fields


def test_baseline_size_and_determinism():
    first = generate_baseline(300, now=FIXED_NOW)
    assert len(first) == 300
    assert [item.report.id for item in first] == [item.report.id for item in generate_baseline(300, now=FIXED_NOW)]
