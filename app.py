import os
from flask import Flask, render_template, jsonify, send_from_directory
from cert_manager import ensure_certificates
from dotenv import load_dotenv

load_dotenv()

from calendar_service import start_background_thread, get_calendar_data
from spotify_routes import spotify_bp

app = Flask(__name__)

# Register Spotify Blueprint
app.register_blueprint(spotify_bp)

# Start background thread for fetching calendar
start_background_thread()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/events")
def get_events():
    return jsonify(get_calendar_data())

@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory('static', 'manifest.json')

@app.route('/sw.js')
def serve_sw():
    return send_from_directory('static', 'sw.js')

if __name__ == "__main__":
    cert_file, key_file = ensure_certificates()
    app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False, ssl_context=(cert_file, key_file))
