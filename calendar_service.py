import os
import time
import threading
import urllib.parse
from datetime import datetime, date, timedelta
import requests
from icalendar import Calendar
import recurring_ical_events
import re
from dotenv import load_dotenv

load_dotenv()

ICS_URL = os.getenv("ICS_URL")
if not ICS_URL:
    print("Warnung: ICS_URL ist in der .env-Datei nicht gesetzt!")

BIRTHDAY_ICS_URL = os.getenv("BIRTHDAY_ICS_URL")

week_events = []
week_birthdays = []
today_birthday_names = []
last_update = None

travel_time_cache = {}
CACHE_TTL = 600

def get_travel_time(destination):
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key or not destination:
        return None
    
    now = time.time()
    if destination in travel_time_cache:
        cached = travel_time_cache[destination]
        if now - cached["timestamp"] < CACHE_TTL:
            return cached["data"]
            
    origin = "Boppstraße 28, 55118 Mainz"
    origin_enc = urllib.parse.quote(origin)
    dest_enc = urllib.parse.quote(destination)
    
    result = {"driving": None, "walking": None}
    
    # 1. Fahrtzeit (Driving)
    url_driving = f"https://maps.googleapis.com/maps/api/distancematrix/json?origins={origin_enc}&destinations={dest_enc}&departure_time=now&key={api_key}&language=de"
    try:
        response = requests.get(url_driving, timeout=5)
        data = response.json()
        if data.get("status") == "OK":
            element = data["rows"][0]["elements"][0]
            if element.get("status") == "OK":
                if "duration_in_traffic" in element:
                    result["driving"] = element["duration_in_traffic"]["text"]
                else:
                    result["driving"] = element["duration"]["text"]
    except Exception as e:
        print(f"Fehler bei Google Maps API (Driving) für {destination}: {e}")
        
    # 2. Fußweg (Walking) - nur für 55118 und 55116
    if "55118" in destination or "55116" in destination:
        url_walking = f"https://maps.googleapis.com/maps/api/distancematrix/json?origins={origin_enc}&destinations={dest_enc}&mode=walking&key={api_key}&language=de"
        try:
            response = requests.get(url_walking, timeout=5)
            data = response.json()
            if data.get("status") == "OK":
                element = data["rows"][0]["elements"][0]
                if element.get("status") == "OK":
                    result["walking"] = element["duration"]["text"]
        except Exception as e:
            print(f"Fehler bei Google Maps API (Walking) für {destination}: {e}")
            
    if not result["driving"] and not result["walking"]:
        return None
        
    travel_time_cache[destination] = {"data": result, "timestamp": now}
    return result

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
                    location = str(event.get("LOCATION", "")).strip()
                    
                    travel_time = None
                    if location:
                        travel_time = get_travel_time(location)
                    
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
                        "assignee": assignee,
                        "location": location,
                        "travel_time": travel_time
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

def start_background_thread():
    bg_thread = threading.Thread(target=fetch_calendar_data, daemon=True)
    bg_thread.start()

def get_calendar_data():
    return {
        "events": week_events,
        "last_update": last_update,
        "today_birthdays": today_birthday_names,
        "week_birthdays": week_birthdays
    }
