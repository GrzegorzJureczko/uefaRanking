import unittest

from main import (
    calculate_country_efficiency,
    calculate_points_efficiency,
    european_participants,
    get_league_uefa_summary,
)


class LeaguePointsSummaryTests(unittest.TestCase):
    def test_get_league_uefa_summary_sums_matching_club_points(self):
        uefa_points = {
            "Arsenal": {"total": 81.0, "years": {"2022": 0, "2023": 17, "2024": 22, "2025": 36, "2026": 6}},
            "Liverpool": {"total": 107.5, "years": {"2022": 33, "2023": 19, "2024": 20, "2025": 29.5, "2026": 6}},
        }
        standings = [
            {"name": "Arsenal", "points": 79},
            {"name": "Liverpool", "points": 59},
        ]

        summary = get_league_uefa_summary("47", uefa_points, standings, "England")

        self.assertEqual(summary["total"], 188.5)
        self.assertEqual(summary["years"]["2022"], 33)
        self.assertEqual(summary["years"]["2023"], 36)
        self.assertEqual(summary["years"]["2025"], 65.5)

    def test_calculate_points_efficiency_counts_only_qualified_clubs(self):
        clubs = [
            {"uefa_points_total": 60.0, "qualification": {"title": "Champions League", "color": "#000"}},
            {"uefa_points_total": 20.0, "qualification": None},
            {"uefa_points_total": "-", "qualification": None},
        ]

        result = calculate_points_efficiency(clubs)

        self.assertEqual(result, {"percent": 75.0, "qualified": 60.0, "total": 80.0})

    def test_calculate_points_efficiency_without_points(self):
        self.assertIsNone(calculate_points_efficiency([])["percent"])

    def test_calculate_points_efficiency_without_qualification_data(self):
        clubs = [{"uefa_points_total": 50.0, "qualification": None}]

        self.assertIsNone(calculate_points_efficiency(clubs)["percent"])

    def test_calculate_country_efficiency_uses_all_clubs_of_the_country(self):
        uefa_points = {
            "Slavia Prague": {"country": "Czech Republic", "total": 30.0},
            "Opava": {"country": "Czech Republic", "total": 10.0},
            "Arsenal": {"country": "England", "total": 80.0},
        }

        result = calculate_country_efficiency(uefa_points, "Czech Republic", {"Slavia Prague", "Arsenal"})

        self.assertEqual(result, {"percent": 75.0, "qualified": 30.0, "total": 40.0})

    def test_calculate_country_efficiency_without_clubs(self):
        self.assertIsNone(calculate_country_efficiency({}, "Poland", {"X"})["percent"])

    def test_european_participants_use_matches_or_points_of_the_season(self):
        uefa_points = {
            "A": {"matches": {"2020": 8}, "years": {"2020": 0}},
            "B": {"matches": {"2020": 0}, "years": {"2020": 1.5}},
            "C": {"matches": {"2020": 0}, "years": {"2020": 0}},
            "D": {"matches": {"2019": 6}, "years": {"2019": 4}},
        }

        self.assertEqual(european_participants(uefa_points, 2020), {"A", "B"})


if __name__ == "__main__":
    unittest.main()
