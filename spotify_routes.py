import os
import time
from flask import Blueprint, jsonify, request, redirect
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

load_dotenv()

spotify_bp = Blueprint('spotify_bp', __name__)

SPOTIPY_CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
SPOTIPY_REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI", "https://localhost:5000/callback")

if SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET:
    sp_oauth = SpotifyOAuth(
        client_id=SPOTIPY_CLIENT_ID,
        client_secret=SPOTIPY_CLIENT_SECRET,
        redirect_uri=SPOTIPY_REDIRECT_URI,
        scope="streaming user-read-email user-read-private user-read-currently-playing user-read-playback-state user-modify-playback-state playlist-read-private playlist-read-collaborative",
        cache_path=".spotifycache",
        open_browser=False
    )
else:
    sp_oauth = None

@spotify_bp.route("/login")
def login():
    if not sp_oauth:
        return "Spotify ist nicht konfiguriert. Bitte SPOTIPY Variablen in der .env setzen."
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)

@spotify_bp.route("/callback")
def callback():
    if not sp_oauth:
        return "Spotify ist nicht konfiguriert."
    code = request.args.get('code')
    if code:
        sp_oauth.get_access_token(code)
        return "Spotify erfolgreich verknüpft! Du kannst diesen Tab schließen."
    return "Fehler beim Login."

@spotify_bp.route("/api/spotify")
def spotify_api():
    if not sp_oauth:
        return jsonify({"is_playing": False, "error": "Not configured"})
    try:
        token_info = sp_oauth.get_cached_token()
        if not token_info:
            return jsonify({"is_playing": False, "auth_required": True})
        
        sp = spotipy.Spotify(auth=token_info['access_token'])
        
        # Try current_playback first (includes device info)
        playback = sp.current_playback()
        
        # Fallback to currently_playing if playback is None
        if not playback:
            playback = sp.currently_playing()
            
        if playback and playback.get('item'):
            item = playback.get('item')
            track_name = item['name']
            artist_name = item['artists'][0]['name']
            album_img = item['album']['images'][0]['url'] if item['album']['images'] else ""
            
            # device info might be missing in currently_playing fallback
            device = playback.get('device', {})
            volume = device.get('volume_percent', 50)
            is_playing = playback.get('is_playing', False)
            
            return jsonify({
                "is_playing": is_playing,
                "track": track_name,
                "artist": artist_name,
                "image": album_img,
                "volume": volume
            })
        else:
            return jsonify({"is_playing": False})
    except Exception as e:
        print("Spotify API Error:", e)
        return jsonify({"is_playing": False, "error": str(e)})

@spotify_bp.route("/api/spotify/next", methods=["POST"])
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

@spotify_bp.route("/api/spotify/previous", methods=["POST"])
def spotify_previous():
    if not sp_oauth:
        return jsonify({"error": "Not configured"}), 400
    try:
        token_info = sp_oauth.get_cached_token()
        if not token_info:
            return jsonify({"error": "Not authenticated"}), 401
        
        sp = spotipy.Spotify(auth=token_info['access_token'])
        sp.previous_track()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@spotify_bp.route("/api/spotify/play_pause", methods=["POST"])
def spotify_play_pause():
    if not sp_oauth:
        return jsonify({"error": "Not configured"}), 400
    try:
        token_info = sp_oauth.get_cached_token()
        if not token_info:
            return jsonify({"error": "Not authenticated"}), 401
            
        sp = spotipy.Spotify(auth=token_info['access_token'])
        current = sp.current_playback()
        if current and current.get('is_playing'):
            sp.pause_playback()
            return jsonify({"success": True, "is_playing": False})
        else:
            data = request.json or {}
            device_id = data.get('device_id')
            sp.start_playback(device_id=device_id)
            return jsonify({"success": True, "is_playing": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@spotify_bp.route("/api/spotify/token")
def spotify_token():
    if not sp_oauth:
        return jsonify({"token": None})
    token_info = sp_oauth.get_cached_token()
    if not token_info:
        return jsonify({"token": None})
    return jsonify({"token": token_info['access_token']})

@spotify_bp.route("/api/spotify/volume", methods=["POST"])
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

@spotify_bp.route("/api/spotify/playlists")
def api_playlists():
    if not sp_oauth:
        return jsonify({"error": "Not configured"}), 400
    try:
        token_info = sp_oauth.get_cached_token()
        if not token_info:
            return jsonify({"error": "Not authenticated"}), 401
        
        sp = spotipy.Spotify(auth=token_info['access_token'])
        
        query = request.args.get('q', '')
        if query:
            results = sp.search(q=query, type='playlist')
            playlists_data = results['playlists']['items']
        else:
            results = sp.current_user_playlists()
            playlists_data = results['items']
            
        return jsonify({"playlists": playlists_data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@spotify_bp.route("/api/spotify/play_playlist", methods=["POST"])
def play_playlist():
    if not sp_oauth:
        return jsonify({"error": "Not configured"}), 400
    try:
        token_info = sp_oauth.get_cached_token()
        if not token_info:
            return jsonify({"error": "Not authenticated"}), 401
            
        data = request.json
        playlist_uri = data.get('uri')
        device_id = data.get('device_id')
        
        sp = spotipy.Spotify(auth=token_info['access_token'])
        
        # 1. Wake up / Transfer playback to this device
        if device_id:
            try:
                sp.transfer_playback(device_id=device_id, force_play=False)
                # Small buffer to ensure transfer is processed
                time.sleep(0.5)
            except Exception as transfer_e:
                print(f"Transfer/Wakeup Error: {transfer_e}")

        # 2. Set shuffle
        try:
            sp.shuffle(state=True, device_id=device_id)
        except Exception as shuffle_e:
            print(f"Shuffle Error: {shuffle_e}")
            
        # 3. Start the actual playlist
        sp.start_playback(context_uri=playlist_uri, device_id=device_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
