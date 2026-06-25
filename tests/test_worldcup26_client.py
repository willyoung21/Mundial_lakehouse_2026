"""Tests for worldcup26_client.py — pure functions only, no HTTP calls."""

from unittest.mock import patch

import pandas as pd

from ingestion.worldcup26_client import (
    _derive_league_round,
    _parse_int,
    _parse_local_date,
    _to_bool,
    fetch_fixtures,
)


class TestParseLocalDate:
    def test_standard_format(self):
        assert _parse_local_date("06/11/2026 18:00") == "2026-06-11"

    def test_single_digit_day_month(self):
        assert _parse_local_date("6/9/2026 20:00") == "2026-06-09"

    def test_returns_first_10_chars_on_error(self):
        assert _parse_local_date("2026-06-11") == "2026-06-11"

    def test_handles_no_time(self):
        assert _parse_local_date("12/31/2026") == "2026-12-31"


class TestParseInt:
    def test_numeric_string(self):
        assert _parse_int("3") == 3

    def test_none_input(self):
        assert _parse_int(None) is None

    def test_empty_string(self):
        assert _parse_int("") is None

    def test_null_string(self):
        assert _parse_int("null") is None

    def test_already_int(self):
        assert _parse_int(5) == 5

    def test_non_numeric_string(self):
        assert _parse_int("abc") is None

    def test_whitespace(self):
        assert _parse_int("  2  ") == 2


class TestToBool:
    def test_true_string(self):
        assert _to_bool("TRUE") is True

    def test_false_string(self):
        assert _to_bool("FALSE") is False

    def test_bool_passthrough(self):
        assert _to_bool(True) is True
        assert _to_bool(False) is False

    def test_numeric_strings(self):
        assert _to_bool("1") is True
        assert _to_bool("0") is False


class TestDeriveLeagueRound:
    def test_group_stage(self):
        assert _derive_league_round({"type": "group", "group": "A"}) == "Group A"

    def test_group_stage_no_group(self):
        assert _derive_league_round({"type": "group"}) == "Group Stage"

    def test_round_of_16(self):
        assert _derive_league_round({"type": "round_of_16"}) == "Round of 16"

    def test_final(self):
        assert _derive_league_round({"type": "final"}) == "Final"

    def test_semi_final(self):
        assert _derive_league_round({"type": "semi_final"}) == "Semi-final"

    def test_quarter_final(self):
        assert _derive_league_round({"type": "quarter_final"}) == "Quarter-final"

    def test_unknown_type_title_case(self):
        result = _derive_league_round({"type": "third_place"})
        assert result == "3rd Place Final"


class TestFetchFixtures:
    """Tests for fetch_fixtures with mocked curl."""

    FAKE_GAMES = [
        {
            "id": "1",
            "local_date": "06/20/2026 18:00",
            "home_team_name": "Spain",
            "away_team_name": "Germany",
            "home_team_id": "10",
            "away_team_id": "11",
            "home_score": "1",
            "away_score": "1",
            "type": "group",
            "group": "B",
            "referee": "Referee Name",
            "stadium_id": "5",
        },
        {
            "id": "2",
            "local_date": "06/21/2026 20:00",  # different date → excluded
            "home_team_name": "France",
            "away_team_name": "Brazil",
            "home_team_id": "20",
            "away_team_id": "21",
            "home_score": None,
            "away_score": None,
            "type": "group",
            "group": "C",
        },
    ]

    @patch("ingestion.worldcup26_client._curl")
    def test_filters_by_date(self, mock_curl):
        mock_curl.return_value = self.FAKE_GAMES
        df = fetch_fixtures("2026-06-20", jwt="token", stadiums={})
        assert len(df) == 1
        assert df.iloc[0]["home_team_name"] == "Spain"

    @patch("ingestion.worldcup26_client._curl")
    def test_output_schema(self, mock_curl):
        mock_curl.return_value = self.FAKE_GAMES
        df = fetch_fixtures("2026-06-20", jwt="token", stadiums={})
        required_cols = {
            "fixture_id",
            "date",
            "status",
            "home_team_name",
            "away_team_name",
            "goals_home",
            "goals_away",
            "league_round",
        }
        assert required_cols.issubset(set(df.columns))

    @patch("ingestion.worldcup26_client._curl")
    def test_finished_status_by_scores(self, mock_curl):
        mock_curl.return_value = self.FAKE_GAMES
        df = fetch_fixtures("2026-06-20", jwt="token", stadiums={})
        # Game has scores → should be 'Match Finished'
        assert df.iloc[0]["status"] == "Match Finished"

    @patch("ingestion.worldcup26_client._curl")
    def test_scheduled_status_when_no_scores(self, mock_curl):
        # Game on 2026-06-21 has no scores → Scheduled
        mock_curl.return_value = self.FAKE_GAMES
        df = fetch_fixtures("2026-06-21", jwt="token", stadiums={})
        assert len(df) == 1
        assert df.iloc[0]["status"] == "Scheduled"

    @patch("ingestion.worldcup26_client._curl")
    def test_stadium_lookup_used(self, mock_curl):
        mock_curl.return_value = self.FAKE_GAMES
        stadiums = {"5": {"name": "SoFi Stadium", "city": "Los Angeles"}}
        df = fetch_fixtures("2026-06-20", jwt="token", stadiums=stadiums)
        assert df.iloc[0]["venue_name"] == "SoFi Stadium"

    @patch("ingestion.worldcup26_client._curl")
    def test_empty_result_on_date_with_no_games(self, mock_curl):
        mock_curl.return_value = self.FAKE_GAMES
        df = fetch_fixtures("2026-07-01", jwt="token", stadiums={})
        assert len(df) == 0
        assert isinstance(df, pd.DataFrame)
