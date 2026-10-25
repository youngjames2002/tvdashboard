import datetime as dt
import os
import json

import icalendar
import recurring_ical_events
import requests
from fastapi import FastAPI, HTTPException

from pathlib import Path
from fastapi.responses import FileResponse

ICAL_URL = os.environ["GCAL_ICAL_URL"] 
BASE_DIR = Path(__file__).parent
SPORTS_FILE = BASE_DIR / "sports.json"

app = FastAPI()

def _sort_key(start, tz):
    return start if isinstance(start, dt.datetime) else dt.datetime.combine(start, dt.time.min, tz)

@app.get("/events")
def get_events(days: int = 30, limit: int = 10):
    try:
        resp = requests.get(ICAL_URL, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Calendar fetch failed: {exc}")

    cal = icalendar.Calendar.from_ical(resp.content)
    now = dt.datetime.now().astimezone()
    occurrences = recurring_ical_events.of(cal).between(now, now + dt.timedelta(days=days))
    occurrences = sorted(occurrences, key=lambda ev: _sort_key(ev["DTSTART"].dt, now.tzinfo))[:limit]

    events = []
    for ev in occurrences:
        start = ev["DTSTART"].dt
        all_day = not isinstance(start, dt.datetime)
        events.append({
            "start": start.isoformat() if all_day else start.astimezone(now.tzinfo).isoformat(),
            "all_day": all_day,
            "summary": str(ev.get("SUMMARY", "(no title)")),
        })
    return events

@app.get("/sports")
def get_sports():
    # Written by fetch_sports.py on cron; this endpoint only reads it
    try:
        return json.loads(SPORTS_FILE.read_text())
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="sports.json not generated yet; run fetch_sports.py")


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "index.html")