from flask import Flask, render_template, jsonify
from ranking import get_uefa_points
from standings import get_all_standings
from difflib import SequenceMatcher
import logging

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
        if best_ratio > 0.8:
            mapping[standing_club['name']] = best_match
    
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
            'uefa_points': uefa_points.get(uefa_club_name, '-'),
            'matched': uefa_club_name is not None
        }
        merged_data.append(merged_club)
    
    return merged_data


@app.route("/")
def hello_world():
    try:
        logger.info("Fetching data...")
        
        # Fetch both datasets
        uefa_points = get_uefa_points()
        standings = get_all_standings()
        
        if not uefa_points:
            logger.warning("Failed to fetch UEFA points")
            uefa_points = {}
        
        if not standings:
            logger.warning("Failed to fetch standings")
            standings = []
        
        # Merge the data
        merged_data = merge_club_data(uefa_points, standings)
        
        logger.info(f"Successfully fetched and merged data for {len(merged_data)} clubs")
        
        return render_template("index.html", clubs=merged_data)
    
    except Exception as e:
        logger.error(f"Error in hello_world: {e}", exc_info=True)
        return render_template("index.html", clubs=[], error=str(e))


@app.route("/api/clubs")
def get_clubs_api():
    """API endpoint to get clubs data as JSON"""
    try:
        uefa_points = get_uefa_points()
        standings = get_all_standings()
        
        if not uefa_points:
            uefa_points = {}
        if not standings:
            standings = []
        
        merged_data = merge_club_data(uefa_points, standings)
        return jsonify(merged_data)
    
    except Exception as e:
        logger.error(f"Error in get_clubs_api: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)