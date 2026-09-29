import re
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app

STAGES = ["Reports received", "Classifying", "Extracting locations", "Finding duplicates", "Clustering incidents", "Calculating priority"]


def _strip(items):
    return [(item["id"], item["priority"], item["status"]) for item in items]


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        assert test_client.post("/api/reset").status_code == 200
        yield test_client


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["llm_configured"] is False and body["extraction_mode"] == "rules_fallback"


def test_summary_is_computed_from_database(client):
    first, second = client.get("/api/summary").json(), client.get("/api/summary").json()
    assert first == second
    assert set(first) == {"reports_today", "active_incidents", "critical", "escalating", "resolved", "unlocated"}
    incidents = client.get("/api/incidents").json()
    assert first["active_incidents"] == sum(1 for item in incidents if item["status"] != "resolved")
    assert first["resolved"] == sum(1 for item in incidents if item["status"] == "resolved")
    assert first["critical"] == sum(1 for item in incidents if item["status"] != "resolved" and item["priority"] >= 80)


def test_incident_list_sorted_and_compact(client):
    incidents = client.get("/api/incidents").json()
    assert 35 <= len(incidents) <= 45
    priorities = [item["priority"] for item in incidents]
    assert priorities == sorted(priorities, reverse=True)
    assert "raw_text" not in incidents[0] and "priority_factors" not in incidents[0]


def test_incident_filters(client):
    assert all(item["priority"] >= 50 for item in client.get("/api/incidents", params={"min_priority": 50}).json())
    assert all(item["status"] == "resolved" for item in client.get("/api/incidents", params={"status": "resolved"}).json())
    assert all(item["status"] != "resolved" for item in client.get("/api/incidents", params={"status": "active"}).json())
    assert client.get("/api/incidents", params={"min_priority": 100}).status_code == 200
    assert client.get("/api/incidents", params={"min_priority": 101}).status_code == 422
    assert client.get("/api/incidents", params={"status": "bogus"}).status_code == 422
    empty = client.get("/api/incidents", params={"status": "dispatched", "min_priority": 100})
    assert empty.status_code == 200 and empty.json() == []


def test_incident_detail_and_evidence(client):
    incident_id = client.get("/api/incidents").json()[0]["id"]
    detail = client.get(f"/api/incidents/{incident_id}").json()
    assert detail["id"] == incident_id and len(detail["priority_factors"]) == 8
    assert detail["velocity"]["label"] == detail["velocity_label"]
    evidence = client.get(f"/api/incidents/{incident_id}/evidence").json()
    assert evidence["incident_id"] == incident_id
    assert evidence["factors"] == detail["priority_factors"]
    assert evidence["representative_reports"]
    assert evidence["extraction"]["label"] == "Rules fallback"


def test_unknown_incident_returns_404(client):
    for method, path in (("get", "/api/incidents/HYD-999"), ("get", "/api/incidents/HYD-999/evidence"), ("post", "/api/incidents/HYD-999/brief")):
        response = getattr(client, method)(path)
        assert response.status_code == 404 and "detail" in response.json()
    assert client.post("/api/incidents/HYD-999/status", json={"status": "verified"}).status_code == 404


def test_heatmap_shape(client):
    points = client.get("/api/heatmap").json()
    assert points and all(len(point) == 3 and 0 < point[2] <= 1 for point in points)


def test_status_update_and_validation(client):
    incident_id = client.get("/api/incidents", params={"status": "open"}).json()[0]["id"]
    before = client.get("/api/summary").json()
    assert client.post(f"/api/incidents/{incident_id}/status", json={"status": "bogus"}).status_code == 422
    assert client.post(f"/api/incidents/{incident_id}/status", json={}).status_code == 422
    response = client.post(f"/api/incidents/{incident_id}/status", json={"status": "resolved"})
    assert response.json() == {"id": incident_id, "status": "resolved"}
    after = client.get("/api/summary").json()
    assert after["resolved"] == before["resolved"] + 1
    assert after["active_incidents"] == before["active_incidents"] - 1
    client.post(f"/api/incidents/{incident_id}/status", json={"status": "open"})


def test_brief_separates_facts_from_assessment(client):
    incident_id = client.get("/api/incidents").json()[0]["id"]
    brief = client.post(f"/api/incidents/{incident_id}/brief").json()
    assert brief["generated_by"] == "template"
    assert brief["facts"] and brief["assessment"]
    assert brief["recommended_next_step"].startswith("AI suggestion:")
    assert any("est." in line for line in brief["assessment"])
    assert not any("est." in line for line in brief["facts"])


def test_simulate_then_reset_is_idempotent(client):
    baseline = client.get("/api/incidents").json()
    started = time.perf_counter()
    result = client.post("/api/simulate").json()
    assert time.perf_counter() - started < 5
    assert result["received"] == 100 and result["out_of_scope"] == 4
    assert [stage["name"] for stage in result["stages"]] == STAGES
    assert 15 <= len(result["new_incident_ids"]) <= 19
    assert result["incidents_after"] - result["incidents_before"] == len(result["new_incident_ids"])
    assert result["hero_incident_id"] in result["new_incident_ids"]
    assert re.match(r"batch-\d{4}-\d{2}-\d{2}T", result["batch_id"])
    hero = client.get(f"/api/incidents/{result['hero_incident_id']}").json()
    assert hero["band"] == "CRITICAL" and hero["corridor"] is not None
    ranked = [item["id"] for item in client.get("/api/incidents", params={"status": "active"}).json()]
    assert ranked[0] == hero["id"]

    first = client.post("/api/reset").json()
    second = client.post("/api/reset").json()
    assert first == second
    assert _strip(client.get("/api/incidents").json()) == _strip(baseline)


def test_second_simulation_still_works(client):
    client.post("/api/reset")
    client.post("/api/simulate")
    second = client.post("/api/simulate").json()
    assert second["received"] == 100 and second["hero_incident_id"]
    hero = client.get(f"/api/incidents/{second['hero_incident_id']}").json()
    assert hero["locality"] == "Kukatpally" and hero["band"] == "CRITICAL"
    client.post("/api/reset")
