import os
import json
from flask import Flask, render_template, request, jsonify
from google import genai
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

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
    location = data.get('location', None)
    
    if not location or (location.get('lat') == 0 and location.get('lng') == 0):
        # Fallback if no location provided
        return jsonify({"doctors": [
            {"name": f"City {specialty} Clinic", "address": "Location not provided", "rating": 4.5, "distance": "N/A"}
        ]})

    user_lat = location.get('lat')
    user_lng = location.get('lng')
    
    # Query OpenStreetMap Overpass API for clinics/hospitals within 10km (approx 6.2 miles)
    overpass_url = "http://overpass-api.de/api/interpreter"
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
        response = requests.post(overpass_url, data={'data': overpass_query}, timeout=10)
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
                "distance": f"{dist:.1f} miles"
            })
            
        # Sort by distance
        doctors.sort(key=lambda x: float(x['distance'].split(' ')[0]))
            
        if not doctors:
             doctors = [{"name": f"Nearest {specialty} Specialist", "address": "Search regional directory", "rating": 4.0, "distance": "> 10 miles"}]
             
        return jsonify({"doctors": doctors})
        
    except Exception as e:
        print(f"Overpass API error: {e}")
        return jsonify({"doctors": [{"name": f"City {specialty} Clinic", "address": "Could not load exact location", "rating": 4.5, "distance": "Unknown"}]})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
