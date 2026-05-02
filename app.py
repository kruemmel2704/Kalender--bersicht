import os
import time
import threading
from datetime import datetime, date
import requests
from flask import Flask, render_template, jsonify, request, redirect
from dotenv import load_dotenv
from icalendar import Calendar
import recurring_ical_events
import re
import spotipy
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()

app = Flask(__name__)

ICS_URL = os.getenv("ICS_URL")
if not ICS_URL:
    print("Warnung: ICS_URL ist in der .env-Datei nicht gesetzt!")

from datetime import datetime, date, timedelta

# Global cache for the week's events
week_events = []
week_birthdays = []
today_birthday_names = []
last_update = None
BIRTHDAY_ICS_URL = os.getenv("BIRTHDAY_ICS_URL")

# Spotify Integration
SPOTIPY_CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
SPOTIPY_REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI", "https://localhost:5000/callback")

if SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET:
    sp_oauth = SpotifyOAuth(
        client_id=SPOTIPY_CLIENT_ID,
        client_secret=SPOTIPY_CLIENT_SECRET,
        redirect_uri=SPOTIPY_REDIRECT_URI,
        scope="user-read-currently-playing user-read-playback-state user-modify-playback-state",
        cache_path=".spotifycache",
        open_browser=False
    )
else:
    sp_oauth = None

def fetch_calendar_data():
    global week_events, week_birthdays, today_birthday_names, last_update
    while True:
        if ICS_URL:
            try:
                # Add timeout to avoid hanging
                response = requests.get(ICS_URL, timeout=10)
                response.raise_for_status()
                
                cal = Calendar.from_ical(response.content)
                now = datetime.now()
                today = now.date()
                
                # Current rolling week (Today to Today + 6 days)
                start_date = today
                end_date = start_date + timedelta(days=6)
                
                events = recurring_ical_events.of(cal).between(
                    datetime.combine(start_date, datetime.min.time()),
                    datetime.combine(end_date, datetime.max.time())
                )
                
                parsed_events = []
                for event in events:
                    start_dt = event.get("DTSTART").dt
                    end_dt = event.get("DTEND").dt if event.get("DTEND") else None
                    summary = str(event.get("SUMMARY", "Kein Titel"))
                    description = str(event.get("DESCRIPTION", ""))
                    
                    assignee = None
                    match = re.search(r'\$bearbeiter\s*:?\s*(.+)', description, re.IGNORECASE)
                    if match:
                        assignee = match.group(1).strip()
                    
                    is_all_day = False
                    # Convert to datetime if it's just a date (all-day event)
                    if isinstance(start_dt, date) and not isinstance(start_dt, datetime):
                        is_all_day = True
                        event_date = start_dt
                        time_str = "Ganztägig"
                        
                        start_timestamp = datetime.combine(start_dt, datetime.min.time()).timestamp()
                        if end_dt and isinstance(end_dt, date) and not isinstance(end_dt, datetime):
                            actual_end_date = end_dt - timedelta(days=1)
                        else:
                            actual_end_date = start_dt
                        end_timestamp = datetime.combine(actual_end_date, datetime.max.time()).timestamp()
                    else:
                        is_all_day = False
                        event_date = start_dt.date()
                        start_timestamp = start_dt.timestamp()
                        
                        time_str = start_dt.strftime("%H:%M")
                        if end_dt and isinstance(end_dt, datetime):
                            time_str += f" - {end_dt.strftime('%H:%M')}"
                            end_timestamp = end_dt.timestamp()
                        else:
                            end_timestamp = start_timestamp + 3600
                    
                    # Filter out events that ended more than 30 minutes ago for today
                    if event_date == today:
                        if now.timestamp() > end_timestamp + 1800:
                            continue
                        
                    is_past_day = False # We don't fetch past days anymore
                    day_names = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
                    
                    parsed_events.append({
                        "summary": summary,
                        "time_str": time_str,
                        "date_str": event_date.strftime("%d.%m."),
                        "day_name": day_names[event_date.weekday()],
                        "is_all_day": is_all_day,
                        "start_timestamp": start_timestamp,
                        "is_past_day": is_past_day,
                        "event_date_iso": event_date.isoformat(),
                        "assignee": assignee
                    })
                
                # Sort events chronologically
                parsed_events.sort(key=lambda x: (x["event_date_iso"], not x["is_all_day"], x["start_timestamp"]))
                
                week_events = parsed_events
                last_update = datetime.now().strftime("%H:%M:%S")
            except Exception as e:
                print(f"Fehler beim Abrufen oder Parsen des Kalenders: {e}")
                
        if BIRTHDAY_ICS_URL:
            try:
                b_response = requests.get(BIRTHDAY_ICS_URL, timeout=10)
                b_response.raise_for_status()
                
                b_cal = Calendar.from_ical(b_response.content)
                now = datetime.now()
                today = now.date()
                start_date = today
                end_date = start_date + timedelta(days=6)
                
                b_events = recurring_ical_events.of(b_cal).between(
                    datetime.combine(start_date, datetime.min.time()),
                    datetime.combine(end_date, datetime.max.time())
                )
                
                t_bday_names = []
                w_bdays = []
                day_names = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
                
                for event in b_events:
                    summary = str(event.get("SUMMARY", "Geburtstag"))
                    start_dt = event.get("DTSTART").dt
                    
                    if isinstance(start_dt, datetime):
                        event_date = start_dt.date()
                    else:
                        event_date = start_dt
                        
                    if event_date == today:
                        t_bday_names.append(summary)
                    
                    w_bdays.append({
                        "name": summary,
                        "date_str": event_date.strftime("%d.%m."),
                        "day_name": day_names[event_date.weekday()],
                        "event_date_iso": event_date.isoformat()
                    })
                
                w_bdays.sort(key=lambda x: x["event_date_iso"])
                
                today_birthday_names = t_bday_names
                week_birthdays = w_bdays
                
            except Exception as e:
                print(f"Fehler beim Abrufen des Geburtstagskalenders: {e}")
                
        time.sleep(30)

# Start background thread before first request
bg_thread = threading.Thread(target=fetch_calendar_data, daemon=True)
bg_thread.start()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login")
def login():
    if not sp_oauth:
        return "Spotify ist nicht konfiguriert. Bitte SPOTIPY Variablen in der .env setzen."
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)

@app.route("/callback")
def callback():
    if not sp_oauth:
        return "Spotify ist nicht konfiguriert."
    code = request.args.get('code')
    if code:
        sp_oauth.get_access_token(code)
        return "Spotify erfolgreich verknüpft! Du kannst diesen Tab schließen."
    return "Fehler beim Login."

@app.route("/api/spotify")
def spotify_api():
    if not sp_oauth:
        return jsonify({"is_playing": False, "error": "Not configured"})
    try:
        token_info = sp_oauth.get_cached_token()
        if not token_info:
            return jsonify({"is_playing": False, "auth_required": True})
        
        sp = spotipy.Spotify(auth=token_info['access_token'])
        current_playback = sp.current_playback()
        
        if current_playback is not None and current_playback.get('is_playing'):
            item = current_playback.get('item')
            if not item:
                return jsonify({"is_playing": False})
                
            track_name = item['name']
            artist_name = item['artists'][0]['name']
            album_img = item['album']['images'][0]['url'] if item['album']['images'] else ""
            volume = current_playback.get('device', {}).get('volume_percent', 50)
            
            return jsonify({
                "is_playing": True,
                "track": track_name,
                "artist": artist_name,
                "image": album_img,
                "volume": volume
            })
        else:
            return jsonify({"is_playing": False})
    except Exception as e:
        print("Spotify Error:", e)
        return jsonify({"is_playing": False, "error": str(e)})

@app.route("/api/spotify/next", methods=["POST"])
def spotify_next():
    if not sp_oauth:
        return jsonify({"error": "Not configured"}), 400
    try:
        token_info = sp_oauth.get_cached_token()
        if not token_info:
            return jsonify({"error": "Not authenticated"}), 401
        
        sp = spotipy.Spotify(auth=token_info['access_token'])
        sp.next_track()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/spotify/volume", methods=["POST"])
def spotify_volume():
    if not sp_oauth:
        return jsonify({"error": "Not configured"}), 400
    try:
        token_info = sp_oauth.get_cached_token()
        if not token_info:
            return jsonify({"error": "Not authenticated"}), 401
            
        data = request.json
        volume = data.get('volume', 50)
        
        sp = spotipy.Spotify(auth=token_info['access_token'])
        sp.volume(volume)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/events")
def get_events():
    return jsonify({
        "events": week_events,
        "last_update": last_update,
        "today_birthdays": today_birthday_names,
        "week_birthdays": week_birthdays
    })

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False, ssl_context="adhoc")
