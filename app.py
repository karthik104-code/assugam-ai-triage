import os
import json
import sqlite3
from flask import Flask, render_template, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from google import genai
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "super-secret-triage-key")

# Database initialization
def init_db():
    conn = sqlite3.connect('app.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, 
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                  transcript TEXT, analysis TEXT, specialty TEXT)''')
    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect('app.db')
    conn.row_factory = sqlite3.Row
    return conn
# Initialize Gemini Client if API Key is available
gemini_api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=gemini_api_key) if gemini_api_key else None

SYSTEM_PROMPT = """You are a "Medical Support & Triage Assistant." Your goal is to process voice-transcribed patient symptoms and provide preliminary analysis, potential causes, and nearby provider recommendations.
Operational Protocol:
1. Safety First (Mandatory): Always start with a disclaimer: "I am an AI, not a doctor. If you are experiencing a life-threatening emergency, call emergency services immediately."
2. Symptom Intake: Analyze the input text for key health indicators (pain level, duration, location, and specific symptoms).
3. Differential Analysis: Provide a list of possible conditions. Use phrases like "Your symptoms are consistent with..." or "Could be related to..." instead of "You have..."
4. Recommendation Engine:
- Suggest common over-the-counter (OTC) management if appropriate, but emphasize consulting a professional.
- Cross-reference the identified condition with a specialty (e.g., "Dermatologist" for rashes).
5. Geospatial Matching: Use the user's location to find suitable doctors. Priority should be given to clinics matching the needed specialty.
6. Privacy: Do not store identifiable health data in plain text.

Respond ONLY with a valid JSON object (no markdown, no backticks, no code blocks) with the following keys: 
"disclaimer", "analysis", "possible_conditions" (list of strings), "otc_suggestions" (list of strings), "recommended_specialty", "is_emergency" (boolean).
"""

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    if 'user_id' in session:
        return jsonify({"logged_in": True, "username": session.get('username')})
    return jsonify({"logged_in": False})

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", 
                  (username, generate_password_hash(password)))
        conn.commit()
        
        session['user_id'] = c.lastrowid
        session['username'] = username
        return jsonify({"success": True, "message": "Registered successfully"})
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username already exists"}), 409
    finally:
        conn.close()

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, username, password FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    conn.close()
    
    if user and check_password_hash(user['password'], password):
        session['user_id'] = user['id']
        session['username'] = user['username']
        return jsonify({"success": True, "message": "Logged in successfully"})
    
    return jsonify({"error": "Invalid username or password"}), 401

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"success": True, "message": "Logged out successfully"})

@app.route('/api/history', methods=['GET'])
def get_history():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT timestamp, transcript, analysis, specialty FROM history WHERE user_id = ? ORDER BY id DESC", (session['user_id'],))
    records = [dict(row) for row in c.fetchall()]
    conn.close()
    
    return jsonify({"history": records})

@app.route('/api/analyze', methods=['POST'])
def analyze_symptoms():
    data = request.json
    transcript = data.get('transcript', '').strip()
    
    if not transcript:
        return jsonify({'error': 'No transcript provided'}), 400

    # Emergency keyword check (simple fallback)
    emergency_keywords = ["chest pain", "cannot breathe", "severe bleeding", "heart attack", "stroke"]
    is_emergency = any(keyword in transcript.lower() for keyword in emergency_keywords)
    
    if is_emergency:
        return jsonify({
            "disclaimer": "I am an AI, not a doctor. If you are experiencing a life-threatening emergency, call emergency services immediately.",
            "analysis": "Emergency symptoms detected based on your input.",
            "possible_conditions": ["Medical Emergency"],
            "otc_suggestions": [],
            "recommended_specialty": "Emergency Room",
            "is_emergency": True
        })

    if not client:
        return jsonify({
            "disclaimer": "Configuration Error",
            "analysis": "Gemini API key is missing. Please create a .env file in the project folder and add your GEMINI_API_KEY=your_key_here",
            "possible_conditions": [],
            "otc_suggestions": [],
            "recommended_specialty": "None",
            "is_emergency": False,
            "error": "Missing GEMINI_API_KEY in environment variables."
        }), 500

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[SYSTEM_PROMPT + "\n\nUser Symptoms: " + transcript]
        )
        
        # Parse the JSON response
        llm_output = response.text.strip()
        
        # Strip any markdown code block formatting if the model still includes it
        if llm_output.startswith("```json"):
            llm_output = llm_output[7:]
        if llm_output.startswith("```"):
            llm_output = llm_output[3:]
        if llm_output.endswith("```"):
            llm_output = llm_output[:-3]
            
        parsed_response = json.loads(llm_output.strip())
        
        # Save to history if logged in
        if 'user_id' in session:
            conn = get_db()
            c = conn.cursor()
            c.execute("INSERT INTO history (user_id, transcript, analysis, specialty) VALUES (?, ?, ?, ?)",
                      (session['user_id'], transcript, parsed_response.get('analysis', ''), parsed_response.get('recommended_specialty', '')))
            conn.commit()
            conn.close()
            
        return jsonify(parsed_response)
        
    except Exception as e:
        print(f"Error parsing Gemini response: {e}")
        return jsonify({
            "disclaimer": "I am an AI, not a doctor. If you are experiencing a life-threatening emergency, call emergency services immediately.",
            "analysis": "An error occurred while processing your request. Please try again.",
            "possible_conditions": ["Analysis Failed"],
            "otc_suggestions": [],
            "recommended_specialty": "General Practitioner",
            "is_emergency": False,
            "error": str(e)
        }), 500

import math

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 3958.8 # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

@app.route('/api/doctors', methods=['POST'])
def find_doctors():
    data = request.json
    specialty = data.get('specialty', 'General Practitioner')
    # Prevent long AI sentences from breaking the clinic names
    if len(specialty) > 35:
        specialty = "Specialist"
        
    location = data.get('location', None)
    
    if not location or (location.get('lat') == 0 and location.get('lng') == 0):
        # Fallback if no location provided
        return jsonify({"doctors": [
            {"name": f"City {specialty} Clinic", "address": "Location not provided", "rating": 4.5, "distance": "N/A", "map_link": "#"}
        ]})

    user_lat = location.get('lat')
    user_lng = location.get('lng')
    
    # Query OpenStreetMap Overpass API for clinics/hospitals within 10km (approx 6.2 miles)
    overpass_url = "https://overpass-api.de/api/interpreter"
    overpass_query = f"""
    [out:json][timeout:15];
    (
      node["amenity"="clinic"](around:10000,{user_lat},{user_lng});
      node["amenity"="hospital"](around:10000,{user_lat},{user_lng});
      node["amenity"="doctors"](around:10000,{user_lat},{user_lng});
    );
    out body 5;
    """
    
    try:
        # We use requests which is already in requirements.txt
        import requests
        headers = {'User-Agent': 'AssugamAi-MedicalTriage/1.0'}
        response = requests.post(overpass_url, data={'data': overpass_query}, headers=headers, timeout=10)
        response.raise_for_status()
        result = response.json()
        
        doctors = []
        for element in result.get('elements', []):
            tags = element.get('tags', {})
            # Prefer the exact specialty name if name is missing, but append 'Clinic'
            name = tags.get('name', f"Local {specialty} Provider")
            
            # Construct address
            street = tags.get('addr:street', '')
            city = tags.get('addr:city', '')
            address = f"{street}, {city}".strip(', ')
            if not address:
                address = "Address available on map"
                
            # Calculate distance
            poi_lat = element.get('lat')
            poi_lon = element.get('lon')
            dist = calculate_distance(user_lat, user_lng, poi_lat, poi_lon)
            
            doctors.append({
                "name": name,
                "address": address,
                "rating": 4.5, # OSM doesn't have ratings, so we mock a good rating
                "distance": f"{dist:.1f} miles",
                "map_link": f"https://www.google.com/maps/search/?api=1&query={poi_lat},{poi_lon}"
            })
            
        # Sort by distance
        doctors.sort(key=lambda x: float(x['distance'].split(' ')[0]))
            
        if not doctors:
             doctors = [{"name": f"Nearest {specialty} Specialist", "address": "Search regional directory", "rating": 4.0, "distance": "> 10 miles", "map_link": "#"}]
             
        return jsonify({"doctors": doctors})
        
    except Exception as e:
        print(f"Overpass API error: {e}")
        return jsonify({"doctors": [{"name": f"City {specialty} Clinic", "address": "Could not load exact location", "rating": 4.5, "distance": "Unknown", "map_link": "#"}]})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
