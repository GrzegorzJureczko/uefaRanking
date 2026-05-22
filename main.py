from flask import Flask, render_template, jsonify, request
from ranking import get_uefa_points
from standings import get_all_standings
from difflib import SequenceMatcher
import logging
import os

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# League configuration with IDs and names
LEAGUES = {
    '47': {'name': 'English Premier League', 'code': 'en', 'id': 47},
    '55': {'name': 'Italian Serie A', 'code': 'it', 'id': 55},  
    '87': {'name': 'Spanish La Liga', 'code': 'es', 'id': 87},
    '54': {'name': 'German Bundesliga', 'code': 'de', 'id': 54},
    '53': {'name': 'French Ligue 1', 'code': 'fr', 'id': 53},
    '61': {'name': 'Portuguese Liga Portugal', 'code': 'pt', 'id': 61},
    '57': {'name': 'Dutch Eredivisie', 'code': 'nl', 'id': 57},
    '40': {'name': 'Belgian First Division A', 'code': 'be', 'id': 40},
    '71': {'name': 'Turkish Super League', 'code': 'tr', 'id': 71},
    '122': {'name': 'Czech First League', 'code': 'cz', 'id': 122},
    '135': {'name': 'Greek Super League 1', 'code': 'gr', 'id': 135},
    '196': {'name': 'Polish Ekstraklasa', 'code': 'pl', 'id': 196},
    '46': {'name': 'Danish Superligaen', 'code': 'dk', 'id': 46},
    '59': {'name': 'Norwegian Eliteserien', 'code': 'no', 'id': 59},
    '136': {'name': 'Cypriot 1. Division', 'code': 'cy', 'id': 136},
    '69': {'name': 'Swiss Super League', 'code': 'ch', 'id': 69},
    '38': {'name': 'Austrian Bundesliga', 'code': 'at', 'id': 38},
    '64': {'name': 'Scottish Premiership', 'code': 'sc', 'id': 64},
    '67': {'name': 'Swedish Allsvenskan', 'code': 'se', 'id': 67},
    '252': {'name': 'Croatian HNL', 'code': 'hr', 'id': 252},
}


def fuzzy_match_clubs(uefa_clubs, standings_clubs):
    """
    Match clubs from both datasets using fuzzy string matching.
    Returns a mapping of standings club names to UEFA club names.
    """
    mapping = {}
    
    for standing_club in standings_clubs:
        standing_name = standing_club['name'].lower()
        best_match = None
        best_ratio = 0
        
        for uefa_name in uefa_clubs.keys():
            uefa_name_lower = uefa_name.lower()
            ratio = SequenceMatcher(None, standing_name, uefa_name_lower).ratio()
            
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = uefa_name
        
        # Only match if similarity is high enough (80%)
        if best_ratio > 0.7:
            mapping[standing_club['name']] = best_match
    print(f"Fuzzy matching results: {mapping}")
    return mapping


def merge_club_data(uefa_points, standings_data):
    """
    Merge UEFA points data with league standings data.
    Returns a list of clubs with combined information.
    """
    # Create mapping between standings club names and UEFA club names
    club_mapping = fuzzy_match_clubs(uefa_points, standings_data)
    
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
        return render_template("index.html", leagues=LEAGUES, selected_league=None, clubs=[])
    except Exception as e:
        logger.error(f"Error in index: {e}", exc_info=True)
        return render_template("index.html", leagues=LEAGUES, selected_league=None, clubs=[], error=str(e))


@app.route("/league/<league_id>")
def league_standings(league_id):
    """Show standings for a specific league"""
    try:
        if league_id not in LEAGUES:
            return render_template("index.html", leagues=LEAGUES, selected_league=None, clubs=[], 
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
        merged_data = merge_club_data(uefa_points, standings)
        
        logger.info(f"Successfully fetched and merged data for {len(merged_data)} clubs")
        
        return render_template(
            "index.html",
            clubs=merged_data,
            leagues=LEAGUES,
            selected_league=league_id,
            league_name=LEAGUES[league_id]['name'],
            error=error_message
        )
    
    except Exception as e:
        logger.error(f"Error in league_standings: {e}", exc_info=True)
        return render_template("index.html", leagues=LEAGUES, selected_league=league_id, 
                             clubs=[], error=str(e))


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
        
        merged_data = merge_club_data(uefa_points, standings)
        return jsonify({
            "league": LEAGUES[league_id],
            "clubs": merged_data
        })
    
    except Exception as e:
        logger.error(f"Error in get_clubs_api: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)