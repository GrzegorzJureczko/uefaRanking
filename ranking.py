import json
from pathlib import Path
import requests
import os

url = "https://api.rankingiuefa.pl/"
OVERRIDES_PATH = Path(__file__).resolve().parent / "club_name_overrides.json"

def load_club_name_overrides():
    """Load optional manual club name overrides from JSON."""
    try:
        with OVERRIDES_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"Error loading club name overrides: {e}")
        return {}


def apply_club_name_overrides(ranking_dict, overrides):
    """Apply manual name overrides to the extracted UEFA ranking dictionary."""
    if not overrides or not isinstance(overrides, dict):
        return ranking_dict

    for original_name, override_name in overrides.items():
        if not original_name or not override_name or original_name == override_name:
            continue

        if original_name not in ranking_dict:
            continue

        if override_name in ranking_dict:
            print(
                f"Override skipped: target name '{override_name}' already exists in ranking data."
            )
            continue

        ranking_dict[override_name] = ranking_dict.pop(original_name)

    return ranking_dict


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
            'country': club.get('country', 'Unknown'),
            'total': club.get('total', 0),
            'years': years
        }
    return ranking_dict


def get_uefa_points():
    """Main function to get all UEFA points data"""
    rank = getUEFARanking(2026)
    ranking = ExtractRanking(rank)
    overrides = load_club_name_overrides()
    return apply_club_name_overrides(ranking, overrides)


if __name__ == "__main__":
    raw_rank = get_uefa_points()
    print(raw_rank)

