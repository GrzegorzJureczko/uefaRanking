import unittest

from main import calculate_points_efficiency, get_league_uefa_summary


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


if __name__ == "__main__":
    unittest.main()
