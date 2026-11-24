import unittest

from main import get_league_uefa_summary


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


if __name__ == "__main__":
    unittest.main()
