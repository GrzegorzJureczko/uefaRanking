import json
from pathlib import Path
import requests
import os
import time

url = "https://comp.uefa.com/v2/coefficients"
PAGE_SIZE = 500
# UEFA country names that differ from the ones used in LEAGUES (main.py)
COUNTRY_ALIASES = {"Czechia": "Czech Republic", "Türkiye": "Turkey"}
OVERRIDES_PATH = Path(__file__).resolve().parent / "club_name_overrides.json"
CACHE_PATH = Path(__file__).resolve().parent / "data" / "cache.json"
CACHE_KEY = "uefa_points_2026"

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
    """Fetch the 5-year UEFA club coefficient ranking (all pages) from the official UEFA API"""
    members = []
    page = 1
    try:
        while True:
            response = requests.get(
                url,
                params={
                    "coefficientType": "MEN_CLUB",
                    "coefficientRange": "OVERALL",
                    "seasonYear": baseYear,
                    "page": page,
                    "pagesize": PAGE_SIZE,
                    "language": "EN",
                },
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15,
            )
            response.raise_for_status()
            batch = response.json().get("data", {}).get("members", [])
            members.extend(batch)
            if len(batch) < PAGE_SIZE:
                return members
            page += 1
    except (requests.exceptions.RequestException, ValueError) as e:
        print(f"Error fetching UEFA ranking: {e}")
        return None


def ExtractRanking(members):
    """Convert UEFA API members into {club: {country, total, years}}"""
    if not members:
        return {}

    ranking_dict = {}
    for entry in members:
        member = entry.get('member', {})
        overall = entry.get('overallRanking', {})
        name = member.get('displayName')
        if not name:
            continue
        country = member.get('countryName', 'Unknown')
        years = {
            str(season['seasonYear']): season.get('totalPoints', 0)
            for season in entry.get('seasonRankings', [])
            if 'seasonYear' in season
        }
        ranking_dict[name] = {
            'country': COUNTRY_ALIASES.get(country, country),
            'total': overall.get('totalPoints', 0),
            'years': years
        }
    return ranking_dict


def load_cached_ranking():
    """Load the last saved UEFA ranking snapshot (already extracted format)."""
    try:
        with CACHE_PATH.open("r", encoding="utf-8") as file:
            return json.load(file).get(CACHE_KEY, {}).get("data", {})
    except (FileNotFoundError, ValueError, AttributeError) as e:
        print(f"Error loading cached UEFA ranking: {e}")
        return {}


def save_cached_ranking(ranking):
    """Store the freshly fetched UEFA ranking, keeping other cache entries intact."""
    try:
        try:
            with CACHE_PATH.open("r", encoding="utf-8") as file:
                cache = json.load(file)
        except (FileNotFoundError, ValueError):
            cache = {}
        cache[CACHE_KEY] = {"ts": int(time.time()), "data": ranking}
        with CACHE_PATH.open("w", encoding="utf-8") as file:
            json.dump(cache, file, ensure_ascii=False)
    except OSError as e:
        print(f"Error saving UEFA ranking cache: {e}")


def get_uefa_points():
    """Main function to get all UEFA points data"""
    rank = getUEFARanking(2026)
    ranking = ExtractRanking(rank)
    if ranking:
        save_cached_ranking(ranking)
    else:
        print("UEFA ranking API unavailable, using cached snapshot.")
        ranking = load_cached_ranking()
    overrides = load_club_name_overrides()
    return apply_club_name_overrides(ranking, overrides)


if __name__ == "__main__":
    raw_rank = get_uefa_points()
    print(raw_rank)

