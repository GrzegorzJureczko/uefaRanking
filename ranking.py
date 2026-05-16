import requests
import os
from cache import get_cache, set_cache

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
        # Keep total and per-year breakdown if available
        years = club.get('years', {}) if isinstance(club.get('years', {}), dict) else {}
        ranking_dict[club['club']] = {
            'total': club.get('total', 0),
            'years': years
        }
    return ranking_dict


def get_uefa_points():
    """Main function to get all UEFA points data (cached daily)"""
    cache_key = "uefa_points_2026"
    cached = get_cache(cache_key, ttl_seconds=24*3600)
    if cached is not None:
        return cached

    rank = getUEFARanking(2026)
    ranking = ExtractRanking(rank)
    # store parsed ranking in cache
    set_cache(cache_key, ranking)
    return ranking


if __name__ == "__main__":
    raw_rank = get_uefa_points()
    print(raw_rank)

