import requests
import os

url = "https://api.rankingiuefa.pl/"

def getUEFARanking(baseYear):
    """Fetch UEFA ranking data from the API"""
    try:
        response = requests.get(url + f"/clubs/five-years/{baseYear}", timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching UEFA ranking: {e}")
        return None


def ExtractRanking(json_data):
    """Extract club rankings from API response"""
    if not json_data or 'rows' not in json_data:
        return {}
    
    ranking_dict = {}
    for club in json_data['rows']:
        ranking_dict[club['club']] = club['total']
    return ranking_dict


def get_uefa_points():
    """Main function to get all UEFA points data"""
    rank = getUEFARanking(2026)
    return ExtractRanking(rank)


if __name__ == "__main__":
    raw_rank = get_uefa_points()
    print(raw_rank)

