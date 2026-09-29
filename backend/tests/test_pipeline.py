import inspect
import json
import time
from datetime import timedelta

from app import db, pipeline, service
from app.generator import generate_batch
from app.pipeline import TfidfModel, corridor_for, text_similarity, velocity_for
from conftest import FIXED_NOW
from evaluation import adjusted_rand_index, assignments, purity, truth_incident_ids


def _incident(conn, incident_id):
    return dict(conn.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone())


def _hero_id(conn, batch_id):
    counts = truth_incident_ids(conn, batch_id, "TRUTH-HERO")
    return max((key for key in counts if key), key=lambda key: counts[key])


def test_pipeline_never_touches_ground_truth():
    assert "truth_incident" not in inspect.getsource(pipeline)
    assert "truth_incident" not in db.PIPELINE_REPORT_COLUMNS


def test_baseline_incident_count_and_statuses(demo_db):
    conn, _, _ = demo_db
    total = conn.execute("SELECT COUNT(DISTINCT incident_id) FROM reports WHERE batch_id = 'baseline' AND incident_id IS NOT NULL").fetchone()[0]
    assert 35 <= total <= 45
    statuses = {row[0] for row in conn.execute("SELECT DISTINCT status FROM incidents")}
    assert {"open", "verified", "dispatched", "resolved"} <= statuses


def test_batch_produces_expected_incident_count(demo_db):
    conn, _, batch = demo_db
    pairs = assignments(conn, batch["batch_id"])
    ari, pure = adjusted_rand_index(pairs), purity(pairs)
    print(f"\nBatch: {len(batch['new_incident_ids'])} new incidents, {batch['batch_incident_count']} touched; ARI={ari:.3f} purity={pure:.3f}")
    assert 15 <= len(batch["new_incident_ids"]) <= 19
    assert 15 <= batch["batch_incident_count"] <= 19
    assert ari > 0.85
    assert pure > 0.9


def test_fresh_database_batch_alone():
    conn = db.connect(":memory:")
    db.recreate(conn)
    started = time.perf_counter()
    result = service.run_batch(conn, generate_batch(100, now=FIXED_NOW), "solo", provider=None)
    assert time.perf_counter() - started < 5
    assert 15 <= result["incidents_after"] <= 19


def test_hero_is_single_critical_escalating_cluster(demo_db):
    conn, _, batch = demo_db
    counts = truth_incident_ids(conn, batch["batch_id"], "TRUTH-HERO")
    assigned = {key for key in counts if key}
    assert len(assigned) == 1
    hero = _incident(conn, assigned.pop())
    assert batch["hero_incident_id"] == hero["id"]
    assert hero["report_count"] >= 40 and hero["unique_sources"] >= 28
    assert hero["priority"] >= 80 and hero["velocity_label"] == "RAPIDLY ESCALATING"
    corridor = json.loads(hero["corridor_json"])
    assert 100 <= corridor["length_m"] <= 140
    assert hero["locality"] == "Kukatpally" and hero["road"] == "Road No. 5"


def test_small_dangerous_incident_gets_severity_floor_and_top_five(demo_db):
    conn, _, batch = demo_db
    counts = truth_incident_ids(conn, batch["batch_id"], "TRUTH-DANGER")
    assert len(counts) == 1
    danger = _incident(conn, next(iter(counts)))
    assert danger["report_count"] == 3
    assert danger["priority"] >= 75 and danger["severity_floor_applied"] == 1
    ranked = [row[0] for row in conn.execute("SELECT id FROM incidents WHERE status != 'resolved' ORDER BY priority DESC, last_reported DESC LIMIT 5")]
    assert danger["id"] in ranked


def test_inflated_single_handle_incident_ranks_below_hero(demo_db):
    conn, _, batch = demo_db
    counts = truth_incident_ids(conn, batch["batch_id"], "TRUTH-INFLATED")
    inflated = _incident(conn, max(counts, key=counts.get))
    hero = _incident(conn, _hero_id(conn, batch["batch_id"]))
    assert inflated["report_count"] >= 8 and inflated["unique_sources"] == 1
    assert inflated["priority"] < hero["priority"]


def test_out_of_scope_reports_are_excluded(demo_db):
    conn, _, batch = demo_db
    assert batch["out_of_scope"] == 4
    rows = conn.execute("SELECT in_scope, incident_id FROM reports WHERE batch_id = ? AND truth_incident LIKE 'OUT-%'", (batch["batch_id"],)).fetchall()
    assert len(rows) == 4 and all(in_scope == 0 and incident is None for in_scope, incident in rows)


def test_duplicates_are_evidence_not_volume(demo_db):
    conn, _, batch = demo_db
    hero_id = _hero_id(conn, batch["batch_id"])
    hero = _incident(conn, hero_id)
    handles = {row[0] for row in conn.execute("SELECT source_handle FROM reports WHERE incident_id = ? AND is_duplicate = 0", (hero_id,))}
    duplicates = conn.execute("SELECT COUNT(*) FROM reports WHERE incident_id = ? AND is_duplicate = 1", (hero_id,)).fetchone()[0]
    assert duplicates == hero["duplicate_count"] >= 6
    assert hero["unique_sources"] == len(handles)
    velocity = json.loads(hero["velocity_json"])
    non_duplicates = conn.execute("SELECT COUNT(*) FROM reports WHERE incident_id = ? AND is_duplicate = 0", (hero_id,)).fetchone()[0]
    assert sum(velocity["buckets"]) <= non_duplicates


def test_priority_is_traceable_to_factors(demo_db):
    conn, _, _ = demo_db
    for row in conn.execute("SELECT priority, base_priority, severity_floor_applied, priority_factors_json FROM incidents"):
        factors = json.loads(row["priority_factors_json"])
        assert len(factors) == 8
        for factor in factors:
            assert abs(factor["contribution"] - factor["weight"] * factor["value"] * 100) < 0.11
            assert factor["sentence"]
        assert abs(sum(factor["contribution"] for factor in factors) - row["base_priority"]) <= 1
        assert row["priority"] == (75 if row["severity_floor_applied"] else row["base_priority"])


def test_cluster_scores_are_persisted(demo_db):
    conn, _, batch = demo_db
    rows = conn.execute("SELECT cluster_score, cluster_details_json FROM reports WHERE batch_id = ? AND cluster_score IS NOT NULL", (batch["batch_id"],)).fetchall()
    assert rows
    for score, details in rows:
        parts = json.loads(details)
        weighted = 0.30 * parts["semantic"] + 0.35 * parts["geographic"] + 0.15 * parts["temporal"] + 0.20 * parts["category"]
        assert abs(weighted - score) < 0.01


def test_simulation_is_fast(demo_db):
    _, _, batch = demo_db
    assert batch["elapsed_ms"] < 5000
    assert [stage["name"] for stage in batch["stages"]] == ["Reports received", "Classifying", "Extracting locations", "Finding duplicates", "Clustering incidents", "Calculating priority"]


def test_tfidf_similarity_behaviour():
    model = TfidfModel(["sewer overflow on road no. 5", "foul smell in madhapur", "open manhole near school"])
    assert model.similarity("sewer overflow on road no. 5", "sewer overflow on road no. 5") > 0.99
    assert model.similarity("sewer overflow on road no. 5", "foul smell in madhapur") < 0.1
    assert text_similarity("sewer overflow", "sewer overflow again") > 0.5


def test_corridor_and_velocity_units():
    line = [(17.4948 + index * 0.0001, 78.3996 + index * 0.0003) for index in range(10)]
    corridor, _, _ = corridor_for(line)
    assert corridor is not None and 150 < corridor["length_m"] < 300
    cluster = [(17.4948, 78.3996), (17.49481, 78.39961), (17.49479, 78.39959)]
    assert corridor_for(cluster)[0] is None
    reports = [{"created_at": (FIXED_NOW - timedelta(minutes=10 * index)).isoformat()} for index in range(12)]
    assert velocity_for(reports, FIXED_NOW)["label"] == "RAPIDLY ESCALATING"
    assert velocity_for(reports[:2], FIXED_NOW)["label"] == "STEADY"  # too few reports to call a trend
