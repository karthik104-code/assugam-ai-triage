document.addEventListener('DOMContentLoaded', () => {
    const recordBtn = document.getElementById('record-btn');
    const statusText = document.getElementById('status-text');
    const transcriptText = document.getElementById('transcript-text');
    const resultsArea = document.getElementById('results-area');
    const emergencyAlert = document.getElementById('emergency-alert');
    const analysisText = document.getElementById('analysis-text');
    const conditionsList = document.getElementById('conditions-list');
    const otcList = document.getElementById('otc-list');
    const specialtyText = document.getElementById('specialty-text');
    const doctorsList = document.getElementById('doctors-list');
    const submitBtn = document.getElementById('submit-btn');

    // Check Web Speech API support
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        statusText.textContent = "Your browser doesn't support Voice-to-Text.";
        statusText.style.color = "var(--danger)";
        recordBtn.disabled = true;
        return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    let isRecording = false;
    let finalTranscript = '';

    recordBtn.addEventListener('click', () => {
        if (isRecording) {
            recognition.stop();
        } else {
            finalTranscript = '';
            transcriptText.value = 'Listening...';
            recognition.start();
        }
    });

    recognition.onstart = () => {
        isRecording = true;
        recordBtn.classList.add('recording');
        statusText.textContent = 'Listening... Tap to stop';
        statusText.classList.add('recording');
        resultsArea.classList.add('hidden');
    };

    recognition.onresult = (event) => {
        let interimTranscript = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
            if (event.results[i].isFinal) {
                finalTranscript += event.results[i][0].transcript;
            } else {
                interimTranscript += event.results[i][0].transcript;
            }
        }
        transcriptText.value = finalTranscript + interimTranscript;
    };

    recognition.onerror = (event) => {
        console.error("Speech recognition error", event.error);
        statusText.textContent = `Error: ${event.error}. Try again.`;
        resetUI();
    };

    recognition.onend = () => {
        resetUI();
        if (finalTranscript.trim().length > 0) {
            processTranscript(finalTranscript);
        } else {
            statusText.textContent = "Didn't catch that. Tap to try again or type your problem.";
            transcriptText.value = "";
        }
    };

    submitBtn.addEventListener('click', () => {
        const text = transcriptText.value.trim();
        if (text.length > 0) {
            processTranscript(text);
        } else {
            statusText.textContent = "Please enter your symptoms first.";
            statusText.style.color = "var(--warning)";
        }
    });

    function resetUI() {
        isRecording = false;
        recordBtn.classList.remove('recording');
        statusText.classList.remove('recording');
        statusText.textContent = 'Tap to describe your symptoms';
    }

    async function processTranscript(text) {
        statusText.textContent = 'Analyzing symptoms...';
        statusText.style.color = "var(--text-muted)";
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="ph-fill ph-spinner-gap spin"></i> Analyzing...';
        
        try {
            const response = await fetch('/api/analyze', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ transcript: text }),
            });

            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.error || 'Network response was not ok');
            }
            
            displayResults(data);
            
            // After analysis, fetch doctors if it's not a severe emergency requiring immediate 911
            // Even in emergency we could show nearest hospitals, but let's stick to the flow
            if (data.recommended_specialty) {
                fetchDoctors(data.recommended_specialty);
            }

        } catch (error) {
            console.error('Error analyzing symptoms:', error);
            statusText.textContent = `Error: ${error.message}`;
            statusText.style.color = "var(--danger)";
        } finally {
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<i class="ph-fill ph-paper-plane-right"></i> Analyze';
        }
    }

    function displayResults(data) {
        statusText.textContent = 'Analysis complete.';
        resultsArea.classList.remove('hidden');

        // Handle Emergency
        if (data.is_emergency) {
            emergencyAlert.classList.remove('hidden');
            document.documentElement.style.setProperty('--accent-primary', 'var(--danger)');
        } else {
            emergencyAlert.classList.add('hidden');
            document.documentElement.style.setProperty('--accent-primary', '#3b82f6'); // reset to blue
        }

        analysisText.textContent = data.analysis;
        specialtyText.textContent = data.recommended_specialty;

        // Render Conditions
        conditionsList.innerHTML = '';
        data.possible_conditions.forEach(condition => {
            const span = document.createElement('span');
            span.className = 'tag';
            span.textContent = condition;
            conditionsList.appendChild(span);
        });

        // Render OTC
        otcList.innerHTML = '';
        if (data.otc_suggestions && data.otc_suggestions.length > 0) {
            data.otc_suggestions.forEach(otc => {
                const span = document.createElement('span');
                span.className = 'tag';
                span.textContent = otc;
                otcList.appendChild(span);
            });
        } else {
            otcList.innerHTML = '<span style="color: var(--text-muted); font-style: italic;">None suggested. Consult a professional.</span>';
        }
    }

    async function fetchDoctors(specialty) {
        doctorsList.innerHTML = '<div class="loader"></div>';

        let userLat = 0;
        let userLng = 0;

        // Try to get real location
        try {
            const position = await new Promise((resolve, reject) => {
                if (!navigator.geolocation) {
                    reject(new Error('Geolocation not supported'));
                } else {
                    navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 10000 });
                }
            });
            userLat = position.coords.latitude;
            userLng = position.coords.longitude;
        } catch (error) {
            console.warn('Could not get real location, falling back to mock coordinates:', error.message);
        }

        try {
            const response = await fetch('/api/doctors', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ 
                    specialty: specialty,
                    location: { lat: userLat, lng: userLng }

                }),
            });

            if (!response.ok) throw new Error('Network response was not ok');

            const data = await response.json();
            
            doctorsList.innerHTML = '';
            if (data.doctors && data.doctors.length > 0) {
                data.doctors.forEach(doc => {
                    const docCard = document.createElement('div');
                    docCard.className = 'doctor-card';
                    docCard.innerHTML = `
                        <div class="doctor-info">
                            <h4>
                                <a href="${doc.map_link}" target="_blank" style="color: inherit; text-decoration: none;">
                                    ${doc.name} <i class="ph ph-arrow-square-out" style="font-size: 0.8em; color: var(--accent-primary);"></i>
                                </a>
                            </h4>
                            <p><i class="ph ph-map-pin"></i> ${doc.address} (${doc.distance})</p>
                        </div>
                        <div class="doctor-rating">
                            <i class="ph-fill ph-star"></i> ${doc.rating}
                        </div>
                    `;
                    doctorsList.appendChild(docCard);
                });
            } else {
                doctorsList.innerHTML = '<p style="color: var(--text-muted);">No doctors found nearby for this specialty.</p>';
            }

        } catch (error) {
            console.error('Error fetching doctors:', error);
            doctorsList.innerHTML = '<p style="color: var(--danger);">Failed to load provider recommendations.</p>';
        }
    }
});
