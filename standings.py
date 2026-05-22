import json
import requests

SPORTSDB_HEADERS = {
    "apikey": "6676965455"
}

# Map existing league IDs to TheSportsDB league IDs.
# Only English Premier League is mapped here; add more mappings as needed.
LEAGUE_ID_MAP = {
    47: 4328,
    55: 4332,  
    87: 4335,
    54: 4331,
    53: 4334,
    61: 4344,
    57: 4337,
    40: 4338,
    71: 4339,
    122: 4631,
    135: 4336,
    196: 4422,
    46: 4340,
    59: 4358,
    136: 4630,
    69: 4675,
    38: 4621,
    64: 4330,
    67: 4347,
    252: 4629,
}


def get_league_standings(league_id):
    """
    Fetch league standings from TheSportsDB API.
    league_id: Local league ID used by the app.
    """
    sportsdb_league_id = LEAGUE_ID_MAP.get(league_id)
    if sportsdb_league_id is None:
        print(f"No SportsDB mapping for league ID {league_id}")
        return None

    api_key = SPORTSDB_HEADERS.get("apikey")
    if not api_key:
        print("No SportsDB API key configured in SPORTSDB_HEADERS")
        return None

    url = f"https://www.thesportsdb.com/api/v1/json/{api_key}/lookuptable.php?l={sportsdb_league_id}"
    try:
        response = requests.get(url, timeout=20)
        print(f"API Response Status: {response.status_code} {response.reason}")
        response.raise_for_status()
        print(f"API Response Content: {response.text[:500]}")  # Print first 500 chars for debugging

        standings = response.json()
        if not isinstance(standings, dict) or "table" not in standings:
            print(f"Unexpected response format for league {league_id}")
            return None

        return standings
    except Exception as e:
        print(f"Error fetching standings: {e}")
        return None


def extract_standings(json_data):
    """
    Extract relevant standing information from TheSportsDB response.
    Returns a list of dicts with club info.
    """
    if not json_data or "table" not in json_data:
        return []

    standings_list = []
    for item in json_data["table"]:
        club_info = {
            "name": item.get("strTeam", "Unknown"),
            "short_name": item.get("strTeam", ""),
            "played": int(item.get("intPlayed") or 0),
            "wins": int(item.get("intWin") or 0),
            "draws": int(item.get("intDraw") or 0),
            "losses": int(item.get("intLoss") or 0),
            "goals_for": int(item.get("intGoalsFor") or 0),
            "goals_against": int(item.get("intGoalsAgainst") or 0),
            "goal_diff": int(item.get("intGoalDifference") or 0),
            "points": int(item.get("intPoints") or 0),
            "position": int(item.get("intRank") or 0)
        }
        standings_list.append(club_info)

    return standings_list


def get_all_standings(league_id=196):
    """Main function to get all standings data for a specific league"""
    standings_data = get_league_standings(league_id)
    if standings_data is None:
        return []

    return extract_standings(standings_data)


if __name__ == "__main__":
    print("Fetching league standings...")
    standings = get_all_standings(47)
    for club in standings:
        print(f"{club['position']}. {club['name']}: {club['points']} pts ({club['played']} matches)")
