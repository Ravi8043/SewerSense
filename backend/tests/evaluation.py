"""Test-only evaluation helpers. Joins hidden ground truth to *finalised* pipeline output."""

from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from math import comb


def assignments(conn: sqlite3.Connection, batch_id: str) -> list[tuple[str, str]]:
    """(truth_incident, assigned incident or 'UNASSIGNED:<report id>') for in-scope reports."""
    rows = conn.execute(
        "SELECT id, truth_incident, incident_id FROM reports WHERE batch_id = ? AND in_scope = 1", (batch_id,)
    ).fetchall()
    return [(truth, incident or f"UNASSIGNED:{report_id}") for report_id, truth, incident in rows]


def adjusted_rand_index(pairs: list[tuple[str, str]]) -> float:
    contingency = Counter(pairs)
    truth_sizes = Counter(truth for truth, _ in pairs)
    predicted_sizes = Counter(predicted for _, predicted in pairs)
    index = sum(comb(value, 2) for value in contingency.values())
    truth_sum = sum(comb(value, 2) for value in truth_sizes.values())
    predicted_sum = sum(comb(value, 2) for value in predicted_sizes.values())
    expected = truth_sum * predicted_sum / comb(len(pairs), 2)
    maximum = (truth_sum + predicted_sum) / 2
    return 1.0 if maximum == expected else (index - expected) / (maximum - expected)


def purity(pairs: list[tuple[str, str]]) -> float:
    clusters: dict[str, Counter[str]] = defaultdict(Counter)
    for truth, predicted in pairs:
        clusters[predicted][truth] += 1
    return sum(counter.most_common(1)[0][1] for counter in clusters.values()) / len(pairs)


def truth_incident_ids(conn: sqlite3.Connection, batch_id: str, truth: str) -> Counter[str]:
    rows = conn.execute("SELECT incident_id FROM reports WHERE batch_id = ? AND truth_incident = ?", (batch_id, truth)).fetchall()
    return Counter(row[0] for row in rows)
