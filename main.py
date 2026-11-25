from flask import Flask, render_template, jsonify, request
from cache import TTLCache
from ranking import get_uefa_points, season_cache_ttl, BASE_YEAR, MIN_YEAR, CURRENT_SEASON_CACHE_TTL, HISTORIC_SEASON_CACHE_TTL
from standings import get_all_standings, get_top_leagues, FOTMOB_COUNTRY_ALIASES
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
import logging
import os
import re
import threading
import time
import unicodedata

app = Flask(__name__)

# Background cache warm-up: pause between seasons (be gentle to FotMob), check interval and refresh lead time (seconds)
WARMUP_PAUSE = 1
WARMUP_TICK = 300
WARMUP_REFRESH_MARGIN = 600

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


MATCH_THRESHOLD = 0.8


def fuzzy_match_clubs(uefa_clubs, standings_clubs, league_country=None):
    """
    Match clubs from both datasets using fuzzy string matching.
    Returns a mapping of standings club names to UEFA club names.
    If league_country is provided, only match clubs whose UEFA country matches it.
    """
    league_country_lower = league_country.lower() if league_country else None

    candidates = []
    for standing_club in standings_clubs:
        for uefa_name, uefa_val in uefa_clubs.items():
            if not isinstance(uefa_name, str):
                continue
            if league_country_lower and isinstance(uefa_val, dict):
                uefa_country = str(uefa_val.get('country', '')).lower()
                # Skip the country filter for clubs without a known country
                if uefa_country and uefa_country != league_country_lower:
                    continue
            ratio = name_similarity(standing_club['name'], uefa_name)
            # Only match if similarity is high enough (80%)
            if ratio > MATCH_THRESHOLD:
                candidates.append((ratio, standing_club['name'], uefa_name))

    # Best pairs first, so a UEFA club is never shared (e.g. 'Paris FC' vs 'Paris Saint-Germain')
    mapping = {}
    used_uefa = set()
    for ratio, standing_name, uefa_name in sorted(candidates, key=lambda c: -c[0]):
        if standing_name in mapping or uefa_name in used_uefa:
            continue
        mapping[standing_name] = uefa_name
        used_uefa.add(uefa_name)
    logger.info(f"Fuzzy matching results: {mapping}")
    return mapping


def get_league_uefa_summary(league_id, uefa_points, standings_data, league_country=None):
    """Calculate a league-level UEFA points summary from matched clubs."""
    if not isinstance(uefa_points, dict):
        return {"total": "-", "years": {}}

    yearly_totals = {}
    matched_total = 0.0

    named_clubs = [club for club in standings_data if club.get("name")]
    club_mapping = fuzzy_match_clubs(uefa_points, named_clubs, league_country)

    for club in named_clubs:
        matched_name = club_mapping.get(club["name"])
        if matched_name is None:
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


def parse_season():
    """Read the ?season=<ending year> query parameter, falling back to the current season."""
    season = request.args.get('season', type=int)
    if season is None or not MIN_YEAR <= season <= BASE_YEAR:
        return BASE_YEAR
    return season


def season_label(season_year):
    """Season ending in 2027 -> '2026/27'."""
    return f"{season_year - 1}/{str(season_year)[-2:]}"


def season_context(season_year):
    """Template variables for the season selector (newest season first)."""
    return {
        "season": season_year,
        "season_name": season_label(season_year),
        "seasons": [
            {"year": year, "label": season_label(year)}
            for year in range(BASE_YEAR, MIN_YEAR - 1, -1)
        ],
    }


def qualification_legend(clubs):
    """Distinct European qualification spots present in the table, in table order."""
    legend = {}
    for club in clubs:
        spot = club.get('qualification')
        if spot:
            legend.setdefault(spot['title'], spot['color'])
    return [{"title": title, "color": color} for title, color in legend.items()]


_summaries_cache = TTLCache()


def fetch_all_standings(season_year, refresh=False):
    """Standings of every league for a season, fetched in parallel (refresh bypasses the standings cache)."""
    fetch = get_all_standings.refresh if refresh else get_all_standings
    with ThreadPoolExecutor(max_workers=len(LEAGUES)) as executor:
        return dict(zip(LEAGUES, executor.map(lambda league_id: fetch(int(league_id), season_year), LEAGUES)))


def compute_league_summaries(uefa_points, standings_by_league, season_year):
    """Summaries of all leagues for the menu; complete results are cached."""
    summaries = {
        league_id: get_league_uefa_summary(
            league_id,
            uefa_points,
            standings_by_league[league_id] or [],
            LEAGUES[league_id].get("country"),
        )
        for league_id in LEAGUES
    }
    # Incomplete results (a failed fetch) are not cached so the next request retries
    if uefa_points and all(standings_by_league.values()):
        _summaries_cache.set(season_year, summaries, season_cache_ttl(season_year))
    return summaries


def build_league_summaries(uefa_points, current_league_id=None, current_standings=None, season_year=BASE_YEAR):
    """Build a summary dictionary for all leagues for the menu (standings are fetched in parallel)."""
    cached = _summaries_cache.get(season_year)
    if cached is not None:
        return cached

    standings_by_league = fetch_all_standings(season_year)
    if current_league_id in standings_by_league:
        standings_by_league[current_league_id] = current_standings
    return compute_league_summaries(uefa_points, standings_by_league, season_year)


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
            'qualification': club.get('qualification'),
            'group_name': club.get('group_name'),
            'uefa_points_total': uefa_total,
            'uefa_points_years': uefa_years,
            'matched': uefa_club_name is not None,
            'uefa_name': uefa_club_name
        }
        merged_data.append(merged_club)
    
    return merged_data


def european_participants(uefa_points, season_year):
    """
    Names of clubs that played in UEFA competitions in the season ending in season_year
    (matches are counted only for UEFA games, so domestic cup games never make a club a participant).
    Matches are not always filled in for clubs knocked out in qualifying, so any points count too.
    """
    season = str(season_year)
    return {
        name for name, club in uefa_points.items()
        if isinstance(club, dict)
        and ((club.get('matches') or {}).get(season, 0) > 0 or (club.get('years') or {}).get(season, 0) > 0)
    }


def _efficiency_result(qualified, total):
    if total <= 0:
        return {"percent": None, "qualified": 0.0, "total": 0.0}
    return {
        "percent": round(qualified / total * 100, 1),
        "qualified": round(qualified, 2),
        "total": round(total, 2),
    }


def calculate_points_efficiency(clubs):
    """
    Share of a federation's UEFA points (5-year totals) held by clubs that qualified for European
    competitions according to the league table, out of the points of all its matched league clubs.
    """
    # Without any qualification spot in the table the result would be a misleading 0%
    if not any(club.get('qualification') for club in clubs):
        return _efficiency_result(0.0, 0.0)

    total = qualified = 0.0
    for club in clubs:
        points = club.get('uefa_points_total')
        if not isinstance(points, (int, float)):
            continue
        total += points
        if club.get('qualification'):
            qualified += points
    return _efficiency_result(qualified, total)


def calculate_country_efficiency(uefa_points, country, participants):
    """
    Share of a country's UEFA points (5-year totals, all its clubs in the UEFA ranking) held by the clubs
    that played in Europe the next season (participants are UEFA club names).
    Needs neither league tables nor club name matching.
    """
    total = qualified = 0.0
    for name, club in uefa_points.items():
        if not isinstance(club, dict) or str(club.get('country', '')).lower() != country.lower():
            continue
        points = club.get('total') or 0.0
        total += points
        if name in participants:
            qualified += points
    return _efficiency_result(qualified, total)


_efficiency_cache = TTLCache()


def compute_season_efficiency(uefa_points, standings_by_league, season_year):
    """
    Points efficiency of every league for one season; complete results are cached.
    Past seasons use the clubs that actually played in Europe the next season. The current season has no
    next season yet, so it uses the European spots in the league tables.
    """
    result = {}
    if season_year < BASE_YEAR:
        participants = european_participants(get_uefa_points(season_year + 1) or {}, season_year + 1)
        if not participants:
            return {league_id: None for league_id in LEAGUES}
        for league_id, league in LEAGUES.items():
            result[league_id] = calculate_country_efficiency(uefa_points, league['country'], participants)
        _efficiency_cache.set(season_year, result, season_cache_ttl(season_year))
        return result

    complete = True
    for league_id, league in LEAGUES.items():
        standings = standings_by_league[league_id]
        if not standings:
            result[league_id] = None
            complete = False
            continue
        clubs = merge_club_data(uefa_points, standings, league['country'])
        result[league_id] = calculate_points_efficiency(clubs)

    # Incomplete results (a failed fetch) are not cached so the next request retries
    if complete:
        _efficiency_cache.set(season_year, result, season_cache_ttl(season_year))
    return result


def get_season_efficiency(season_year):
    """
    Points efficiency of every league for one season, or None if UEFA data is unavailable.
    Results are cached; only the current season needs the league tables (one request per league).
    """
    cached = _efficiency_cache.get(season_year)
    if cached is not None:
        return cached

    uefa_points = get_uefa_points(season_year)
    if not uefa_points:
        return None

    standings_by_league = fetch_all_standings(season_year) if season_year == BASE_YEAR else {}
    return compute_season_efficiency(uefa_points, standings_by_league, season_year)


def warm_season(season_year, refresh=False):
    """Load (or with refresh, re-fetch) all data the pages need for one season into the caches."""
    uefa_points = (get_uefa_points.refresh if refresh else get_uefa_points)(season_year)
    if not uefa_points:
        return
    standings_by_league = fetch_all_standings(season_year, refresh)
    compute_league_summaries(uefa_points, standings_by_league, season_year)
    compute_season_efficiency(uefa_points, standings_by_league, season_year)


def _warm_seasons(seasons, refresh=False):
    for season_year in seasons:
        try:
            warm_season(season_year, refresh)
        except Exception as e:
            logger.error(f"Cache warm-up failed for season {season_year}: {e}", exc_info=True)
        time.sleep(WARMUP_PAUSE)


def _warmup_loop():
    historic_seasons = range(BASE_YEAR - 1, MIN_YEAR - 1, -1)
    _warm_seasons([BASE_YEAR])
    _warm_seasons(historic_seasons)
    logger.info("Cache warm-up finished")

    now = time.monotonic()
    current_refreshed = historic_refreshed = now
    while True:
        time.sleep(WARMUP_TICK)
        now = time.monotonic()
        # Refresh shortly before the entries expire so visitors never wait for a cold fetch
        if now - current_refreshed >= CURRENT_SEASON_CACHE_TTL - WARMUP_REFRESH_MARGIN:
            _warm_seasons([BASE_YEAR], refresh=True)
            current_refreshed = now
        if now - historic_refreshed >= HISTORIC_SEASON_CACHE_TTL - WARMUP_REFRESH_MARGIN:
            _warm_seasons(historic_seasons, refresh=True)
            historic_refreshed = now


def start_cache_warmup():
    """Fill the caches in a background thread (current season first) and keep them fresh."""
    threading.Thread(target=_warmup_loop, name="cache-warmup", daemon=True).start()


@app.route("/efficiency")
def efficiency():
    """Countries x seasons table of how much of each federation's UEFA points sit with qualified clubs"""
    seasons = [{"year": year, "label": season_label(year)} for year in range(MIN_YEAR, BASE_YEAR + 1)]
    return render_template("efficiency.html", leagues=LEAGUES, seasons=seasons)


@app.route("/api/efficiency/<int:season_year>")
def get_efficiency_api(season_year):
    """API endpoint with points efficiency per league for one season"""
    if not MIN_YEAR <= season_year <= BASE_YEAR:
        return jsonify({"error": "Invalid season"}), 400
    try:
        result = get_season_efficiency(season_year)
        if result is None:
            return jsonify({"error": "UEFA ranking unavailable"}), 502
        return jsonify({"season": season_year, "leagues": result})
    except Exception as e:
        logger.error(f"Error in get_efficiency_api: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


def other_countries(uefa_points):
    """UEFA federations (sorted) that have no league in LEAGUES."""
    known = {league['country'].lower() for league in LEAGUES.values()}
    return sorted({
        club['country'] for club in uefa_points.values()
        if isinstance(club, dict) and club.get('country') not in (None, 'Unknown')
        and club['country'].lower() not in known
    })


def get_other_leagues(season_year=BASE_YEAR):
    """
    Top divisions of the federations missing from LEAGUES as {league_id: {'name', 'id', 'country'}}
    (federations without UEFA clubs in that season's ranking or without a FotMob league are left out).
    Only looked up on request.
    """
    uefa_points = get_uefa_points(season_year)
    top_leagues = get_top_leagues()
    if not uefa_points or not top_leagues:
        return {}

    leagues = {}
    for country in other_countries(uefa_points):
        league = top_leagues.get(FOTMOB_COUNTRY_ALIASES.get(country, country))
        if league:
            leagues[str(league['id'])] = {
                'name': f"{country}: {league['name']}", 'id': league['id'], 'country': country,
                'league_name': league['name'],
            }
    return leagues


def find_league(league_id, season_year=BASE_YEAR):
    """League info for a main league or (looked up only when needed) one of the other leagues."""
    return LEAGUES.get(league_id) or get_other_leagues(season_year).get(league_id)


def get_other_countries_efficiency(season_year):
    """
    Points efficiency of the federations that have no league in LEAGUES (no FotMob table), or None if UEFA data
    is unavailable. Only past seasons have a value (clubs that played in Europe the next season); computed on demand.
    """
    uefa_points = get_uefa_points(season_year)
    if not uefa_points:
        return None

    countries = other_countries(uefa_points)
    if season_year >= BASE_YEAR:
        return {country: None for country in countries}

    participants = european_participants(get_uefa_points(season_year + 1) or {}, season_year + 1)
    if not participants:
        return {country: None for country in countries}
    return {country: calculate_country_efficiency(uefa_points, country, participants) for country in countries}


@app.route("/api/efficiency/<int:season_year>/other")
def get_other_efficiency_api(season_year):
    """API endpoint with points efficiency per remaining UEFA federation for one season (loaded on demand)"""
    if not MIN_YEAR <= season_year <= BASE_YEAR:
        return jsonify({"error": "Invalid season"}), 400
    try:
        result = get_other_countries_efficiency(season_year)
        if result is None:
            return jsonify({"error": "UEFA ranking unavailable"}), 502
        league_ids = {league['country']: league_id for league_id, league in get_other_leagues(season_year).items()}
        return jsonify({"season": season_year, "countries": result, "league_ids": league_ids})
    except Exception as e:
        logger.error(f"Error in get_other_efficiency_api: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/other-leagues")
def get_other_leagues_api():
    """API endpoint with the top divisions of the remaining UEFA federations (loaded on demand)"""
    try:
        leagues = get_other_leagues(parse_season())
        if not leagues:
            return jsonify({"error": "League list unavailable"}), 502
        return jsonify({"leagues": [{"league_id": league_id, **league} for league_id, league in leagues.items()]})
    except Exception as e:
        logger.error(f"Error in get_other_leagues_api: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/")
def index():
    """Show league selector"""
    season = parse_season()
    ctx = season_context(season)
    try:
        uefa_points = get_uefa_points(season)
        if not uefa_points:
            uefa_points = {}
        league_summaries = build_league_summaries(uefa_points, season_year=season)
        return render_template("index.html", leagues=LEAGUES, selected_league=None, clubs=[], league_summary={}, league_summaries=league_summaries, **ctx)
    except Exception as e:
        logger.error(f"Error in index: {e}", exc_info=True)
        return render_template("index.html", leagues=LEAGUES, selected_league=None, clubs=[], league_summary={}, league_summaries={}, error=str(e), **ctx)


@app.route("/league/<league_id>")
def league_standings(league_id):
    """Show standings for a specific league"""
    season = parse_season()
    ctx = season_context(season)
    try:
        league = find_league(league_id, season)
        if league is None:
            return render_template("index.html", leagues=LEAGUES, selected_league=None, clubs=[], league_summary={}, league_summaries={},
                                 error="Invalid league selected", **ctx)
        is_main_league = league_id in LEAGUES

        logger.info(f"Fetching data for league {league['name']} ({ctx['season_name']})...")
        
        # Fetch both datasets
        uefa_points = get_uefa_points(season)
        standings = get_all_standings(int(league_id), season)
        
        error_message = None
        if not uefa_points:
            logger.warning("Failed to fetch UEFA points")
            uefa_points = {}
        
        if not standings:
            error_message = f"Failed to fetch standings for {league['name']} ({ctx['season_name']}). The league or season may not be supported by the API."
            logger.warning(error_message)
            standings = []
        
        # Merge the data
        merged_data = merge_club_data(uefa_points, standings, league['country'])
        if is_main_league:
            league_summaries = build_league_summaries(uefa_points, current_league_id=league_id, current_standings=standings, season_year=season)
            league_summary = league_summaries[league_id]
        else:
            # Other leagues are not part of the menu summaries; only reuse the ones that are already cached
            league_summaries = _summaries_cache.get(season) or {}
            league_summary = get_league_uefa_summary(league_id, uefa_points, standings, league['country'])
        
        logger.info(f"Successfully fetched and merged data for {len(merged_data)} clubs")
        
        return render_template(
            "index.html",
            clubs=merged_data,
            leagues=LEAGUES,
            other_leagues=None if is_main_league else get_other_leagues(season),
            selected_league=league_id,
            league_name=league['name'],
            league_summary=league_summary,
            league_summaries=league_summaries,
            qualification_legend=qualification_legend(merged_data),
            error=error_message,
            **ctx
        )
    
    except Exception as e:
        logger.error(f"Error in league_standings: {e}", exc_info=True)
        return render_template("index.html", leagues=LEAGUES, selected_league=league_id, 
                             clubs=[], league_summary={}, league_summaries={}, error=str(e), **ctx)


@app.route("/api/clubs/<league_id>")
def get_clubs_api(league_id):
    """API endpoint to get clubs data as JSON for a specific league (optional ?season=<ending year>)"""
    try:
        season = parse_season()
        league = find_league(league_id, season)
        if league is None:
            return jsonify({"error": "Invalid league ID"}), 400
        
        uefa_points = get_uefa_points(season)
        standings = get_all_standings(int(league_id), season)
        
        if not uefa_points:
            uefa_points = {}
        if not standings:
            standings = []
        
        merged_data = merge_club_data(uefa_points, standings, league['country'])
        return jsonify({
            "league": league,
            "season": season,
            "clubs": merged_data
        })
    
    except Exception as e:
        logger.error(f"Error in get_clubs_api: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    DEBUG = True
    # The debug reloader runs this module twice; only its serving child process should warm the caches
    if not DEBUG or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        start_cache_warmup()
    app.run(debug=DEBUG)