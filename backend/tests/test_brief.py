import json
import re

from app.brief import build_fact_payload, template_brief


def _numbers(text):
    return set(re.findall(r"\d+", text))


def test_template_uses_only_supplied_numbers(demo_db):
    conn, _, batch = demo_db
    for incident_id in [batch["hero_incident_id"], *batch["new_incident_ids"][:5]]:
        facts = build_fact_payload(conn, incident_id)
        brief = template_brief(facts)
        produced = _numbers(" ".join(brief["facts"] + brief["assessment"] + [brief["recommended_next_step"]]))
        assert produced <= _numbers(json.dumps(facts, ensure_ascii=False))
        assert brief["recommended_next_step"].startswith("AI suggestion:")
        assert any("not yet confirmed" in line for line in brief["assessment"])
        assert not any(word in " ".join(brief["facts"]).lower() for word in ("estimate", "est.", "likely"))
