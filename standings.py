from cache import ttl_cache
from http_session import session
from ranking import BASE_YEAR, season_cache_ttl

FOTMOB_URL = "https://www.fotmob.com/api/data/tltable"
FOTMOB_LEAGUES_URL = "https://www.fotmob.com/api/data/leagues"
FOTMOB_HEADERS = {"User-Agent": "Mozilla/5.0"}
# FotMob legend keys for European competition spots (excludes e.g. relegation or league playoffs)
EUROPEAN_LEGEND_PREFIXES = ("championsleague", "clqual", "europaleague", "euroqual", "europa_conference_league")


def get_league_standings(league_id):
    """
    Fetch league standings from FotMob (free, no API key).
    league_id: League ID used by the app, which is also the FotMob league ID.
    """
    try:
        response = session.get(
            FOTMOB_URL, params={"leagueId": league_id}, headers=FOTMOB_HEADERS, timeout=20
        )
        print(f"API Response Status: {response.status_code} {response.reason}")
        response.raise_for_status()

        payload = response.json()
        data = payload[0].get("data") if isinstance(payload, list) and payload else None
        if not isinstance(data, dict):
            print(f"Unexpected response format for league {league_id}")
            return None

        return data
    except Exception as e:
        print(f"Error fetching standings: {e}")
        return None


def _group_rows(group):
    return (group.get("table") or {}).get("all") or []


def _table_groups(data):
    """
    Return [(group_name, rows, legend)] for a FotMob table response.
    Leagues split into stages (e.g. championship/relegation groups) list the stage groups first
    and the full regular-season table last; clubs from that table that are in no stage group
    are added as an extra group, and groups are ordered by their best regular-season position.
    """
    table = data.get("table")
    if isinstance(table, dict) and table.get("all"):
        return [(None, table["all"], data.get("legend"))]

    tables = [group for group in data.get("tables") or [] if _group_rows(group)]
    if len(tables) < 2:
        return [(None, _group_rows(group), group.get("legend") or data.get("legend")) for group in tables]

    *stages, regular = tables
    regular_position = {row.get("id"): int(row.get("idx") or 0) for row in _group_rows(regular)}
    staged_ids = {row.get("id") for group in stages for row in _group_rows(group)}

    groups = [(group.get("leagueName"), _group_rows(group), group.get("legend")) for group in stages]
    leftovers = [row for row in _group_rows(regular) if row.get("id") not in staged_ids]
    if leftovers:
        groups.append(("Other clubs", leftovers, None))

    def best_position(group):
        return min(regular_position.get(row.get("id"), 0) or float("inf") for row in group[1])

    return sorted(groups, key=best_position)


def _european_qualification_by_position(legend):
    """Map 0-based table position -> {'title', 'color'} for positions leading to European competitions."""
    by_position = {}
    for entry in legend or []:
        if not str(entry.get("tKey", "")).startswith(EUROPEAN_LEGEND_PREFIXES):
            continue
        for index in entry.get("indices") or []:
            by_position[index] = {"title": entry.get("title", ""), "color": entry.get("color")}
    return by_position


def extract_standings(data):
    """
    Extract relevant standing information from a FotMob table response.
    Returns a list of dicts with club info.
    """
    if not data:
        return []

    standings_list = []
    for group_name, rows, legend in _table_groups(data):
        qualification = _european_qualification_by_position(legend)
        for item in rows:
            goals_for, goals_against = 0, 0
            try:
                goals_for, goals_against = (int(x) for x in str(item.get("scoresStr", "")).split("-"))
            except ValueError:
                pass

            position = int(item.get("idx") or 0)
            standings_list.append({
                "name": item.get("name", "Unknown"),
                "short_name": item.get("shortName") or item.get("name", ""),
                "played": int(item.get("played") or 0),
                "wins": int(item.get("wins") or 0),
                "draws": int(item.get("draws") or 0),
                "losses": int(item.get("losses") or 0),
                "goals_for": goals_for,
                "goals_against": goals_against,
                "goal_diff": int(item.get("goalConDiff") or 0),
                "points": int(item.get("pts") or 0),
                "position": position,
                "group_name": group_name,
                "qualification": qualification.get(position - 1)
            })

    return standings_list


def _season_labels(season_year):
    """FotMob season names for a season ending in season_year: '2022/2023', or '2022' for calendar-year leagues."""
    return [f"{season_year - 1}/{season_year}", str(season_year - 1)]


def get_league_standings_for_season(league_id, season_year):
    """
    Fetch the final table of a past season from FotMob.
    FotMob silently falls back to the current season for an unknown season name,
    so the returned 'selectedSeason' is checked against the requested one.
    """
    try:
        for label in _season_labels(season_year):
            response = session.get(
                FOTMOB_LEAGUES_URL,
                params={"id": league_id, "season": label},
                headers=FOTMOB_HEADERS,
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
            if (payload.get("details") or {}).get("selectedSeason") != label:
                continue

            tables = payload.get("table")
            data = tables[0].get("data") if isinstance(tables, list) and tables else None
            return data if isinstance(data, dict) else None

        print(f"Season {season_year} not available for league {league_id}")
        return None
    except Exception as e:
        print(f"Error fetching standings for season {season_year}: {e}")
        return None


@ttl_cache(lambda league_id, season_year: season_cache_ttl(season_year))
def get_all_standings(league_id=196, season_year=None):
    """Main function to get all standings data for a specific league (and season ending in season_year)"""
    if season_year is None or season_year == BASE_YEAR:
        data = get_league_standings(league_id)
    else:
        data = get_league_standings_for_season(league_id, season_year)
    if data is None:
        return []

    return extract_standings(data)


if __name__ == "__main__":
    print("Fetching league standings...")
    standings = get_all_standings(47)
    for club in standings:
        print(f"{club['position']}. {club['name']}: {club['points']} pts ({club['played']} matches)")
