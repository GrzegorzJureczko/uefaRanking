import json
from pathlib import Path
import requests

from cache import ttl_cache
from http_session import session

url = "https://comp.uefa.com/v2/coefficients"
PAGE_SIZE = 500
BASE_YEAR = 2027
# The current season changes while it is played; finished seasons practically never do
CURRENT_SEASON_CACHE_TTL = 3600
HISTORIC_SEASON_CACHE_TTL = 24 * 3600
# Oldest season with both UEFA coefficients (from 2005) and FotMob standings (from 2010/11)
MIN_YEAR = 2011
# UEFA country names that differ from the ones used in LEAGUES (main.py)
COUNTRY_ALIASES = {"Czechia": "Czech Republic", "Türkiye": "Turkey"}
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


def season_cache_ttl(season_year=None):
    """Cache lifetime (seconds) of data for a season ending in season_year (None means the current season)."""
    if season_year is None or season_year == BASE_YEAR:
        return CURRENT_SEASON_CACHE_TTL
    return HISTORIC_SEASON_CACHE_TTL


def getUEFARanking(baseYear):
    """Fetch the 5-year UEFA club coefficient ranking (all pages) from the official UEFA API"""
    members = []
    page = 1
    try:
        while True:
            response = session.get(
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
        matches = {
            str(season['seasonYear']): season.get('numberOfMatches') or 0
            for season in entry.get('seasonRankings', [])
            if 'seasonYear' in season
        }
        ranking_dict[name] = {
            'country': COUNTRY_ALIASES.get(country, country),
            'total': overall.get('totalPoints', 0),
            'years': years,
            'matches': matches
        }
    return ranking_dict


def fill_missing_years(ranking, base_year):
    """Give every club all 5 ranking seasons (oldest first), using 0 for seasons without European games."""
    seasons = [str(year) for year in range(base_year - 4, base_year + 1)]
    for club in ranking.values():
        years = club.get('years') or {}
        club['years'] = {season: years.get(season, 0.0) for season in seasons}
    return ranking


@ttl_cache(season_cache_ttl)
def get_uefa_points(base_year=BASE_YEAR):
    """Main function to get all UEFA points data (5 seasons ending in base_year)"""
    rank = getUEFARanking(base_year)
    ranking = ExtractRanking(rank)
    ranking = fill_missing_years(ranking, base_year)
    overrides = load_club_name_overrides()
    return apply_club_name_overrides(ranking, overrides)


if __name__ == "__main__":
    raw_rank = get_uefa_points()
    print(raw_rank)

