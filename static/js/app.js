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

        // Voice Output using HTML5 SpeechSynthesis
        if ('speechSynthesis' in window) {
            window.speechSynthesis.cancel(); // Stop any currently playing audio
            const utterance = new SpeechSynthesisUtterance(data.analysis);
            utterance.rate = 1.0;
            // Optionally set voice here if needed, default is usually fine
            window.speechSynthesis.speak(utterance);
        }

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

    // --- Authentication & History Logic ---
    const authBtn = document.getElementById('auth-btn');
    const authModal = document.getElementById('auth-modal');
    const authTitle = document.getElementById('auth-title');
    const authUsername = document.getElementById('auth-username');
    const authPassword = document.getElementById('auth-password');
    const submitAuthBtn = document.getElementById('submit-auth-btn');
    const switchToRegister = document.getElementById('switch-to-register');
    const authError = document.getElementById('auth-error');
    
    const historyToggleBtn = document.getElementById('history-toggle-btn');
    const historyPanel = document.getElementById('history-panel');
    const closeHistoryBtn = document.getElementById('close-history-btn');
    const historyList = document.getElementById('history-list');

    let isLoginMode = true;
    let isLoggedIn = false;

    // Check login status on load
    checkAuthStatus();

    async function checkAuthStatus() {
        try {
            const res = await fetch('/api/auth/status');
            const data = await res.json();
            if (data.logged_in) {
                setLoggedInState(data.username);
            } else {
                setLoggedOutState();
                authModal.classList.remove('hidden');
            }
        } catch(e) { 
            console.error(e); 
            authModal.classList.remove('hidden');
        }
    }

    function setLoggedInState(username) {
        isLoggedIn = true;
        authBtn.innerHTML = `<i class="ph ph-sign-out"></i> Logout (${username})`;
        historyToggleBtn.classList.remove('hidden');
    }

    function setLoggedOutState() {
        isLoggedIn = false;
        authBtn.innerHTML = `<i class="ph ph-user"></i> Sign In`;
        historyToggleBtn.classList.add('hidden');
        historyPanel.classList.add('hidden');
    }

    authBtn.addEventListener('click', async () => {
        if (isLoggedIn) {
            // Logout
            await fetch('/api/auth/logout', { method: 'POST' });
            setLoggedOutState();
        } else {
            // Show modal
            authModal.classList.remove('hidden');
        }
    });

    const guestBtn = document.getElementById('guest-btn');
    if (guestBtn) {
        guestBtn.addEventListener('click', () => {
            authModal.classList.add('hidden');
        });
    }

    switchToRegister.addEventListener('click', (e) => {
        e.preventDefault();
        isLoginMode = !isLoginMode;
        if (isLoginMode) {
            authTitle.innerHTML = '<i class="ph ph-user"></i> Sign In';
            submitAuthBtn.textContent = 'Login';
            switchToRegister.textContent = "Don't have an account? Register";
        } else {
            authTitle.innerHTML = '<i class="ph ph-user-plus"></i> Create Account';
            submitAuthBtn.textContent = 'Register';
            switchToRegister.textContent = "Already have an account? Login";
        }
        authError.style.display = 'none';
    });

    submitAuthBtn.addEventListener('click', async () => {
        const username = authUsername.value.trim();
        const password = authPassword.value.trim();
        if(!username || !password) return;

        const endpoint = isLoginMode ? '/api/auth/login' : '/api/auth/register';
        submitAuthBtn.disabled = true;
        
        try {
            const res = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            const data = await res.json();
            
            if (res.ok) {
                authModal.classList.add('hidden');
                authUsername.value = '';
                authPassword.value = '';
                authError.style.display = 'none';
                setLoggedInState(username);
            } else {
                authError.textContent = data.error;
                authError.style.display = 'block';
            }
        } catch(e) {
            authError.textContent = 'Network error';
            authError.style.display = 'block';
        } finally {
            submitAuthBtn.disabled = false;
        }
    });

    // History Toggle
    historyToggleBtn.addEventListener('click', async () => {
        if (historyPanel.classList.contains('hidden')) {
            historyPanel.classList.remove('hidden');
            await loadHistory();
        } else {
            historyPanel.classList.add('hidden');
        }
    });

    closeHistoryBtn.addEventListener('click', () => {
        historyPanel.classList.add('hidden');
    });

    async function loadHistory() {
        historyList.innerHTML = '<div class="loader"></div>';
        try {
            const res = await fetch('/api/history');
            const data = await res.json();
            if (data.history && data.history.length > 0) {
                historyList.innerHTML = '';
                data.history.forEach(item => {
                    const card = document.createElement('div');
                    card.style.background = 'rgba(255,255,255,0.05)';
                    card.style.padding = '15px';
                    card.style.borderRadius = '8px';
                    card.style.border = '1px solid rgba(255,255,255,0.1)';
                    card.innerHTML = `
                        <p style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 5px;">${new Date(item.timestamp).toLocaleString()}</p>
                        <p style="font-size: 0.9rem; font-style: italic; margin-bottom: 10px;">"${item.transcript}"</p>
                        <p style="font-size: 0.95rem;"><strong>Analysis:</strong> ${item.analysis}</p>
                        <p style="font-size: 0.85rem; color: var(--accent-primary); margin-top: 5px;">Recommended: ${item.specialty}</p>
                    `;
                    historyList.appendChild(card);
                });
            } else {
                historyList.innerHTML = '<p style="color: var(--text-muted);">No history found.</p>';
            }
        } catch (e) {
            historyList.innerHTML = '<p style="color: var(--danger);">Failed to load history.</p>';
        }
    }
});

// --- Splash Screen Logic ---
window.addEventListener('load', () => {
    const splash = document.getElementById('splash-screen');
    if (splash) {
        // Show splash for 2.5 seconds before fading out
        setTimeout(() => {
            splash.style.opacity = '0';
            // Wait for CSS transition (0.8s) to complete before hiding
            setTimeout(() => {
                splash.style.visibility = 'hidden';
            }, 800); 
        }, 2500); 
    }
});
