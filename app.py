from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
import requests
import random
import datetime
import os
from dotenv import load_dotenv
import google.generativeai as genai
import json
import time

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app, supports_credentials=True)

# ThingSpeak Configuration
THINGSPEAK_CHANNEL_ID = "3072910"
THINGSPEAK_READ_API_KEY = "FC4MV1CFXV3MWF36"
THINGSPEAK_WRITE_API_KEY = "6SP78VL51TQZKI7E"
THINGSPEAK_BASE_URL = "https://api.thingspeak.com"

# Configure Gemini AI (optional)
gemini_api_key = os.getenv('GEMINI_API_KEY')
if gemini_api_key:
    genai.configure(api_key=gemini_api_key)

# Global state variables (similar to Streamlit session state)
app_state = {
    'connection_status': 'Unknown',
    'pump_status': 'OFF',
    'pump_logs': [],
    'last_update': None,
    'chat_history': []
}

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/dashboard')
def dashboard():
    return app.send_static_file('dashboard.html')

@app.route('/api/login', methods=['POST'])
def login():
    """Handle login authentication - same as Streamlit logic"""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        # Same authentication logic as Streamlit
        if username == 'farmer' and password == '1234':
            return jsonify({
                'success': True,
                'message': 'Login successful! Redirecting...',
                'username': username
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Invalid username or password'
            }), 401
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Login error: {str(e)}'
        }), 500

@app.route('/api/logout', methods=['POST'])
def logout():
    """Handle logout"""
    return jsonify({'success': True, 'message': 'Logged out successfully'})

def get_thingspeak_data_cached(results=24):
    """Fetch real sensor data from ThingSpeak with caching - same logic as Streamlit"""
    try:
        # Fetch channel feeds (all fields)
        url = f"{THINGSPEAK_BASE_URL}/channels/{THINGSPEAK_CHANNEL_ID}/feeds.json"
        params = {
            'api_key': THINGSPEAK_READ_API_KEY,
            'results': results
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Parse the data
            feeds = data.get('feeds', [])
            
            if not feeds:
                print("No data found in ThingSpeak channel. Using simulated data.")
                return get_simulated_data()
            
            # Extract data from feeds with better validation
            times = []
            pump_status = []
            temperatures = []
            humidity = []
            soil_moisture = []
            
            for feed in feeds:
                try:
                    # Parse timestamp with better error handling
                    if feed.get('created_at'):
                        timestamp_str = feed['created_at']
                        if timestamp_str.endswith('Z'):
                            timestamp_str = timestamp_str.replace('Z', '+00:00')
                        
                        timestamp = datetime.datetime.fromisoformat(timestamp_str)
                        timestamp = timestamp.replace(tzinfo=None)
                        times.append(timestamp.isoformat())
                        
                        # Extract field values with validation
                        def safe_float(value, default):
                            try:
                                if value is not None and value != '':
                                    return float(value)
                                return default
                            except (ValueError, TypeError):
                                return default
                        
                        pump_val = safe_float(feed.get('field1'), 0)
                        temp_val = safe_float(feed.get('field2'), 25)
                        humid_val = safe_float(feed.get('field3'), 60)
                        moisture_val = safe_float(feed.get('field4'), 50)
                        
                        # Validate ranges
                        pump_val = max(0, min(1, pump_val))
                        temp_val = max(-10, min(60, temp_val))
                        humid_val = max(0, min(100, humid_val))
                        moisture_val = max(0, min(100, moisture_val))
                        
                        pump_status.append(pump_val)
                        temperatures.append(temp_val)
                        humidity.append(humid_val)
                        soil_moisture.append(moisture_val)
                        
                except Exception as feed_error:
                    print(f"Skipping invalid feed entry: {feed_error}")
                    continue
            
            if not times:
                print("No valid timestamp data found. Using simulated data.")
                return get_simulated_data()
            
            # Update global state
            app_state['connection_status'] = 'Online'
            app_state['last_update'] = datetime.datetime.now()
            
            # Get current pump status
            if pump_status:
                current_pump = pump_status[-1]
                app_state['pump_status'] = 'ON' if current_pump == 1 else 'OFF'
            
            # Create processed data list
            processed_data = []
            for i in range(len(times)):
                processed_data.append({
                    'timestamp': times[i],
                    'pump_status': pump_status[i],
                    'temperature': temperatures[i],
                    'humidity': humidity[i],
                    'soil_moisture': soil_moisture[i]
                })
            
            return {
                'success': True,
                'data': processed_data,
                'times': times,
                'pump_status': pump_status,
                'temperature': temperatures,
                'humidity': humidity,
                'soil_moisture': soil_moisture,
                'source': 'ThingSpeak',
                'latest': processed_data[-1] if processed_data else None,
                'channel_info': {
                    'channel_id': data.get('channel', {}).get('id'),
                    'name': data.get('channel', {}).get('name', 'Smart Irrigation'),
                    'last_entry_id': data.get('channel', {}).get('last_entry_id')
                }
            }
            
        else:
            print(f"ThingSpeak API Error: Status {response.status_code}")
            app_state['connection_status'] = 'Offline'
            return get_simulated_data()
            
    except requests.exceptions.Timeout:
        print("ThingSpeak request timed out")
        app_state['connection_status'] = 'Offline'
        return get_simulated_data()
        
    except requests.exceptions.RequestException as e:
        print(f"Network error: {e}")
        app_state['connection_status'] = 'Offline'
        return get_simulated_data()
        
    except Exception as e:
        print(f"Unexpected error parsing ThingSpeak data: {e}")
        app_state['connection_status'] = 'Offline'
        return get_simulated_data()

def get_simulated_data():
    """Generate simulated sensor data (fallback) - same as Streamlit"""
    current_time = datetime.datetime.now()
    times = [(current_time - datetime.timedelta(hours=i)).isoformat() for i in range(24, 0, -1)]
    
    # Simulate realistic agricultural data
    soil_moisture = [random.randint(20, 80) for _ in range(24)]
    temperature = [random.randint(18, 35) for _ in range(24)]
    humidity = [random.randint(40, 85) for _ in range(24)]
    pump_status = [random.choice([0, 1]) for _ in range(24)]
    
    # Create processed data
    processed_data = []
    for i in range(24):
        processed_data.append({
            'timestamp': times[i],
            'pump_status': pump_status[i],
            'temperature': temperature[i],
            'humidity': humidity[i],
            'soil_moisture': soil_moisture[i]
        })
    
    return {
        'success': True,
        'data': processed_data,
        'times': times,
        'soil_moisture': soil_moisture,
        'temperature': temperature,
        'humidity': humidity,
        'pump_status': pump_status,
        'source': 'Simulated',
        'latest': processed_data[-1] if processed_data else None
    }

@app.route('/api/thingspeak/data')
def get_thingspeak_data():
    """API endpoint to fetch sensor data"""
    try:
        data = get_thingspeak_data_cached()
        return jsonify(data)
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Data fetch error: {str(e)}'
        }), 500

def control_pump_logic(action):
    """Control pump function - EXACT same logic as Streamlit"""
    try:
        # Generate realistic sensor values
        field_value = 1 if action == 'ON' else 0
        
        # Generate random but realistic sensor data
        temperature = round(random.uniform(18, 35), 1)  # 18-35°C
        humidity = round(random.uniform(40, 85), 1)     # 40-85%
        soil_moisture = round(random.uniform(25, 80), 1)  # 25-80%
        
        # Send ALL 4 fields in one request
        url = f"{THINGSPEAK_BASE_URL}/update"
        
        params = {
            'api_key': THINGSPEAK_WRITE_API_KEY,
            'field1': field_value,      # Pump status (0 or 1)
            'field2': temperature,      # Temperature in °C
            'field3': humidity,         # Humidity in %
            'field4': soil_moisture     # Soil moisture in %
        }
        
        print(f"Sending to ThingSpeak: {params}")
        
        response = requests.get(url, params=params, timeout=10)
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if response.status_code == 200 and response.text.isdigit():
            # ThingSpeak returns entry ID as plain text on success
            entry_id = response.text
            app_state['pump_status'] = action
            
            # Enhanced log with all sensor values
            log_entry = f"✅ {timestamp}: Pump {action} | Entry: {entry_id} | T: {temperature}°C | H: {humidity}% | SM: {soil_moisture}%"
            app_state['pump_logs'].append(log_entry)
            
            return True, f"Pump turned {action}! Sensors updated: T:{temperature}°C, H:{humidity}%, SM:{soil_moisture}% (Entry: {entry_id})", {
                'temperature': temperature,
                'humidity': humidity,
                'soil_moisture': soil_moisture,
                'entry_id': entry_id
            }
        else:
            log_entry = f"❌ {timestamp}: Failed - Status: {response.status_code}, Response: {response.text}"
            app_state['pump_logs'].append(log_entry)
            return False, f"Failed! Status: {response.status_code}, Response: {response.text}", None
            
    except requests.exceptions.RequestException as e:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"❌ {timestamp}: Network error - {str(e)}"
        app_state['pump_logs'].append(log_entry)
        return False, f"Network error: {str(e)}", None
    except Exception as e:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"❌ {timestamp}: Unexpected error - {str(e)}"
        app_state['pump_logs'].append(log_entry)
        return False, f"Unexpected error: {str(e)}", None

@app.route('/api/pump/control', methods=['POST'])
def control_pump():
    """Control pump via ThingSpeak - same as Streamlit"""
    try:
        data = request.get_json()
        action = data.get('action')  # 'ON' or 'OFF'
        
        if action not in ['ON', 'OFF']:
            return jsonify({
                'success': False,
                'message': 'Invalid action. Use ON or OFF.'
            }), 400
        
        success, message, sensor_data = control_pump_logic(action)
        
        if success:
            return jsonify({
                'success': True,
                'message': message,
                'entry_id': sensor_data['entry_id'] if sensor_data else None,
                'sensor_data': sensor_data,
                'pump_status': action
            })
        else:
            return jsonify({
                'success': False,
                'message': message
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Pump control error: {str(e)}'
        }), 500

def get_bot_response_logic(message, language='English'):
    """Chatbot logic - EXACT same as Streamlit"""
    try:
        # Try to use Gemini API if key is available
        if gemini_api_key:
            try:
                model = genai.GenerativeModel('gemini-1.5-flash')
                
                # Language-specific prompts for agricultural advice
                language_prompts = {
                    'English': f"""You are an expert agricultural advisor helping farmers with irrigation and crop management. 
                    Provide practical, actionable advice in English. Keep responses under 150 words.
                    Focus on: irrigation techniques, crop selection, soil health, fertilizers, pest control, and weather management.
                    Be specific and helpful.
                    
                    Farmer's question: {message}""",
                    
                    'Hindi': f"""आप एक कृषि विशेषज्ञ हैं जो किसानों को सिंचाई और फसल प्रबंधन में मदद कर रहे हैं। 
                    हिंदी में व्यावहारिक सलाह दें। जवाब 150 शब्दों से कम रखें।
                    मुख्य विषय: सिंचाई तकनीक, फसल चयन, मिट्टी स्वास्थ्य, उर्वरक, कीट नियंत्रण।
                    स्पष्ट और उपयोगी सलाह दें।
                    
                    किसान का प्रश्न: {message}""",
                    
                    'Telugu': f"""మీరు వ్యవసాయ నిపుణులు మరియు రైతులకు నీటిపారుదల మరియు పంట నిర్వహణలో సహాయం చేస్తున్నారు.
                    తెలుగులో ఆచరణీయ సలహా ఇవ్వండి. సమాధానాలను 150 పదాలకు పరిమితం చేయండి.
                    ప్రధాన అంశాలు: నీటిపారుదల, పంట ఎంపిక, మట్టి ఆరోగ్యం, ఎరువులు, కీటక నియంత్రణ.
                    స్పష్టమైన మరియు ఉపయోగకరమైన సలహా ఇవ్వండి.
                    
                    రైతు ప్రశ్న: {message}"""
                }
                
                prompt = language_prompts.get(language, language_prompts['English'])
                
                response = model.generate_content(prompt)
                
                if response and response.text:
                    return response.text
                else:
                    return "I couldn't generate a response. Please try rephrasing your question."
                    
            except Exception as api_error:
                print(f"Gemini API Error: {api_error}")
                return get_fallback_response_logic(message, language)
            
        else:
            return get_fallback_response_logic(message, language)
            
    except Exception as e:
        error_messages = {
            'English': f"I'm experiencing technical difficulties. Please try again. If this persists, check your API key.",
            'Hindi': f"तकनीकी समस्या हो रही है। कृपया फिर कोशिश करें। यदि समस्या बनी रहे तो API key जांचें।",
            'Telugu': f"సాంకేతిక సమస్య ఉంది. దయచేసి మళ్లీ ప్రయత్నించండి. సమస్య కొనసాగితే API key తనిఖీ చేయండి."
        }
        return error_messages.get(language, error_messages['English'])

def get_fallback_response_logic(message, language='English'):
    """Enhanced fallback responses - same as Streamlit"""
    message_lower = message.lower()
    
    responses = {
        'English': {
            'tomato': "🍅 **Tomato Care**: Water tomatoes 1-2 times per week, deeply. Check soil 2 inches down - if dry, water. Avoid overhead watering to prevent diseases. Use drip irrigation or water at soil level. During fruiting, consistent moisture prevents cracking.",
            
            'water': "💧 **Watering Guide**: Water early morning (6-8 AM) for best absorption. Deep, less frequent watering encourages strong roots. Check soil moisture 2-3 inches deep. Most vegetables need 1-1.5 inches of water per week.",
            
            'irrigation': "🌊 **Irrigation Tips**: Drip irrigation is most efficient - saves 30-50% water. Water slowly and deeply rather than frequent shallow watering. Use moisture sensors to automate timing. Group plants by water needs.",
            
            'pest': "🐛 **Pest Management**: Inspect plants weekly for early detection. Use beneficial insects like ladybugs. Neem oil spray works well for aphids and soft-bodied pests. Remove affected leaves immediately. Avoid overwatering which attracts pests.",
            
            'soil': "🌱 **Soil Health**: Test soil pH annually (6.0-7.0 is ideal for most crops). Add compost to improve structure and nutrients. Mulch retains moisture and suppresses weeds. Avoid walking on wet soil to prevent compaction.",
            
            'fertilizer': "🥕 **Fertilization**: Use balanced N-P-K fertilizer based on soil test. Apply nitrogen for leafy growth, phosphorus for roots/flowers, potassium for fruit development. Organic options like compost provide slow-release nutrients.",
            
            'disease': "🦠 **Disease Prevention**: Ensure good air circulation between plants. Water at soil level to keep leaves dry. Rotate crops annually. Remove infected plant material immediately. Use disease-resistant varieties when possible.",
            
            'default': "🌱 **Agricultural Expert**: I can help with irrigation, crop care, soil management, pest control, and fertilization. For tomato watering: deep watering 1-2x per week. What specific farming challenge can I help you with?"
        },
        
        'Hindi': {
            'tomato': "🍅 **टमाटर की देखभाल**: सप्ताह में 1-2 बार गहरा पानी दें। 2 इंच गहराई में मिट्टी चेक करें। पत्तियों पर पानी न डालें। ड्रिप सिंचाई बेहतर है।",
            
            'water': "💧 **पानी देने की विधि**: सुबह 6-8 बजे पानी दें। गहरा पानी दें, कम बार। 2-3 इंच गहराई में नमी चेक करें। सप्ताह में 1-1.5 इंच पानी चाहिए।",
            
            'irrigation': "🌊 **सिंचाई तकनीक**: ड्रिप सिंचाई 30-50% पानी बचाती है। धीरे-धीरे गहरा पानी दें। नमी सेंसर का उपयोग करें।",
            
            'pest': "🐛 **कीट प्रबंधन**: साप्ताहिक जांच करें। लेडीबग जैसे लाभकारी कीट पालें। नीम तेल का छिड़काव करें। संक्रमित पत्तियां तुरंत हटाएं।",
            
            'soil': "🌱 **मिट्टी स्वास्थ्य**: pH 6.0-7.0 रखें। कंपोस्ट डालें। मल्चिंग करें। गीली मिट्टी पर न चलें।",
            
            'fertilizer': "🥕 **उर्वरक**: मिट्टी जांच के आधार पर NPK उर्वरक दें। जैविक खाद बेहतर है।",
            
            'disease': "🦠 **रोग नियंत्रण**: पौधों में हवा का संचार रखें। मिट्टी के स्तर पर पानी दें। फसल चक्र अपनाएं।",
            
            'default': "🌱 **कृषि विशेषज्ञ**: मैं सिंचाई, फसल देखभाल, मिट्टी प्रबंधन में मदद करूंगा। टमाटर के लिए: सप्ताह में 1-2 बार गहरा पानी। आपकी क्या समस्या है?"
        },
        
        'Telugu': {
            'tomato': "🍅 **టమాట్ల సంరక్షణ**: వారానికి 1-2 సార్లు లోతుగా నీరు పోయండి। 2 అంగుళాల లోతులో మట్టి తనిఖీ చేయండి। ఆకులపై నీరు పోయవద్దు।",
            
            'water': "💧 **నీరు పోసే విధానం**: ఉదయం 6-8 గంటలలో నీరు పోయండి। లోతుగా, తక్కువసార్లు। 2-3 అంగుళాల లోతులో తేమ చూడండి।",
            
            'irrigation': "🌊 **నీటిపారుదల**: డ్రిప్ ఇరిగేషన్ 30-50% నీరు ఆదా చేస్తుంది। నెమ్మదిగా లోతుగా నీరు పోయండి।",
            
            'pest': "🐛 **కీటక నియంత్రణ**: వారానికొకసారి తనిఖీ చేయండి। మంచి కీటకాలను పెంచండి। వేప నూనె స్ప్రే చేయండి।",
            
            'soil': "🌱 **నేల ఆరోగ్యం**: pH 6.0-7.0 ఉంచండి। కంపోస్ట్ వేయండి। మల్చింగ్ చేయండి।",
            
            'fertilizer': "🥕 **ఎరువులు**: మట్టి పరీక్ష ఆధారంగా NPK ఎరువు వేయండి. సేంద్రీయ ఎరువులు మంచివి।",
            
            'disease': "🦠 **వ్యాధి నివారణ**: మొక్కల మధ్య గాలి తిరిగేలా వేయండి। మట్టి స్థాయిలో నీరు పోయండి।",
            
            'default': "🌱 **వ్యవసాయ నిపుణుడు**: నేను నీటిపారుదల, పంట సంరక్షణ, నేల నిర్వహణలో సహాయం చేస్తాను। టమాటోలకు: వారానికి 1-2 సార్లు లోతుగా నీరు. మీ సమస్య ఏమిటి?"
        }
    }
    
    # Smart keyword matching
    lang_responses = responses.get(language, responses['English'])
    
    # Check for keywords in the message
    for keyword, response in lang_responses.items():
        if keyword != 'default' and keyword in message_lower:
            return response
    
    # Return default response if no keyword matches
    return lang_responses['default']

@app.route('/api/chat', methods=['POST'])
def chat_with_ai():
    """Handle chatbot interactions - same as Streamlit"""
    try:
        data = request.get_json()
        message = data.get('message', '')
        language = data.get('language', 'English')
        
        if not message.strip():
            return jsonify({
                'success': False,
                'message': 'Message cannot be empty'
            }), 400
        
        # Add to chat history (like Streamlit session state)
        user_message = message.strip()
        bot_response = get_bot_response_logic(user_message, language)
        
        app_state['chat_history'].append((user_message, bot_response))
        
        # Keep only last 50 conversations to manage memory
        if len(app_state['chat_history']) > 50:
            app_state['chat_history'] = app_state['chat_history'][-50:]
        
        return jsonify({
            'success': True,
            'response': bot_response,
            'source': 'Gemini AI' if gemini_api_key else 'Fallback System'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Chat error: {str(e)}'
        }), 500

@app.route('/api/alerts')
def get_alerts():
    """Generate smart alerts based on current sensor data - same logic as Streamlit"""
    try:
        # Get latest sensor data
        data = get_thingspeak_data_cached()
        
        if data.get('success') and data.get('latest'):
            current = data['latest']
            alerts = generate_alerts_logic(current)
            return jsonify({
                'success': True,
                'alerts': alerts
            })
        
        return jsonify({
            'success': True,
            'alerts': []
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Alert generation error: {str(e)}'
        }), 500

def generate_alerts_logic(sensor_data):
    """Generate alerts based on sensor readings - same as Streamlit"""
    alerts = []
    
    moisture = sensor_data.get('soil_moisture', 50)
    temperature = sensor_data.get('temperature', 25)
    humidity = sensor_data.get('humidity', 60)
    pump_status = sensor_data.get('pump_status', 0)
    
    # Critical moisture conditions (highest priority)
    if moisture < 30:
        if pump_status == 0:  # OFF
            alerts.append({
                'type': 'critical',
                'title': '⚠️ Urgent: Low Moisture Alert',
                'message': f'Soil moisture is critically low ({moisture:.1f}%). Turn on irrigation immediately!'
            })
        else:
            alerts.append({
                'type': 'info',
                'title': '💧 Active Irrigation',
                'message': f'Pump is ON for low moisture ({moisture:.1f}%). Monitor for improvement in 15-30 minutes.'
            })
    
    elif moisture < 40:
        if pump_status == 0:
            alerts.append({
                'type': 'warning',
                'title': '⚠️ Warning: Low Moisture',
                'message': f'Soil moisture is getting low ({moisture:.1f}%). Consider irrigation soon.'
            })
        else:
            alerts.append({
                'type': 'success',
                'title': '💧 Good: Active Irrigation',
                'message': f'Pump is ON for low-normal moisture ({moisture:.1f}%). This should help improve levels.'
            })
    
    # High moisture conditions
    elif moisture > 80:
        if pump_status == 1:  # ON
            alerts.append({
                'type': 'warning',
                'title': '⚠️ Stop Irrigation',
                'message': f'Soil moisture is very high ({moisture:.1f}%). Turn OFF pump to prevent waterlogging!'
            })
        else:
            alerts.append({
                'type': 'success',
                'title': '✅ Excellent Moisture',
                'message': f'Soil moisture is very high ({moisture:.1f}%). No irrigation needed.'
            })
    
    elif moisture > 70:
        if pump_status == 1:
            alerts.append({
                'type': 'warning',
                'title': '⚠️ Caution',
                'message': f'Soil moisture is high ({moisture:.1f}%) but pump is ON. Consider turning OFF soon.'
            })
        else:
            alerts.append({
                'type': 'success',
                'title': '✅ Great Moisture Levels',
                'message': f'Soil moisture is high ({moisture:.1f}%). Plants are well-watered.'
            })
    
    # Optimal range
    elif 40 <= moisture <= 70:
        if pump_status == 1:
            alerts.append({
                'type': 'success',
                'title': '✅ Perfect: Active Irrigation',
                'message': f'Pump is ON and soil moisture is optimal ({moisture:.1f}%). Monitor and turn OFF when it reaches 70%+.'
            })
        else:
            alerts.append({
                'type': 'success',
                'title': '✅ Optimal Moisture Range',
                'message': f'Soil moisture is in the ideal range ({moisture:.1f}%) for most crops. Continue monitoring.'
            })
    
    # Weather-based recommendations
    if temperature > 30 and humidity < 50:
        alerts.append({
            'type': 'warning',
            'title': '🌡️ Weather Alert',
            'message': f'High temperature ({temperature:.1f}°C) and low humidity ({humidity:.1f}%). Plants may need extra water today.'
        })
    
    if temperature > 35:
        alerts.append({
            'type': 'critical',
            'title': '🔥 Heat Warning',
            'message': f'Very high temperature ({temperature:.1f}°C)! Ensure adequate irrigation and consider shade protection.'
        })
    
    # Pump status context
    if pump_status == 1:
        alerts.append({
            'type': 'info',
            'title': '💡 Pump Status',
            'message': 'Irrigation is currently ACTIVE. Expected soil moisture improvement in 15-30 minutes.'
        })
    
    # Default message if no specific recommendations
    if not alerts:
        alerts.append({
            'type': 'info',
            'title': '📊 Status',
            'message': 'All parameters are within normal range. Continue regular monitoring.'
        })
    
    return alerts

@app.route('/api/pump/logs')
def get_pump_logs():
    """Get pump control logs"""
    try:
        return jsonify({
            'success': True,
            'logs': app_state['pump_logs'][-20:],  # Last 20 logs
            'total_logs': len(app_state['pump_logs'])
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error fetching logs: {str(e)}'
        }), 500

@app.route('/api/pump/logs/clear', methods=['POST'])
def clear_pump_logs():
    """Clear pump logs"""
    try:
        app_state['pump_logs'] = []
        return jsonify({
            'success': True,
            'message': 'Pump logs cleared successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error clearing logs: {str(e)}'
        }), 500

@app.route('/api/test/sensor', methods=['POST'])
def send_test_sensor_data():
    """Send test sensor data to ThingSpeak without changing pump status - same as Streamlit"""
    try:
        # Get current pump status first
        current_pump = 0
        try:
            status_url = f"{THINGSPEAK_BASE_URL}/channels/{THINGSPEAK_CHANNEL_ID}/feeds/last.json?api_key={THINGSPEAK_READ_API_KEY}"
            status_response = requests.get(status_url, timeout=5)
            if status_response.status_code == 200:
                status_data = status_response.json()
                if status_data and 'field1' in status_data:
                    current_pump = int(float(status_data['field1']) if status_data['field1'] else 0)
        except:
            pass
        
        # Generate new sensor values
        temperature = round(random.uniform(18, 35), 1)
        humidity = round(random.uniform(40, 85), 1)
        soil_moisture = round(random.uniform(25, 80), 1)
        
        # Send all fields
        url = f"{THINGSPEAK_BASE_URL}/update"
        params = {
            'api_key': THINGSPEAK_WRITE_API_KEY,
            'field1': current_pump,     # Keep current pump status
            'field2': temperature,      # New temperature
            'field3': humidity,         # New humidity  
            'field4': soil_moisture     # New soil moisture
        }
        
        print(f"Test sensor data: {params}")
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200 and response.text.isdigit():
            entry_id = response.text
            return jsonify({
                'success': True,
                'message': f'Sensors updated: T:{temperature}°C, H:{humidity}%, SM:{soil_moisture}% (Entry: {entry_id})',
                'entry_id': entry_id,
                'sensor_data': {
                    'temperature': temperature,
                    'humidity': humidity,
                    'soil_moisture': soil_moisture
                }
            })
        else:
            return jsonify({
                'success': False,
                'message': f'Failed: {response.status_code} - {response.text}'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

@app.route('/api/status')
def get_system_status():
    """Get overall system status - like Streamlit sidebar info"""
    try:
        return jsonify({
            'success': True,
            'status': {
                'connection_status': app_state['connection_status'],
                'pump_status': app_state['pump_status'],
                'last_update': app_state['last_update'].isoformat() if app_state['last_update'] else None,
                'total_logs': len(app_state['pump_logs']),
                'chat_history_count': len(app_state['chat_history']),
                'thingspeak_config': {
                    'channel_id': THINGSPEAK_CHANNEL_ID,
                    'read_api_key': THINGSPEAK_READ_API_KEY[:8] + "...",
                    'write_api_key': THINGSPEAK_WRITE_API_KEY[:8] + "..."
                }
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Status error: {str(e)}'
        }), 500

@app.route('/api/chat/history')
def get_chat_history():
    """Get chat history"""
    try:
        return jsonify({
            'success': True,
            'chat_history': app_state['chat_history'][-20:],  # Last 20 conversations
            'total_conversations': len(app_state['chat_history'])
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error fetching chat history: {str(e)}'
        }), 500

@app.route('/api/chat/clear', methods=['POST'])
def clear_chat_history():
    """Clear chat history"""
    try:
        app_state['chat_history'] = []
        return jsonify({
            'success': True,
            'message': 'Chat history cleared successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error clearing chat history: {str(e)}'
        }), 500

@app.route('/api/thingspeak/test')
def test_thingspeak_api():
    """Test ThingSpeak API connectivity - like Streamlit testing buttons"""
    try:
        results = {}
        
        # Test Read API
        try:
            read_url = f"{THINGSPEAK_BASE_URL}/channels/{THINGSPEAK_CHANNEL_ID}/feeds/last.json?api_key={THINGSPEAK_READ_API_KEY}"
            read_response = requests.get(read_url, timeout=5)
            if read_response.status_code == 200:
                results['read_api'] = {
                    'status': 'success',
                    'message': 'Read API Working!',
                    'data': read_response.json()
                }
            else:
                results['read_api'] = {
                    'status': 'error',
                    'message': f'Read API Error: {read_response.status_code}'
                }
        except Exception as e:
            results['read_api'] = {
                'status': 'error',
                'message': f'Read API Failed: {str(e)}'
            }
        
        # Test Write API
        try:
            write_url = f"{THINGSPEAK_BASE_URL}/update?api_key={THINGSPEAK_WRITE_API_KEY}&field1=0"
            write_response = requests.get(write_url, timeout=5)
            if write_response.status_code == 200 and write_response.text.isdigit():
                results['write_api'] = {
                    'status': 'success',
                    'message': f'Write API Working! Entry: {write_response.text}'
                }
            else:
                results['write_api'] = {
                    'status': 'error',
                    'message': f'Write API Error: {write_response.status_code} - {write_response.text}'
                }
        except Exception as e:
            results['write_api'] = {
                'status': 'error',
                'message': f'Write API Failed: {str(e)}'
            }
        
        # Test Channel Status
        try:
            latest_url = f"{THINGSPEAK_BASE_URL}/channels/{THINGSPEAK_CHANNEL_ID}/feeds/last.json?api_key={THINGSPEAK_READ_API_KEY}"
            channel_response = requests.get(latest_url, timeout=5)
            
            if channel_response.status_code == 200:
                latest_data = channel_response.json()
                
                if latest_data and 'entry_id' in latest_data:
                    results['channel_status'] = {
                        'status': 'success',
                        'message': 'Channel is Active and Receiving Data!',
                        'data': {
                            "Last Entry ID": latest_data.get('entry_id'),
                            "Last Updated": latest_data.get('created_at'),
                            "Pump Status": "ON" if latest_data.get('field1') == '1' else "OFF" if latest_data.get('field1') == '0' else "Unknown",
                            "Temperature": f"{latest_data.get('field2', 'N/A')}°C" if latest_data.get('field2') else "No data",
                            "Humidity": f"{latest_data.get('field3', 'N/A')}%" if latest_data.get('field3') else "No data",
                            "Soil Moisture": f"{latest_data.get('field4', 'N/A')}%" if latest_data.get('field4') else "No data"
                        }
                    }
                else:
                    results['channel_status'] = {
                        'status': 'warning',
                        'message': 'Channel exists but has no data entries yet'
                    }
            else:
                results['channel_status'] = {
                    'status': 'error',
                    'message': f'Channel Status Error: {channel_response.status_code}'
                }
                
        except Exception as e:
            results['channel_status'] = {
                'status': 'error',
                'message': f'Status Check Failed: {str(e)}'
            }
        
        return jsonify({
            'success': True,
            'test_results': results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'API test error: {str(e)}'
        }), 500

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'message': 'API endpoint not found'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'message': 'Internal server error'
    }), 500

if __name__ == '__main__':
    # Create static folder structure
    os.makedirs('static', exist_ok=True)
    
    print("🌱 Smart Irrigation System Backend Starting...")
    print("📁 Place your HTML files in the 'static' folder:")
    print("   - static/index.html (login page)")
    print("   - static/dashboard.html (dashboard page)")
    print("🔗 ThingSpeak Configuration:")
    print(f"   - Channel ID: {THINGSPEAK_CHANNEL_ID}")
    print(f"   - Read API: {THINGSPEAK_READ_API_KEY[:8]}...")
    print(f"   - Write API: {THINGSPEAK_WRITE_API_KEY[:8]}...")
    print("🤖 AI Configuration:")
    print(f"   - Gemini API: {'✅ Configured' if gemini_api_key else '❌ Not configured (using fallback responses)'}")
    print("🚀 Server will run on http://localhost:5000")
    print("📊 Available endpoints:")
    print("   - GET  / (login page)")
    print("   - GET  /dashboard (dashboard page)")
    print("   - POST /api/login (authentication)")
    print("   - GET  /api/thingspeak/data (sensor data)")
    print("   - POST /api/pump/control (pump control)")
    print("   - POST /api/chat (chatbot)")
    print("   - GET  /api/alerts (smart alerts)")
    print("   - GET  /api/status (system status)")
    print("   - GET  /api/thingspeak/test (API testing)")
    
    app.run(debug=True, host='0.0.0.0', port=5000)