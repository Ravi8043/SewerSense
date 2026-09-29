"""Response brief: a strict fact payload, an optional validated LLM rewrite, and a deterministic
template fallback. Reported facts and AI assessment are kept in separate lists."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from pydantic import ValidationError

from .config import LLM_MAX_OUTPUT_TOKENS, LLM_MODEL, LLM_TIMEOUT_SECONDS, llm_api_key
from .db import load_json, rows_to_dicts
from .pipeline import band_for, confidence_label
from .schemas import LLMBrief

try:
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None  # type: ignore[assignment]

IST = timezone(timedelta(hours=5, minutes=30))
SUGGESTION_PREFIX = "AI suggestion: "
BRIEF_SYSTEM_PROMPT = (
    "You write short operational briefs for a sewerage control room from a JSON fact payload. "
    "Use only the supplied facts. Do not invent numbers, people, causes, or actions claimed as completed. "
    "'facts' may only restate what reports say or counts in the payload. 'assessment' holds estimates and "
    "interpretation and must label estimates as estimates. 'recommended_next_step' is a single verification-first "
    "suggestion that starts with 'AI suggestion:'. Every number you write must appear in the payload."
)


class BriefNotFound(Exception):
    pass


def _fmt_time(value: str) -> str:
    return datetime.fromisoformat(value).astimezone(IST).strftime("%d %b %Y, %H:%M IST")


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def build_fact_payload(conn: sqlite3.Connection, incident_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
    if row is None:
        raise BriefNotFound(incident_id)
    incident = dict(row)
    reports = rows_to_dicts(conn.execute(
        """SELECT raw_text, source, created_at, households, road_blocked, health_risk, near_sensitive, landmark, is_duplicate, cluster_score
           FROM reports WHERE incident_id = ? ORDER BY is_duplicate ASC, (cluster_score IS NULL) DESC, cluster_score DESC, created_at DESC""",
        (incident_id,),
    ).fetchall())
    active = [item for item in reports if not item["is_duplicate"]]
    corridor = load_json(incident["corridor_json"], None)
    velocity = load_json(incident["velocity_json"], {})
    claims = sorted(int(item["households"]) for item in active if item["households"])
    return {
        "incident_id": incident["id"],
        "title": incident["title"],
        "category": incident["category"].replace("_", " "),
        "locality": incident["locality"],
        "road": incident["road"],
        "landmarks_mentioned": sorted({item["landmark"] for item in active if item["landmark"]}),
        "status": incident["status"],
        "report_count": incident["report_count"],
        "duplicate_count": incident["duplicate_count"],
        "independent_sources": incident["unique_sources"],
        "source_mix": load_json(incident["source_mix_json"], {}),
        "first_reported": _fmt_time(incident["first_reported"]),
        "last_reported": _fmt_time(incident["last_reported"]),
        "reports_mentioning_blocked_road": sum(1 for item in active if item["road_blocked"]),
        "reports_mentioning_health_risk": sum(1 for item in active if item["health_risk"]),
        "reports_mentioning_sensitive_place": sum(1 for item in active if item["near_sensitive"]),
        "reported_household_claims": {"min": claims[0], "max": claims[-1], "count": len(claims)} if claims else None,
        "estimated_households": incident["est_households"],
        "estimated_corridor_m": round(corridor["length_m"]) if corridor else None,
        "radius_m": round(incident["radius_m"]),
        "sensitive_place": incident["sensitive_place"],
        "velocity_label": velocity.get("label", "STEADY"),
        "reports_latest_3h": velocity.get("recent", 0),
        "reports_prior_3h": velocity.get("prior", 0),
        "priority": incident["priority"],
        "priority_band": band_for(incident["priority"]),
        "severity_floor_applied": bool(incident["severity_floor_applied"]),
        "confidence_label": confidence_label(incident["confidence"]),
        "confidence_reasons": load_json(incident["confidence_reasons_json"], []),
        "representative_reports": [
            {"source": item["source"], "time": _fmt_time(item["created_at"]), "text": item["raw_text"]} for item in active[:5]
        ],
    }


def template_brief(facts: dict[str, Any]) -> dict[str, Any]:
    location = ", ".join(value for value in (facts["road"], facts["locality"]) if value) or "location unconfirmed"
    mix = ", ".join(f"{source} {count}" for source, count in sorted(facts["source_mix"].items(), key=lambda pair: -pair[1]))
    fact_lines = [
        f"{_plural(facts['report_count'], 'report')} describe {facts['category']} at {location}"
        + (f"; {_plural(facts['duplicate_count'], 'repeat post')} counted once." if facts["duplicate_count"] else "."),
        f"{_plural(facts['independent_sources'], 'independent source')} across source types: {mix}.",
        f"First reported {facts['first_reported']}; most recent report {facts['last_reported']}.",
    ]
    if facts["landmarks_mentioned"]:
        fact_lines.append(f"Landmarks named in reports: {', '.join(facts['landmarks_mentioned'])}.")
    cues = []
    if facts["reports_mentioning_blocked_road"]:
        cues.append(f"{_plural(facts['reports_mentioning_blocked_road'], 'report')} say the road is blocked")
    if facts["reports_mentioning_health_risk"]:
        cues.append(f"{_plural(facts['reports_mentioning_health_risk'], 'report')} raise health concerns")
    if facts["reports_mentioning_sensitive_place"]:
        cues.append(f"{_plural(facts['reports_mentioning_sensitive_place'], 'report')} mention a nearby school, hospital, or market")
    if cues:
        fact_lines.append("Safety cues: " + "; ".join(cues) + ".")
    claims = facts["reported_household_claims"]
    if claims:
        span = f"{claims['min']}" if claims["min"] == claims["max"] else f"{claims['min']}–{claims['max']}"
        fact_lines.append(f"{_plural(claims['count'], 'report')} state {span} households affected.")

    assessment = [f"Priority {facts['priority']} ({facts['priority_band']})" + (" — raised to the severity floor because a severe hazard is near a sensitive place." if facts["severity_floor_applied"] else ".")]
    extent = f" along an estimated ~{facts['estimated_corridor_m']} m stretch" if facts["estimated_corridor_m"] else f" within an estimated ~{facts['radius_m']} m radius"
    assessment.append(f"Estimated impact: ~{facts['estimated_households']} households (est.){extent}; not yet confirmed on site.")
    if facts["sensitive_place"]:
        assessment.append(f"Sensitive location nearby: {facts['sensitive_place']} (from illustrative gazetteer).")
    trend = {
        "RAPIDLY ESCALATING": "Reports are arriving rapidly; the situation may be worsening.",
        "INCREASING": "Report rate is increasing.",
        "STEADY": "Report rate is steady.",
        "DECLINING": "Report rate is declining; verify whether the issue persists.",
    }[facts["velocity_label"]]
    assessment.append(f"{trend} ({facts['reports_latest_3h']} in the latest 3 h vs {facts['reports_prior_3h']} before.)")
    assessment.append(f"Confidence {facts['confidence_label']}: {'; '.join(facts['confidence_reasons'])}.")
    assessment.append("The cause has not been determined; reports describe symptoms only.")

    if facts["priority_band"] == "CRITICAL" or facts["severity_floor_applied"]:
        step = f"Send the nearest field crew to verify conditions at {location} first, then decide on jetting or barricading."
    elif facts["priority_band"] == "HIGH":
        step = f"Schedule a field verification at {location} within this shift."
    else:
        step = f"Ask a field officer to confirm the issue at {location} during routine rounds."
    return {"facts": fact_lines, "assessment": assessment, "recommended_next_step": SUGGESTION_PREFIX + step, "generated_by": "template"}


def _numbers(text: str) -> set[str]:
    return {value.lstrip("0") or "0" for value in re.findall(r"\d+", text)}


def _llm_brief(facts: dict[str, Any]) -> Optional[dict[str, Any]]:
    if anthropic is None or not llm_api_key():
        return None
    try:
        client = anthropic.Anthropic(api_key=llm_api_key(), timeout=LLM_TIMEOUT_SECONDS, max_retries=0)
        response = client.messages.parse(
            model=LLM_MODEL,
            max_tokens=LLM_MAX_OUTPUT_TOKENS * 2,
            system=BRIEF_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(facts, ensure_ascii=False)}],
            output_format=LLMBrief,
            output_config={"effort": "low"},
        )
        if response.stop_reason in ("refusal", "max_tokens") or response.parsed_output is None:
            return None
        brief = LLMBrief.model_validate(response.parsed_output.model_dump())
    except (ValidationError, Exception):  # any failure falls back to the template
        return None
    # Guard: every number in the output must come from the payload.
    allowed = _numbers(json.dumps(facts, ensure_ascii=False))
    produced = _numbers(" ".join([*brief.facts, *brief.assessment, brief.recommended_next_step]))
    if not produced <= allowed:
        return None
    step = brief.recommended_next_step.strip()
    if not step.lower().startswith("ai suggestion"):
        step = SUGGESTION_PREFIX + step
    return {"facts": brief.facts, "assessment": brief.assessment, "recommended_next_step": step, "generated_by": "llm"}


def generate_brief(conn: sqlite3.Connection, incident_id: str) -> dict[str, Any]:
    facts = build_fact_payload(conn, incident_id)
    return _llm_brief(facts) or template_brief(facts)
