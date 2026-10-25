"""Fetch the latest result and next game for favourite teams from ESPN's public API.

Run from cron; writes sports.json next to this file for the dashboard to serve.
"""
import datetime as dt
import json
import os
from pathlib import Path

import requests

BASE = "https://site.api.espn.com/apis/site/v2/sports"
OUT = Path(__file__).parent / "sports.json"

TEAMS = [
    {"short": "Arsenal", "sport": "soccer", "league": "eng.1", "id": "359"},
    {"short": "Raiders", "sport": "football", "league": "nfl", "id": "13"},
    {"short": "76ers", "sport": "basketball", "league": "nba", "id": "20"},
]


def get_events(team):
    url = f"{BASE}/{team['sport']}/{team['league']}/teams/{team['id']}/schedule"
    # Soccer schedules return past results by default; upcoming fixtures need fixture=true
    param_sets = [{}, {"fixture": "true"}] if team["sport"] == "soccer" else [{}]
    events = {}
    for params in param_sets:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        for ev in resp.json().get("events", []):
            events[ev["id"]] = ev  # dedupe across the two soccer calls
    return sorted(events.values(), key=lambda e: e["date"])


def score_of(competitor):
    score = competitor.get("score")
    # Schedule endpoint returns {"value", "displayValue"}; scoreboard returns a plain string
    return score.get("displayValue") if isinstance(score, dict) else score


def summarise(ev, team_id):
    comp = ev["competitions"][0]
    us = next(c for c in comp["competitors"] if c["team"]["id"] == team_id)
    them = next(c for c in comp["competitors"] if c["team"]["id"] != team_id)
    completed = comp["status"]["type"].get("completed", False)
    outcome = None
    if completed:
        outcome = "W" if us.get("winner") else "L" if them.get("winner") else "D"
    return {
        "date": ev["date"],
        "home": us.get("homeAway") == "home",
        "opponent": them["team"].get("shortDisplayName") or them["team"]["displayName"],
        "score_for": score_of(us) if completed else None,
        "score_against": score_of(them) if completed else None,
        "outcome": outcome,
        "completed": completed,
    }


def team_summary(team):
    games = [summarise(ev, team["id"]) for ev in get_events(team)]
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    played = [g for g in games if g["completed"]]
    upcoming = [g for g in games if not g["completed"] and g["date"] >= now[:16]]
    return {
        "short": team["short"],
        "last": played[-1] if played else None,
        "next": upcoming[0] if upcoming else None,
        "stale": False,
    }


def main():
    previous = {}
    if OUT.exists():
        previous = {t["short"]: t for t in json.loads(OUT.read_text()).get("teams", [])}

    teams = []
    for team in TEAMS:
        try:
            teams.append(team_summary(team))
            print(f"ok    {team['short']}")
        except Exception as exc:  # one bad team shouldn't wipe the others
            print(f"FAIL  {team['short']}: {exc}")
            fallback = previous.get(team["short"], {"short": team["short"], "last": None, "next": None})
            teams.append({**fallback, "stale": True})

    payload = {"fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(), "teams": teams}
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, OUT)  # atomic: the API never reads a half-written file


if __name__ == "__main__":
    main()