import json
import http.client
import os

# Credentials for the free-api-live-football-data API
RAPIDAPI_HOST = "free-api-live-football-data.p.rapidapi.com"
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "aa0f9d7724msh696a52e2cb168ccp128165jsn36e76705848d")


def get_league_standings(league_id=196):
    """
    Fetch league standings from the API
    league_id=196 corresponds to Premier League
    """
    try:
        conn = http.client.HTTPSConnection(RAPIDAPI_HOST)
        
        headers = {
            'x-rapidapi-host': RAPIDAPI_HOST,
            'Content-Type': "application/json",
            "X-RapidAPI-Key": RAPIDAPI_KEY
        }
        
        conn.request("GET", f"/football-get-standing-all?leagueid={league_id}", headers=headers)
        
        res = conn.getresponse()
        data = res.read()
        
        standings = json.loads(data.decode("utf-8"))
        conn.close()
        
        return standings
    except Exception as e:
        print(f"Error fetching standings: {e}")
        return None


def extract_standings(json_data):
    """
    Extract relevant standing information from API response
    Returns a list of dicts with club info
    """
    if not json_data or 'response' not in json_data:
        return []
    
    standings_list = []
    for item in json_data['response']['standing']:
        club_info = {
            'name': item.get('name', 'Unknown'),
            'short_name': item.get('shortName', ''),
            'played': item.get('played', 0),
            'wins': item.get('wins', 0),
            'draws': item.get('draws', 0),
            'losses': item.get('losses', 0),
            'goals_for': item.get('scoresStr', '0-0').split('-')[0],
            'goals_against': item.get('scoresStr', '0-0').split('-')[1],
            'goal_diff': item.get('goalConDiff', 0),
            'points': item.get('pts', 0),
            'position': item.get('idx', 0)
        }
        standings_list.append(club_info)
    
    return standings_list


def get_all_standings():
    """Main function to get all standings data"""
    standings_data = get_league_standings()
    return extract_standings(standings_data)


if __name__ == "__main__":
    standings = get_all_standings()
    for club in standings:
        print(f"{club['position']}. {club['name']}: {club['points']} pts ({club['played']} matches)")
