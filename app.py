import datetime as dt
import os
import json
from pathlib import Path
from urllib.parse import quote

import icalendar
import recurring_ical_events
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ICAL_URL = os.environ["GCAL_ICAL_URL"]
BASE_DIR = Path(__file__).parent
SPORTS_FILE = BASE_DIR / "sports.json"
MUSIC_DIR = Path(os.environ.get("MUSIC_DIR", BASE_DIR / "music"))

app = FastAPI()
app.mount("/music", StaticFiles(directory=MUSIC_DIR, check_dir=False), name="music")


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
    try:
        return json.loads(SPORTS_FILE.read_text())
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="sports.json not generated yet; run fetch_sports.py")


@app.get("/playlist")
def get_playlist():
    if not MUSIC_DIR.is_dir():
        return []
    files = sorted(f for f in MUSIC_DIR.iterdir() if f.is_file() and f.suffix.lower() == ".mp3")
    return [{"name": f.name, "url": f"/music/{quote(f.name)}"} for f in files]


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "index.html")