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

@app.route('/api/doctors', methods=['POST'])
def find_doctors():
    data = request.json
    specialty = data.get('specialty', 'General Practitioner')
    location = data.get('location', None) # Expected: {lat, lng}
    
    # Mocking a nearby doctor search
    mock_doctors = [
        {"name": f"City {specialty} Clinic", "address": "123 Main St, Local City", "rating": 4.5, "distance": "1.2 miles"},
        {"name": f"CarePlus {specialty}", "address": "456 Oak Avenue, Local City", "rating": 4.8, "distance": "3.5 miles"},
        {"name": f"First Health {specialty} Center", "address": "789 Pine Road, Local City", "rating": 4.2, "distance": "5.0 miles"}
    ]
    
    return jsonify({"doctors": mock_doctors})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
