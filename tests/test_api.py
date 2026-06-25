"""Tests for FastAPI endpoints — DB mocked, no Neon connection needed."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.database import get_db
from api.main import app


def _make_conn(rows: list[dict]):
    """Build a mock SQLAlchemy connection that returns `rows` for any execute() call."""
    mock_conn = MagicMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = rows
    mock_result.scalar.return_value = rows[0] if rows else None
    mock_conn.execute.return_value = mock_result
    return mock_conn


@pytest.fixture()
def client():
    return TestClient(app)


# ── /health ──────────────────────────────────────────────────────────────────


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── /matches ─────────────────────────────────────────────────────────────────

FAKE_MATCHES = [
    {
        "match_id": 1,
        "match_date": "2026-06-13",
        "stage": "Group B",
        "home_team_name": "Spain",
        "away_team_name": "Cape Verde",
        "home_team_code": "ESP",
        "away_team_code": "CPV",
        "home_confederation": "UEFA",
        "away_confederation": "CAF",
        "home_score": 1,
        "away_score": 1,
        "result": "draw",
        "stadium_name": None,
    }
]


def test_matches_returns_list(client):
    conn = _make_conn(FAKE_MATCHES)
    app.dependency_overrides[get_db] = lambda: conn
    r = client.get("/matches?limit=1")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert data[0]["home_team_name"] == "Spain"
    app.dependency_overrides.clear()


def test_matches_with_group_filter(client):
    conn = _make_conn(FAKE_MATCHES)
    app.dependency_overrides[get_db] = lambda: conn
    r = client.get("/matches?group=Group+B")
    assert r.status_code == 200
    app.dependency_overrides.clear()


def test_matches_with_status_filter(client):
    conn = _make_conn(FAKE_MATCHES)
    app.dependency_overrides[get_db] = lambda: conn
    r = client.get("/matches?status=finished")
    assert r.status_code == 200
    app.dependency_overrides.clear()


# ── /matches/standings ────────────────────────────────────────────────────────

FAKE_STANDINGS = [
    {
        "group": "Group B",
        "team": "Spain",
        "code": "ESP",
        "played": 1,
        "wins": 0,
        "draws": 1,
        "losses": 0,
        "gf": 1,
        "ga": 1,
        "gd": 0,
        "points": 1,
    },
    {
        "group": "Group B",
        "team": "Cape Verde",
        "code": "CPV",
        "played": 1,
        "wins": 0,
        "draws": 1,
        "losses": 0,
        "gf": 1,
        "ga": 1,
        "gd": 0,
        "points": 1,
    },
]


def test_standings_grouped_by_group(client):
    conn = _make_conn(FAKE_STANDINGS)
    app.dependency_overrides[get_db] = lambda: conn
    r = client.get("/matches/standings")
    assert r.status_code == 200
    data = r.json()
    assert "Group B" in data
    assert isinstance(data["Group B"], list)
    assert len(data["Group B"]) == 2
    app.dependency_overrides.clear()


# ── /team ─────────────────────────────────────────────────────────────────────

FAKE_TEAM_STATS = [
    {
        "team_canonical": "Spain",
        "fifa_code": "ESP",
        "confederation": "UEFA",
        "competition_slug": "wc2026",
        "competition": "wc2026",
        "matches_played": 1,
        "wins": 0,
        "draws": 1,
        "losses": 0,
        "goals_scored": 1,
        "goals_conceded": 1,
        "goal_diff": 0,
        "points": 1,
        "win_pct": 0.0,
        "avg_xg_per_match": None,
        "total_xg": None,
        "total_shots": None,
        "xg_overperformance": None,
        "last_match_date": "2026-06-13",
    }
]


def test_team_stats_found(client):
    conn = _make_conn(FAKE_TEAM_STATS)
    app.dependency_overrides[get_db] = lambda: conn
    r = client.get("/team/ESP/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["team"] == "Spain"
    assert data["code"] == "ESP"
    assert isinstance(data["stats_by_competition"], list)
    app.dependency_overrides.clear()


def test_team_stats_not_found(client):
    conn = _make_conn([])  # empty result → 404
    app.dependency_overrides[get_db] = lambda: conn
    r = client.get("/team/ZZZ/stats")
    assert r.status_code == 404
    app.dependency_overrides.clear()


def test_team_list(client):
    conn = _make_conn(FAKE_TEAM_STATS)
    app.dependency_overrides[get_db] = lambda: conn
    r = client.get("/team")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    app.dependency_overrides.clear()


# ── /predict/winner ───────────────────────────────────────────────────────────

FAKE_RATINGS_STATS = [
    {"team": "spain", "code": "esp", "avg_xg_per_match": 1.5, "defense": 0.6},
    {"team": "france", "code": "fra", "avg_xg_per_match": 1.4, "defense": 0.7},
]

FAKE_RATINGS_CODES = [
    {"team": "spain", "code": "esp"},
    {"team": "france", "code": "fra"},
]


def test_predict_winner_by_name(client):
    mock_conn = MagicMock()
    call_count = [0]

    def side_effect(sql, *args, **kwargs):
        result = MagicMock()
        if call_count[0] == 0:
            result.mappings.return_value.all.return_value = FAKE_RATINGS_STATS
        else:
            result.mappings.return_value.all.return_value = FAKE_RATINGS_CODES
        call_count[0] += 1
        return result

    mock_conn.execute.side_effect = side_effect
    app.dependency_overrides[get_db] = lambda: mock_conn

    r = client.post("/predict/winner", json={"home": "spain", "away": "france"})
    assert r.status_code == 200
    data = r.json()
    assert "home_win_pct" in data
    assert "draw_pct" in data
    assert "away_win_pct" in data
    total = data["home_win_pct"] + data["draw_pct"] + data["away_win_pct"]
    assert abs(total - 100.0) < 1.0  # probabilities sum to ~100%
    app.dependency_overrides.clear()


def test_predict_winner_team_not_found(client):
    mock_conn = MagicMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []
    mock_conn.execute.return_value = mock_result

    app.dependency_overrides[get_db] = lambda: mock_conn
    r = client.post("/predict/winner", json={"home": "Wakanda", "away": "Spain"})
    assert r.status_code == 404
    app.dependency_overrides.clear()


def test_predict_probabilities_sum_to_100(client):
    mock_conn = MagicMock()
    call_count = [0]

    def side_effect(sql, *args, **kwargs):
        result = MagicMock()
        if call_count[0] == 0:
            result.mappings.return_value.all.return_value = FAKE_RATINGS_STATS
        else:
            result.mappings.return_value.all.return_value = FAKE_RATINGS_CODES
        call_count[0] += 1
        return result

    mock_conn.execute.side_effect = side_effect
    app.dependency_overrides[get_db] = lambda: mock_conn

    r = client.post("/predict/winner", json={"home": "spain", "away": "france", "n": 50000})
    assert r.status_code == 200
    data = r.json()
    total = data["home_win_pct"] + data["draw_pct"] + data["away_win_pct"]
    assert abs(total - 100.0) < 0.5
    app.dependency_overrides.clear()
