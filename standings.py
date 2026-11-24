import requests

FOTMOB_URL = "https://www.fotmob.com/api/data/tltable"
FOTMOB_HEADERS = {"User-Agent": "Mozilla/5.0"}


def get_league_standings(league_id):
    """
    Fetch league standings from FotMob (free, no API key).
    league_id: League ID used by the app, which is also the FotMob league ID.
    """
    try:
        response = requests.get(
            FOTMOB_URL, params={"leagueId": league_id}, headers=FOTMOB_HEADERS, timeout=20
        )
        print(f"API Response Status: {response.status_code} {response.reason}")
        response.raise_for_status()

        payload = response.json()
        data = payload[0].get("data") if isinstance(payload, list) and payload else None
        if not isinstance(data, dict):
            print(f"Unexpected response format for league {league_id}")
            return None

        return data
    except Exception as e:
        print(f"Error fetching standings: {e}")
        return None


def _table_rows(data):
    """Return the 'all' table rows, also handling leagues split into several tables."""
    table = data.get("table")
    if isinstance(table, dict) and table.get("all"):
        return table["all"]

    for group in data.get("tables") or []:
        rows = (group.get("table") or {}).get("all")
        if rows:
            return rows
    return []


def extract_standings(data):
    """
    Extract relevant standing information from a FotMob table response.
    Returns a list of dicts with club info.
    """
    if not data:
        return []

    standings_list = []
    for item in _table_rows(data):
        goals_for, goals_against = 0, 0
        try:
            goals_for, goals_against = (int(x) for x in str(item.get("scoresStr", "")).split("-"))
        except ValueError:
            pass

        standings_list.append({
            "name": item.get("name", "Unknown"),
            "short_name": item.get("shortName") or item.get("name", ""),
            "played": int(item.get("played") or 0),
            "wins": int(item.get("wins") or 0),
            "draws": int(item.get("draws") or 0),
            "losses": int(item.get("losses") or 0),
            "goals_for": goals_for,
            "goals_against": goals_against,
            "goal_diff": int(item.get("goalConDiff") or 0),
            "points": int(item.get("pts") or 0),
            "position": int(item.get("idx") or 0)
        })

    return standings_list


def get_all_standings(league_id=196):
    """Main function to get all standings data for a specific league"""
    data = get_league_standings(league_id)
    if data is None:
        return []

    return extract_standings(data)
    return clubs


if __name__ == "__main__":
    print("Fetching league standings...")
    standings = get_all_standings(47)
    for club in standings:
        print(f"{club['position']}. {club['name']}: {club['points']} pts ({club['played']} matches)")
