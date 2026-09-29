"""Live-ingestion tests. Only the HTTP call is mocked; normalization, extraction, dedupe,
clustering and scoring are the real SewerSense code."""

import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.ingestion import IngestionError, run_ingestion
from app.ingestion import apify as apify_module
from app.ingestion import tavily as tavily_module
from app.ingestion.apify import ApifyAdapter
from app.ingestion.base import ExternalItem, normalize
from app.ingestion.tavily import TavilyAdapter
from app.main import app

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)

ARTICLE_1 = {
    "title": "Sewage overflow on Road No. 5 in Kukatpally troubles residents",
    "url": "https://www.example-news.in/hyderabad/kukatpally-sewage?utm_source=feed",
    "content": "Residents of Kukatpally complain of sewage overflowing on Road No. 5 near Kukatpally Government School. Vehicles cannot pass and about 30 houses are affected.",
    "score": 0.82,
    "published_date": "Sun, 28 Sep 2026 08:15:00 GMT",
}
ARTICLE_2 = {
    "title": "Open manhole near Miyapur school raises safety fears",
    "url": "https://another-paper.com/city/miyapur-open-manhole",
    "content": "An open manhole on Hafeezpet Road in Miyapur, beside Miyapur Zilla Parishad School, has been left uncovered for two days.",
    "score": 0.77,
}
OFF_TOPIC = {
    "title": "Hyderabad metro ridership rises",
    "url": "https://example-news.in/metro-ridership",
    "content": "Metro ridership in Hyderabad crossed a new record this month according to officials.",
}


@pytest.fixture
def live_conn():
    conn = db.connect(":memory:")
    db.initialize(conn)
    yield conn
    conn.close()


@pytest.fixture
def tavily_on(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")


@pytest.fixture
def apify_on(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "apify_api_test")
    monkeypatch.setenv("APIFY_ACTOR_ID", "apify/google-search-scraper")
    monkeypatch.setattr(config, "APIFY_ACTOR_INPUT", '{"queries": "Hyderabad sewage"}')


def mock_tavily(monkeypatch, responses):
    calls = []

    def fake(url, body, token, timeout, params=None):
        calls.append(body["query"])
        response = responses(body["query"]) if callable(responses) else responses
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(tavily_module, "post_json", fake)
    return calls


def mock_apify(monkeypatch, response):
    calls = []

    def fake(url, body, token, timeout, params=None):
        calls.append({"url": url, "body": body, "params": params})
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(apify_module, "post_json", fake)
    return calls


# --- Tavily ------------------------------------------------------------------------------------
def test_tavily_success_normalizes_with_provenance(monkeypatch, tavily_on):
    calls = mock_tavily(monkeypatch, {"results": [ARTICLE_1, ARTICLE_2]})
    result = TavilyAdapter(queries=["Hyderabad sewage overflow"]).fetch()
    assert calls == ["Hyderabad sewage overflow"]
    assert result.retrieved == 2 and result.rejected == 0
    report, provenance = normalize(result.items[0], NOW)
    assert report.source == "news" and report.source_handle == "news_examplenews"
    assert report.raw_text.startswith("Sewage overflow on Road No. 5 in Kukatpally")
    assert report.created_at == "2026-09-28T08:15:00+00:00"  # the published time supplied by Tavily
    assert provenance["url"] == "https://www.example-news.in/hyderabad/kukatpally-sewage"  # tracking params removed
    assert provenance["queries"] == ["Hyderabad sewage overflow"]
    assert provenance["published_at"] == ARTICLE_1["published_date"]
    assert provenance["original_content"] == ARTICLE_1["content"]
    assert provenance["metadata"] == {"score": 0.82}


def test_tavily_missing_optional_fields_are_not_invented(monkeypatch, tavily_on):
    mock_tavily(monkeypatch, {"results": [{"url": "https://x.in/a", "content": "Drain overflowing on Station Road, Secunderabad since yesterday."}]})
    item = TavilyAdapter(queries=["q"]).fetch().items[0]
    report, provenance = normalize(item, NOW)
    assert provenance["title"] is None and provenance["published_at"] is None
    assert report.created_at == NOW.isoformat()  # ingestion time is used, published_at stays null


def test_tavily_empty_and_malformed(monkeypatch, tavily_on):
    mock_tavily(monkeypatch, {"results": []})
    assert TavilyAdapter(queries=["q"]).fetch().retrieved == 0
    mock_tavily(monkeypatch, {"results": [{"title": "no url or content"}, "garbage", ARTICLE_2]})
    result = TavilyAdapter(queries=["q"]).fetch()
    assert result.retrieved == 3 and result.rejected == 2 and len(result.items) == 1
    mock_tavily(monkeypatch, {"unexpected": True})
    with pytest.raises(IngestionError):
        TavilyAdapter(queries=["q"]).fetch()


def test_tavily_missing_key_and_api_failure(monkeypatch, live_conn):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    result = run_ingestion(live_conn, ["tavily"])
    assert result["status"] == "unavailable" and result["sources"][0]["status"] == "not_configured"
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    mock_tavily(monkeypatch, IngestionError("HTTP 500 from api.tavily.com"))
    result = run_ingestion(live_conn, ["tavily"])
    assert result["sources"][0]["status"] == "failed" and "HTTP 500" in result["sources"][0]["message"]
    assert "tvly-test" not in json.dumps(result)


def test_tavily_partial_query_failure_keeps_other_results(monkeypatch, tavily_on):
    mock_tavily(monkeypatch, lambda query: IngestionError("HTTP 429 from api.tavily.com") if query == "bad" else {"results": [ARTICLE_1]})
    result = TavilyAdapter(queries=["good", "bad"]).fetch()
    assert len(result.items) == 1 and "HTTP 429" in result.warnings[0]


# --- Apify -------------------------------------------------------------------------------------
def test_apify_success_normalizes_with_provenance(monkeypatch, apify_on):
    calls = mock_apify(monkeypatch, [
        {"title": "Sewage leak in Uppal", "url": "https://forum.example.org/t/123", "description": "Sewage leaking on Uppal Ring Road in Uppal for three days, foul smell everywhere.", "searchQuery": {"term": "Hyderabad sewage"}, "position": 2},
    ])
    result = ApifyAdapter().fetch()
    assert calls[0]["url"].endswith("/acts/apify~google-search-scraper/run-sync-get-dataset-items")
    assert calls[0]["body"] == {"queries": "Hyderabad sewage"}  # Actor input comes from configuration
    report, provenance = normalize(result.items[0], NOW)
    assert report.source == config.APIFY_SOURCE_TYPE
    assert provenance["origin"] == "apify" and provenance["queries"] == ["Hyderabad sewage"]
    assert provenance["metadata"]["actor"] == "apify~google-search-scraper" and provenance["metadata"]["position"] == 2


def test_apify_author_is_pseudonymised(monkeypatch, apify_on):
    mock_apify(monkeypatch, [{"text": "Open manhole near Kondapur Area Hospital, very dangerous for patients.", "url": "https://social.example/p/1", "username": "real_person_42"}])
    report, provenance = normalize(ApifyAdapter().fetch().items[0], NOW)
    assert "real_person_42" not in report.source_handle and "real_person_42" not in json.dumps(provenance)


def test_apify_empty_and_malformed(monkeypatch, apify_on):
    mock_apify(monkeypatch, [])
    assert ApifyAdapter().fetch().retrieved == 0
    mock_apify(monkeypatch, [{"foo": "bar"}, 42, {"text": "Drain blockage on Film Nagar Road, Jubilee Hills.", "url": "https://s.example/2"}])
    result = ApifyAdapter().fetch()
    assert result.retrieved == 3 and result.rejected == 2 and len(result.items) == 1
    mock_apify(monkeypatch, {"error": "not a list"})
    with pytest.raises(IngestionError):
        ApifyAdapter().fetch()


def test_apify_missing_token_bad_input_and_failure(monkeypatch, live_conn):
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    result = run_ingestion(live_conn, ["apify"])
    assert result["sources"][0]["status"] == "not_configured" and "APIFY_API_TOKEN" in result["sources"][0]["message"]
    monkeypatch.setenv("APIFY_API_TOKEN", "apify_api_secret")
    monkeypatch.setenv("APIFY_ACTOR_ID", "someone~actor")
    monkeypatch.setattr(config, "APIFY_ACTOR_INPUT", "{not json")
    assert "not valid JSON" in run_ingestion(live_conn, ["apify"])["sources"][0]["message"]
    monkeypatch.setattr(config, "APIFY_ACTOR_INPUT", "{}")
    mock_apify(monkeypatch, IngestionError("HTTP 408 from api.apify.com"))
    result = run_ingestion(live_conn, ["apify"])
    assert result["sources"][0]["status"] == "failed" and "apify_api_secret" not in json.dumps(result)


# --- Integration through the real pipeline -----------------------------------------------------
def test_ingestion_runs_existing_pipeline_and_dedupes_across_sources(monkeypatch, live_conn, tavily_on, apify_on):
    mock_tavily(monkeypatch, {"results": [ARTICLE_1, ARTICLE_2, OFF_TOPIC]})
    # Apify returns the same Kukatpally article (same URL) plus one new report.
    mock_apify(monkeypatch, [
        {"title": ARTICLE_1["title"], "url": ARTICLE_1["url"], "description": ARTICLE_1["content"]},
        {"text": "Caller reports sewage overflowing near Road No. 5 Bus Stop, Kukatpally. Road is blocked.", "url": "https://social.example/p/9"},
    ])
    monkeypatch.setattr(tavily_module.config, "TAVILY_QUERIES", ["Hyderabad sewage overflow", "Kukatpally sewage"])
    result = run_ingestion(live_conn, ["tavily", "apify"], adapters={"tavily": TavilyAdapter(), "apify": ApifyAdapter()}, provider=None, now=NOW)

    tavily, apify = result["sources"]
    assert result["status"] == "ok"
    # Two Tavily queries returned the same 3 articles: 3 unique, 3 repeats.
    assert tavily["retrieved_count"] == 6 and tavily["inserted_count"] == 3 and tavily["duplicate_count"] >= 3
    # Apify's copy of ARTICLE_1 is recognised as the same report, not a new one.
    assert apify["inserted_count"] == 1 and apify["duplicate_count"] >= 1

    # Reports reached SQLite and went through the existing extraction + filtering.
    rows = {row["id"]: dict(row) for row in live_conn.execute("SELECT * FROM reports")}
    assert len(rows) == 4
    off_topic = next(row for row in rows.values() if "ridership" in row["raw_text"])
    assert off_topic["in_scope"] == 0 and off_topic["incident_id"] is None
    kukatpally = next(row for row in rows.values() if "Kukatpally Government School" in row["raw_text"])
    assert kukatpally["locality"] == "Kukatpally" and kukatpally["category"] == "overflow" and kukatpally["geo_quality"] == "exact"

    # Existing clustering grouped the two Kukatpally Road No. 5 reports into one incident.
    incidents = [dict(row) for row in live_conn.execute("SELECT * FROM incidents")]
    road5 = [incident for incident in incidents if incident["road"] == "Road No. 5"]
    assert len(road5) == 1 and road5[0]["report_count"] == 2 and road5[0]["unique_sources"] == 2
    assert result["pipeline"]["incidents_after"] == len(incidents) == 2
    # Existing scoring ran: the open manhole beside a school hits the severity floor.
    manhole = next(incident for incident in incidents if incident["category"] == "manhole")
    assert manhole["priority"] >= 75 and manhole["severity_floor_applied"] == 1

    # Provenance recorded, including the other source that saw the same article.
    provenance = dict(live_conn.execute("SELECT * FROM report_provenance WHERE report_id = ?", (kukatpally["id"],)).fetchone())
    assert provenance["origin"] == "tavily" and provenance["url"] == "https://www.example-news.in/hyderabad/kukatpally-sewage"
    assert json.loads(provenance["queries_json"]) == ["Hyderabad sewage overflow", "Kukatpally sewage"]
    assert json.loads(provenance["metadata_json"])["also_seen_in"] == ["apify"]

    # Re-running the same ingestion inserts nothing new.
    again = run_ingestion(live_conn, ["tavily", "apify"], adapters={"tavily": TavilyAdapter(), "apify": ApifyAdapter()}, provider=None, now=NOW)
    assert sum(source["inserted_count"] for source in again["sources"]) == 0 and again["pipeline"] is None


def test_one_source_fails_other_still_processed(monkeypatch, live_conn, tavily_on, apify_on):
    mock_tavily(monkeypatch, IngestionError("network error contacting api.tavily.com: timeout"))
    mock_apify(monkeypatch, [{"text": ARTICLE_2["content"], "url": ARTICLE_2["url"]}])
    result = run_ingestion(live_conn, ["tavily", "apify"], provider=None, now=NOW)
    assert result["status"] == "partial"
    assert [source["status"] for source in result["sources"]] == ["failed", "ok"]
    assert result["pipeline"]["received"] == 1 and result["pipeline"]["incidents_after"] == 1


# --- API ---------------------------------------------------------------------------------------
def test_api_ingest_without_keys_and_dataset_isolation():
    with TestClient(app) as client:
        client.post("/api/reset")
        demo_before = client.get("/api/summary").json()
        response = client.post("/api/ingest", json={"sources": ["tavily", "apify"]})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "unavailable" and {source["status"] for source in body["sources"]} == {"not_configured"}
        assert client.post("/api/ingest", json={"sources": ["bogus"]}).status_code == 422
        # Live dataset is separate and empty; the demo dataset is untouched.
        assert client.get("/api/incidents", params={"dataset": "live"}).json() == []
        assert client.get("/api/summary").json() == demo_before
        assert client.post("/api/simulate", params={"dataset": "live"}).status_code == 409
        assert client.post("/api/reset", params={"dataset": "live"}).json()["default_incident_id"] is None
        assert client.get("/api/health").json()["live_sources"] == {"tavily": False, "apify": False}


def test_api_ingest_with_mocked_sources_shows_in_live_dataset(monkeypatch, tavily_on):
    mock_tavily(monkeypatch, {"results": [ARTICLE_1, ARTICLE_2]})
    monkeypatch.setattr(tavily_module.config, "TAVILY_QUERIES", ["Hyderabad sewage overflow"])
    with TestClient(app) as client:
        client.post("/api/reset", params={"dataset": "live"})
        body = client.post("/api/ingest", json={"sources": ["tavily"]}).json()
        assert body["status"] == "ok" and body["pipeline"]["incidents_after"] == 2
        live = client.get("/api/incidents", params={"dataset": "live"}).json()
        assert len(live) == 2
        evidence = client.get(f"/api/incidents/{live[0]['id']}/evidence", params={"dataset": "live"}).json()
        assert evidence["representative_reports"][0]["origin"] == "tavily" and evidence["representative_reports"][0]["url"].startswith("https://")
        assert client.post(f"/api/incidents/{live[0]['id']}/brief", params={"dataset": "live"}).json()["generated_by"] == "template"
        assert len(client.get("/api/incidents").json()) >= 35  # demo dataset unchanged
        client.post("/api/reset", params={"dataset": "live"})
