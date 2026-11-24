from flask import Flask, render_template, jsonify, request
from ranking import get_uefa_points
from standings import get_all_standings
from difflib import SequenceMatcher
from pathlib import Path
import logging
import os
import json
import re
import unicodedata

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# League configuration with IDs and names
LEAGUES = {
    '47': {'name': 'English Premier League', 'code': 'en', 'id': 47, 'country': 'England'},
    '55': {'name': 'Italian Serie A', 'code': 'it', 'id': 55, 'country': 'Italy'},
    '87': {'name': 'Spanish La Liga', 'code': 'es', 'id': 87, 'country': 'Spain'},
    '54': {'name': 'German Bundesliga', 'code': 'de', 'id': 54, 'country': 'Germany'},
    '53': {'name': 'French Ligue 1', 'code': 'fr', 'id': 53, 'country': 'France'},
    '61': {'name': 'Portuguese Liga Portugal', 'code': 'pt', 'id': 61, 'country': 'Portugal'},
    '57': {'name': 'Dutch Eredivisie', 'code': 'nl', 'id': 57, 'country': 'Netherlands'},
    '40': {'name': 'Belgian First Division A', 'code': 'be', 'id': 40, 'country': 'Belgium'},
    '71': {'name': 'Turkish Super League', 'code': 'tr', 'id': 71, 'country': 'Turkey'},
    '122': {'name': 'Czech First League', 'code': 'cz', 'id': 122, 'country': 'Czech Republic'},
    '135': {'name': 'Greek Super League 1', 'code': 'gr', 'id': 135, 'country': 'Greece'},
    '196': {'name': 'Polish Ekstraklasa', 'code': 'pl', 'id': 196, 'country': 'Poland'},
    '46': {'name': 'Danish Superligaen', 'code': 'dk', 'id': 46, 'country': 'Denmark'},
    '59': {'name': 'Norwegian Eliteserien', 'code': 'no', 'id': 59, 'country': 'Norway'},
    '38': {'name': 'Austrian Bundesliga', 'code': 'at', 'id': 38, 'country': 'Austria'},
    '64': {'name': 'Scottish Premiership', 'code': 'sc', 'id': 64, 'country': 'Scotland'},
    '67': {'name': 'Swedish Allsvenskan', 'code': 'se', 'id': 67, 'country': 'Sweden'},
    '252': {'name': 'Croatian HNL', 'code': 'hr', 'id': 252, 'country': 'Croatia'},
}


NAME_NOISE_TOKENS = {'fc', 'afc', 'sc', 'ac', 'cf', 'sad', 'fk', 'bsc', 'sk', 'the', 'and'}
# Spellings used by UEFA or the standings source that normalization can't reconcile
NAME_ALIASES = {
    r'\bman\b': 'manchester',
    r'\batleti\b': 'atletico madrid',
    r"\bnott'm\b": 'nottingham',
    r'\bheart of midlothian\b': 'hearts',
    r'\bdinamo zagreb\b': 'gnk dinamo',
}


def _name_tokens(name):
    """Lowercase, accent-free word tokens without generic club-name noise (FC, AFC, '&', ...)."""
    folded = unicodedata.normalize('NFKD', name.lower())
    folded = ''.join(ch for ch in folded if not unicodedata.combining(ch))
    for pattern, replacement in NAME_ALIASES.items():
        folded = re.sub(pattern, replacement, folded)
    tokens = re.findall(r'[a-z0-9]+', folded)
    return [t for t in tokens if t not in NAME_NOISE_TOKENS and len(t) > 1 and not t.isdigit()]


def name_similarity(standing_name, uefa_name):
    """
    Similarity of two club names in 0..1. Uses fuzzy matching on normalized names and
    treats a name whose words are all contained in the other (e.g. 'Leverkusen' vs
    'Bayer Leverkusen') as a strong match.
    """
    a, b = _name_tokens(standing_name), _name_tokens(uefa_name)
    if not a or not b:
        return SequenceMatcher(None, standing_name.lower(), uefa_name.lower()).ratio()
    ratio = SequenceMatcher(None, ' '.join(a), ' '.join(b)).ratio()
    if set(a) <= set(b) or set(b) <= set(a):
        ratio = max(ratio, 0.9)
    return ratio


def fuzzy_match_clubs(uefa_clubs, standings_clubs, league_country=None):
    """
    Match clubs from both datasets using fuzzy string matching.
    Returns a mapping of standings club names to UEFA club names.
    If league_country is provided, only match clubs whose UEFA country matches it.
    """
    mapping = {}
    league_country_lower = league_country.lower() if league_country else None
    
    for standing_club in standings_clubs:
        best_match = None
        best_ratio = 0
        
        for uefa_name, uefa_val in uefa_clubs.items():
            if league_country_lower:
                uefa_country = ''
                if isinstance(uefa_val, dict):
                    uefa_country = str(uefa_val.get('country', '')).lower()
                # Cached snapshots may lack the country; don't filter those out
                if uefa_country and uefa_country != league_country_lower:
                    continue
            ratio = name_similarity(standing_club['name'], uefa_name)
            
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = uefa_name
        
        # Only match if similarity is high enough (80%)
        if best_ratio > 0.8:
            mapping[standing_club['name']] = best_match
    print(f"Fuzzy matching results: {mapping}")
    return mapping


def get_league_uefa_summary(league_id, uefa_points, standings_data, league_country=None):
    """Calculate a league-level UEFA points summary from matched clubs."""
    if not isinstance(uefa_points, dict):
        return {"total": "-", "years": {}}

    league_country_lower = league_country.lower() if league_country else None
    yearly_totals = {}
    matched_total = 0.0

    for club in standings_data:
        club_name = club.get("name")
        if not club_name:
            continue

        matched_name = None
        best_ratio = 0.0
        for uefa_name, uefa_val in uefa_points.items():
            if not isinstance(uefa_name, str):
                continue
            if league_country_lower and isinstance(uefa_val, dict):
                uefa_country = str(uefa_val.get('country', '')).lower()
                if uefa_country and uefa_country != league_country_lower:
                    continue
            ratio = name_similarity(club_name, uefa_name)
            if ratio > best_ratio:
                best_ratio = ratio
                matched_name = uefa_name

        if matched_name is None:
            continue

        if best_ratio <= 0.7:
            continue

        uefa_val = uefa_points.get(matched_name)
        if isinstance(uefa_val, dict):
            years = uefa_val.get('years', {}) if isinstance(uefa_val.get('years', {}), dict) else {}
            for year, value in years.items():
                year_total = yearly_totals.get(year, 0.0) + float(value)
                yearly_totals[year] = year_total
            total = uefa_val.get('total', 0)
            if isinstance(total, (int, float)):
                matched_total += float(total)

    if not yearly_totals and matched_total == 0.0:
        return {"total": "-", "years": {}}

    if matched_total == 0.0 and yearly_totals:
        matched_total = sum(yearly_totals.values())

    return {
        "total": round(matched_total, 2),
        "years": {year: round(total, 2) for year, total in sorted(yearly_totals.items())}
    }


def get_cached_standings(league_id):
    """Load standings from the local JSON cache when available."""
    cache_path = Path(__file__).resolve().parent / "data" / "standings" / f"standings_{league_id}.json"
    if not cache_path.exists():
        return None

    try:
        with cache_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return None

    clubs = payload.get("clubs") if isinstance(payload, dict) else None
    if not isinstance(clubs, list):
        return None

    return clubs


def build_league_summaries(uefa_points, current_league_id=None, current_standings=None):
    """Build a summary dictionary for all leagues for the menu."""
    summaries = {}
    for league_id in LEAGUES:
        standings_data = current_standings if current_league_id and league_id == current_league_id else get_cached_standings(league_id)
        if standings_data is None:
            standings_data = []
        league_info = LEAGUES[league_id]
        summaries[league_id] = get_league_uefa_summary(
            league_id,
            uefa_points,
            standings_data,
            league_info.get("country"),
        )
    return summaries


def merge_club_data(uefa_points, standings_data, league_country=None):
    """
    Merge UEFA points data with league standings data.
    Returns a list of clubs with combined information.
    """
    # Create mapping between standings club names and UEFA club names
    club_mapping = fuzzy_match_clubs(uefa_points, standings_data, league_country)
    
    merged_data = []
    for club in standings_data:
        club_name = club['name']
        uefa_club_name = club_mapping.get(club_name)

        # Default UEFA values when not matched
        uefa_total = '-'
        uefa_years = {}
        if uefa_club_name:
            uefa_val = uefa_points.get(uefa_club_name)
            if isinstance(uefa_val, dict):
                uefa_total = uefa_val.get('total', '-')
                uefa_years = uefa_val.get('years', {})
            else:
                # backward compatibility if it's a scalar
                uefa_total = uefa_val

        merged_club = {
            'position': club['position'],
            'name': club_name,
            'short_name': club['short_name'],
            'played': club['played'],
            'wins': club['wins'],
            'draws': club['draws'],
            'losses': club['losses'],
            'goals_for': club['goals_for'],
            'goals_against': club['goals_against'],
            'goal_diff': club['goal_diff'],
            'season_points': club['points'],
            'uefa_points_total': uefa_total,
            'uefa_points_years': uefa_years,
            'matched': uefa_club_name is not None
        }
        merged_data.append(merged_club)
    
    return merged_data


@app.route("/")
def index():
    """Show league selector"""
    try:
        uefa_points = get_uefa_points()
        if not uefa_points:
            uefa_points = {}
        league_summaries = build_league_summaries(uefa_points)
        return render_template("index.html", leagues=LEAGUES, selected_league=None, clubs=[], league_summary={}, league_summaries=league_summaries)
    except Exception as e:
        logger.error(f"Error in index: {e}", exc_info=True)
        return render_template("index.html", leagues=LEAGUES, selected_league=None, clubs=[], league_summary={}, league_summaries={}, error=str(e))


@app.route("/league/<league_id>")
def league_standings(league_id):
    """Show standings for a specific league"""
    try:
        if league_id not in LEAGUES:
            return render_template("index.html", leagues=LEAGUES, selected_league=None, clubs=[], league_summary={}, league_summaries={},
                                 error="Invalid league selected")
        
        logger.info(f"Fetching data for league {LEAGUES[league_id]['name']}...")
        
        # Fetch both datasets
        uefa_points = get_uefa_points()
        standings = get_all_standings(int(league_id))
        
        error_message = None
        if not uefa_points:
            logger.warning("Failed to fetch UEFA points")
            uefa_points = {}
        
        if not standings:
            error_message = f"Failed to fetch standings for {LEAGUES[league_id]['name']}. The league may not be supported by the API."
            logger.warning(error_message)
            standings = []
        
        # Merge the data
        merged_data = merge_club_data(uefa_points, standings, LEAGUES[league_id]['country'])
        league_summary = get_league_uefa_summary(league_id, uefa_points, standings, LEAGUES[league_id]['country'])
        league_summaries = build_league_summaries(uefa_points, current_league_id=league_id, current_standings=standings)
        
        logger.info(f"Successfully fetched and merged data for {len(merged_data)} clubs")
        
        return render_template(
            "index.html",
            clubs=merged_data,
            leagues=LEAGUES,
            selected_league=league_id,
            league_name=LEAGUES[league_id]['name'],
            league_summary=league_summary,
            league_summaries=league_summaries,
            error=error_message
        )
    
    except Exception as e:
        logger.error(f"Error in league_standings: {e}", exc_info=True)
        return render_template("index.html", leagues=LEAGUES, selected_league=league_id, 
                             clubs=[], league_summary={}, league_summaries={}, error=str(e))


@app.route("/api/clubs/<league_id>")
def get_clubs_api(league_id):
    """API endpoint to get clubs data as JSON for a specific league"""
    try:
        if league_id not in LEAGUES:
            return jsonify({"error": "Invalid league ID"}), 400
        
        uefa_points = get_uefa_points()
        standings = get_all_standings(int(league_id))
        
        if not uefa_points:
            uefa_points = {}
        if not standings:
            standings = []
        
        merged_data = merge_club_data(uefa_points, standings, LEAGUES[league_id]['country'])
        return jsonify({
            "league": LEAGUES[league_id],
            "clubs": merged_data
        })
    
    except Exception as e:
        logger.error(f"Error in get_clubs_api: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)