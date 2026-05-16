# --- 1. STRICT OFFLINE CONFIGURATION (Must be at the very top) ---
import os
import sys
import logging
import uuid
import socket

# Force a 3-second timeout on ALL network connections to prevent hanging
socket.setdefaulttimeout(3.0)

# Tell Stanza and Argos to stay offline
os.environ['STANZA_RESOURCES_DIR'] = '/app/stanza_resources'
os.environ['ARGOS_DEVICE_TYPE'] = 'cpu'
os.environ['XDG_DATA_HOME'] = '/app/argos_data'
os.environ['XDG_CACHE_HOME'] = '/app/argos_cache'
os.environ['XDG_CONFIG_HOME'] = '/app/argos_config'
os.environ['NLTK_DATA'] = '/app/nltk_data'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HUB_OFFLINE'] = '1'

# Mock out urllib.request to fail fast if anything tries to download
try:
    import urllib.request
    def blocked_urlopen(*args, **kwargs):
        # Fail immediately so we don't wait for firewall timeout
        raise socket.timeout("[Offline] BLOCKED internet request")
    urllib.request.urlopen = blocked_urlopen
except Exception:
    pass

# Aggressively mock Argos and SpaCy internal downloads to prevent hanging
try:
    import spacy.cli
    spacy.cli.download = lambda *args, **kwargs: print("[Offline] Blocked spaCy CLI download.")
except Exception:
    pass

try:
    import argostranslate.networking
    # Overriding this prevents Argos from even LOOKING for a connection
    argostranslate.networking.cache_spacy = lambda: print("[Offline] Argos spaCy cache check bypassed.") or None
except Exception:
    pass

import nltk
nltk.data.path.append('/app/nltk_data')

# Mock out library-specific download functions
try:
    import stanza
    stanza.download = lambda *args, **kwargs: print("[Offline] Blocked Stanza download attempt.")
except ImportError:
    pass

try:
    import spacy
    spacy.download = lambda *args, **kwargs: print("[Offline] Blocked spaCy download attempt.")
except ImportError:
    pass

# --- 2. LOGGING AND SYSTEM SETUP ---
# Suppress TensorFlow and Abseil warnings
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["GLOG_minloglevel"] = "2" # Suppress MediaPipe/C++ Info and Warning logs
os.environ["MAGMA_VOLATILE_CACHE"] = "1"
logging.getLogger('absl').setLevel(logging.ERROR)

def silence_loggers():
    for name in ['argostranslate', 'argostranslate.utils', 'stanza', 'engineio', 'socketio']:
        l = logging.getLogger(name)
        l.setLevel(logging.WARNING)
        l.propagate = False # Prevent bubbling up to the root logger

# Ensure stdout and stderr use UTF-8
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        # Fallback for Python versions < 3.7
        import codecs
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())



from flask import Flask, Response, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from flask_cors import CORS
from db_helper import DBHelper
import bcrypt
from werkzeug.utils import secure_filename
import json
from msg2isl import TranslationHandler, TextProcessor, DatabaseHandler  # If using as module
from compress import compress_sentence
from googletrans import Translator
# from llama_model import process_gesture
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from flask_socketio import SocketIO, emit, join_room, leave_room
import gevent
import re
import inspect
import asyncio

# Load environment variables
load_dotenv()

import argostranslate.package
import argostranslate.translate

# --- Offline Translation Setup ---
def install_offline_models():
    """Installs .argosmodel files found in /app/argos_models if not already installed."""
    model_dir = './argos_models' 
    if not os.path.exists(model_dir):
        print(f"[Argos] Model directory {model_dir} not found. Skipping offline model install.")
        return

    # Check already installed packages to avoid redundant work
    try:
        installed_packages = argostranslate.package.get_installed_packages()
        # Create a set of (from, to) strings for easy checking
        installed_set = {f"{pkg.from_code}->{pkg.to_code}" for pkg in installed_packages}
        print(f"[Argos] Currently installed models: {installed_set}")
    except Exception as e:
        print(f"[Argos] Error checking installed packages: {e}")
        installed_set = set()

    print(f"[Argos] Scanning {model_dir} for models...")
    for filename in os.listdir(model_dir):
        if filename.endswith(".argosmodel"):
            path = os.path.join(model_dir, filename)
            
            # Simple check: if filename contains 'en_hi' and 'en->hi' is installed, skip
            # Format is usually 'translate-en_hi-1_1.argosmodel'
            skip = False
            for pair in installed_set:
                from_c, to_c = pair.split('->')
                if f"{from_c}_{to_c}" in filename:
                    skip = True
                    break
            
            if skip:
                print(f"[Argos] Package {filename} already installed. Skipping.")
                continue

            try:
                argostranslate.package.install_from_path(path)
                print(f"[Argos] Installed package: {filename}")
            except Exception as e:
                print(f"[Argos] Error installing {filename}: {e}")

# Try to install models on startup
try:
    install_offline_models()
except Exception as e:
    print(f"[Argos] Initialization error: {e}")

def argos_translate_text(text, from_code='en', to_code='hi'):
    """Helper to translate text using Argos (offline)."""
    try:
        # Check if text is empty
        if not text or not text.strip():
            return ""

        installed_languages = argostranslate.translate.get_installed_languages()
        s_lang = next((l for l in installed_languages if l.code == from_code), None)
        t_lang = next((l for l in installed_languages if l.code == to_code), None)
        
        if s_lang and t_lang:
            # We use s_lang.get_translation(t_lang).translate(text) 
            # This is key: s_lang.get_translation(t_lang) returns a ITranslation object.
            # Calling .translate(text) on it performs raw translation without 
            # the 'Sentence Splitter' (Stanza/spaCy) that requires internet.
            translation = s_lang.get_translation(t_lang)
            translated = translation.translate(text)
            
            print(f"[Argos] Translated ({from_code}->{to_code}): '{text[:30]}...' -> '{translated[:30]}...'")
            return translated
        else:
            print(f"[Argos] Error: {from_code}->{to_code} model not installed or not found.")
            return None
    except Exception as e:
        print(f"[Argos] Translation error: {e}")
        return None


def detect_input_language(text):
    """Classify input as english, hindi (Devanagari), or hinglish."""
    if not text or not text.strip():
        return "english"

    if any('\u0900' <= char <= '\u097f' for char in text):
        return "hindi"

    tokens = re.findall(r"[A-Za-z']+", text.lower())
    if not tokens:
        return "english"

    hinglish_markers = {
        "kya", "ka", "ki", "ke", "hai", "haan", "nahi", "nahin", "mera", "meri",
        "mere", "tera", "teri", "tere", "apna", "apni", "apne", "tum", "aap",
        "main", "mai", "hoon", "hun", "tha", "thi", "the", "raha", "rahi", "rahe",
        "chal", "chalo", "acha", "achha", "bhai", "yaar", "kaise", "kahan", "kyun",
        "mat", "kar", "karo", "kr", "krna", "krte", "krti", "ho", "hoga", "hogi",
        "sab", "bahut", "bohot", "thik", "theek", "wala", "wali", "waise", "aisa",
        "aise", "vaise", "naam", "dost", "ghar", "hall", "haal"
    }

    marker_hits = sum(1 for token in tokens if token in hinglish_markers)
    if marker_hits > 0:
        return "hinglish"

    return "english"


def normalize_hinglish_text(text):
    """Normalize common Roman Hindi spellings before translation."""
    replacements = {
        " hall ": " haal ",
        " h m ": " hum ",
        " m ": " main ",
        " meraa ": " mera ",
        " naamm ": " naam ",
        " kese ": " kaise ",
        " kese ho ": " kaise ho ",
        " kese hai ": " kaise hai ",
        " kese hain ": " kaise hain ",
        " kya hall ": " kya haal ",
    }

    normalized = f" {text.strip().lower()} "
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    return normalized.strip()


def run_coroutine_safely(coro):
    """Execute a coroutine without depending on a reused/closed global event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def translate_input_to_english(text, detected_language):
    """Translate hindi/hinglish to English. English input is returned unchanged."""
    if detected_language == "english":
        return text

    if detected_language == "hindi":
        translated = argos_translate_text(text, from_code='hi', to_code='en')
        return translated or text

    if detected_language == "hinglish":
        try:
            normalized_text = normalize_hinglish_text(text)
            translator = Translator()
            result = translator.translate(normalized_text, src='auto', dest='en')
            if inspect.iscoroutine(result):
                result = run_coroutine_safely(result)

            translated = result.text
            if translated and translated.strip():
                print(f"[Hinglish] Normalized '{text}' -> '{normalized_text}'")
                print(f"[Hinglish] Translated '{normalized_text}' -> '{translated}'")
                return translated
        except Exception as e:
            print(f"[Hinglish] Translation failed: {e}")

    return text


def translate_input_to_hindi(text, detected_language):
    """Translate English/Hinglish to Hindi for speech playback."""
    if detected_language == "hindi":
        return text

    if detected_language == "english":
        translated = argos_translate_text(text, from_code='en', to_code='hi')
        return translated or text

    if detected_language == "hinglish":
        try:
            normalized_text = normalize_hinglish_text(text)
            translator = Translator()
            result = translator.translate(normalized_text, src='auto', dest='hi')
            if inspect.iscoroutine(result):
                result = run_coroutine_safely(result)

            translated = result.text
            if translated and translated.strip():
                print(f"[Hinglish] Normalized '{text}' -> '{normalized_text}'")
                print(f"[Hinglish] Hindi speech translation '{normalized_text}' -> '{translated}'")
                return translated
        except Exception as e:
            print(f"[Hinglish] Hindi translation failed: {e}")

    return text

# Configure Logging
if not os.path.exists('logs'):
    os.makedirs('logs')

file_handler = RotatingFileHandler('logs/app.log', maxBytes=10240, backupCount=10, encoding='utf-8')
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)

# Get the root logger and add the handler
logger = logging.getLogger()
logger.addHandler(file_handler)
logger.setLevel(logging.INFO) 

# Silence verbose third-party loggers AFTER root configuration
silence_loggers()

app = Flask(__name__, static_folder='client/dist', template_folder='client/dist')
app.logger.addHandler(file_handler) # Add to Flask app logger too
CORS(app, supports_credentials=True)
app.secret_key = os.environ.get('SECRET_KEY', 'rahul')  # Use env var with fallback
# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

db_helper = DBHelper()
otp_store = {}
final_sentence = []


# API Routes should be prefixed with /api or handled before the catch-all
# Existing routes like /login, /process_uploaded_video etc. will take precedence
# because they are defined specifically.

# @app.route('/')
# def index():
#     return redirect(url_for('login'))

@app.route('/api/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        action = data.get('action')

        if action == 'login':
            mobile = data.get('mobile')
            password = data.get('password')

            user = db_helper.get_user_by_mobile(mobile)
            print(f"Login attempt for {mobile}. User found: {user is not None}")
            if user:
                print(f"Stored hash: {user['password_hash']}")
                check = bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8'))
                print(f"Password check result: {check}")

            if user and bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
                session['user_info'] = {
                    "mobile": user['mobile'],
                    "username": user['username'],
                    "email": user.get('email'),
                    "gender": user.get('gender'),
                    "profile_picture": '/static' + user.get('profile_picture').split('static')[-1].replace('\\', '/') if user.get('profile_picture') else None
                }
                session['mobile'] = user['mobile']  # Save separately for easy access
                return jsonify({"success": True, "user": session['user_info']})

            else:
                print("Login failed: Invalid credentials")
                return jsonify({"success": False, "message": "Invalid mobile or password."}), 401

        elif action == 'register':
            # Registration logic moved to /register endpoint or handled here if preferred
            pass

    return jsonify({"message": "Login endpoint"})



UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
# UPLOAD_FOLDER = '/static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

import random
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_email_helper(email, otp, subject, body):
    smtp_email = os.environ.get("SMTP_EMAIL", "yugeshtemp@gmail.com") 
    smtp_password = os.environ.get("SMTP_PASSWORD", "") 
    
    try:
        msg = MIMEMultipart()
        msg['From'] = smtp_email
        msg['To'] = email
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'plain'))

        print(f"[Email] Attempting to send OTP to {email} from {smtp_email}...")
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        
        if smtp_password:
             server.login(smtp_email, smtp_password)
             server.send_message(msg)
             server.quit()
             print(f"[Email] Successfully sent OTP to {email}")
        else:
             print(f"[Email Warning] SMTP_PASSWORD missing in .env! Printing to console instead.")
             print(f"========== OTP FOR {email} IS {otp} ==========")
        return True
    except Exception as e:
        print(f"[Email Error] Failed to send email: {e}")
        return False

@app.route('/api/register/send_otp', methods=['POST'])
def register_send_otp():
    data = request.get_json()
    email = data.get('email')
    mobile = data.get('mobile')
    if not email or not mobile:
         return jsonify({"success": False, "message": "Email and mobile are required."}), 400
    
    # Check if user already exists
    if db_helper.user_exists(mobile):
         return jsonify({"success": False, "message": "Mobile number is already registered."}), 400
    if db_helper.get_user_by_email(email):
         return jsonify({"success": False, "message": "Email is already registered."}), 400
         
    otp = str(random.randint(100000, 999999))
    otp_store[email] = {
        'otp': otp,
        'expiry': time.time() + 300 # 5 minutes expiry
    }
    
    success = send_email_helper(
        email, 
        otp, 
        "ISL App - Registration OTP", 
        f"Your OTP for registration is: {otp}\n\nThis OTP is valid for 5 minutes."
    )
    
    if success:
        return jsonify({"success": True, "message": "Registration OTP sent successfully."})
    else:
        return jsonify({"success": False, "message": "Failed to send OTP email. Please check server logs."}), 500

@app.route('/api/register/verify_otp', methods=['POST'])
def register_verify_otp():
    data = request.get_json()
    email = data.get('email')
    otp = data.get('otp')
    if not email or not otp:
        return jsonify({"success": False, "message": "Email and OTP are required."}), 400
    
    record = otp_store.get(email)
    if not record or record['otp'] != str(otp):
         return jsonify({"success": False, "message": "Invalid OTP."}), 400
    if time.time() > record['expiry']:
         return jsonify({"success": False, "message": "OTP has expired."}), 400
         
    return jsonify({"success": True, "message": "Email verified successfully."})

@app.route('/api/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Check if request is JSON (from React) or Form (legacy/multipart)
        if request.is_json:
            data = request.get_json()
            mobile = data.get('mobile')
            username = data.get('username')
            email = data.get('email')
            gender = data.get('gender')
            password = data.get('password')
            otp = data.get('otp')
            profile_pic_path = None # Handle file upload separately or base64
        else:
            mobile = request.form['mobile']
            username = request.form['username']
            email = request.form.get('email')
            gender = request.form.get('gender')
            password = request.form['password']
            otp = request.form.get('otp')
            
            profile_pic_path = None
            file = request.files.get('profile_picture')
            if file and allowed_file(file.filename):
                filename = secure_filename(f"{mobile}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                profile_pic_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                profile_pic_path = '/static' +profile_pic_path.split('static')[-1].replace('\\', '/') if profile_pic_path else None

        # Verify OTP
        if not otp:
             return jsonify({"success": False, "message": "OTP is required."}), 400
             
        record = otp_store.get(email)
        if not record or record['otp'] != str(otp) or time.time() > record['expiry']:
             return jsonify({"success": False, "message": "Invalid or expired OTP."}), 400

        hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        success = db_helper.register_user(
            mobile, username, email, gender, hashed_pw, profile_pic_path
        )
        if success:
            del otp_store[email] # Clear OTP after success
            return jsonify({"success": True, "message": "Registration successful"})
        else:
            return jsonify({"success": False, "message": "Registration failed. User may already exist."}), 400

    return jsonify({"message": "Register endpoint"})

import random
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

@app.route('/api/forgot_password/send_otp', methods=['POST'])
def send_otp():
    data = request.get_json()
    email = data.get('email')
    if not email:
         return jsonify({"success": False, "message": "Email is required."}), 400
    
    user = db_helper.get_user_by_email(email)
    if not user:
         return jsonify({"success": False, "message": "User not found with this email."}), 404
         
    otp = str(random.randint(100000, 999999))
    otp_store[email] = {
        'otp': otp,
        'expiry': time.time() + 300 # 5 minutes expiry
    }
    
    success = send_email_helper(
        email, 
        otp, 
        "ISL App - Password Reset OTP", 
        f"Your OTP for password reset is: {otp}\n\nThis OTP is valid for 5 minutes."
    )
    
    if success:
        return jsonify({"success": True, "message": "OTP sent successfully."})
    else:
        return jsonify({"success": False, "message": "Failed to send OTP email. Please check server logs."}), 500

@app.route('/api/forgot_password/verify_otp', methods=['POST'])
def verify_otp():
    data = request.get_json()
    email = data.get('email')
    otp = data.get('otp')
    
    record = otp_store.get(email)
    if not record or record['otp'] != str(otp):
         return jsonify({"success": False, "message": "Invalid OTP."}), 400
    if time.time() > record['expiry']:
         return jsonify({"success": False, "message": "OTP has expired."}), 400
         
    # Fetch the user to return the username and mobile
    user = db_helper.get_user_by_email(email)
    username = user['username'] if user else "User"
    mobile = user['mobile'] if user else "Unknown"
         
    return jsonify({"success": True, "message": "OTP verified successfully.", "username": username, "mobile": mobile})

@app.route('/api/forgot_password/reset', methods=['POST'])
def reset_password():
    data = request.get_json()
    email = data.get('email')
    otp = data.get('otp')
    new_password = data.get('new_password')
    
    record = otp_store.get(email)
    if not record or record['otp'] != str(otp) or time.time() > record['expiry']:
         return jsonify({"success": False, "message": "Invalid or expired OTP."}), 400
         
    hashed_pw = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    success = db_helper.update_password_by_email(email, hashed_pw)
    
    if success:
         del otp_store[email] # Clear OTP after successful reset
         return jsonify({"success": True, "message": "Password reset successfully."})
    else:
         return jsonify({"success": False, "message": "Failed to reset password."}), 500

@app.route('/api/teacher_dashboard')
def teacher_dashboard():
    if 'user_info' not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 401

    current_mobile = session.get('mobile')

    saved_contacts = db_helper.GetSavedContacts(current_mobile)
    print(saved_contacts, "Saved Contacts")

    return jsonify({
        "success": True,
        "user_info": session['user_info'],
        "students": saved_contacts
    })


@app.route('/api/search_contact')
def search_contact():
    search_mobile = request.args.get('mobile')
    owner_mobile = session.get('mobile')

    if not search_mobile or not owner_mobile:
        return jsonify({"status": "error"})

    result = db_helper.SearchContact(owner_mobile, search_mobile)
    return jsonify(result)


# ...

@app.route('/api/translate_message', methods=['GET'])
def translate_message():
    print("Translate message called")
    message_id = request.args.get('message_id')
    if not message_id:
        return jsonify({'error': 'Message ID is required'}), 400

    message = db_helper.GetMessageById(message_id)
    if not message:
        return jsonify({'error': 'Message not found'}), 404

    text_to_translate = message['message_content']
    
    try:
        # Use Argos Translator instead of Google
        # target='hi' for Hindi, assuming source is English ('en')
        translation = argos_translate_text(text_to_translate, from_code='en', to_code='hi')
        
        if translation:
            return jsonify({'translated_text': translation})
        else:
            # Fallback to original text or error
            return jsonify({'error': 'Offline translation model (EN->HI) not found'}), 500
            
    except Exception as e:
        print(f"Translation error: {e}")
        return jsonify({'error': 'Translation failed', 'details': str(e)}), 500


@app.route('/api/translate_text', methods=['POST'])
def translate_text():
    data = request.get_json() or {}
    text = (data.get('text') or '').strip()
    target = (data.get('target') or 'hi').strip().lower()

    if not text:
        return jsonify({'error': 'Text is required'}), 400

    detected_language = detect_input_language(text)

    try:
        if target == 'hi':
            translated_text = translate_input_to_hindi(text, detected_language)
        elif target == 'en':
            translated_text = translate_input_to_english(text, detected_language)
        else:
            return jsonify({'error': 'Unsupported target language'}), 400

        return jsonify({
            'translated_text': translated_text,
            'detected_language': detected_language,
            'target_language': target
        })
    except Exception as e:
        print(f"Text translation error: {e}")
        return jsonify({'error': 'Translation failed', 'details': str(e)}), 500

@app.route('/api/send-message', methods=['POST'])
def send_message():
    data = request.get_json()
    sender_mobile = str(session.get("mobile") or "").strip()
    receiver_mobile = str(data.get("receiver_mobile") or "").strip()
    message_content = data.get("message")
    gesture_list = data.get("gesture_data")
    
    # Validate fields first
    if not sender_mobile or not receiver_mobile or not message_content:
        return jsonify({"success": False, "error": "Missing fields"}), 400

    if db_helper.is_blocked_between(sender_mobile, receiver_mobile):
        return jsonify({
            "success": False,
            "error": "You cannot send messages in this conversation because one user has blocked the other."
        }), 403

    gesture_metadata_str = None

    if gesture_list:
        try:
             # Format gesture list safely
            gesture_list = [
                [
                    (item["word"], int(item["confidence"] * 100)) 
                    for item in sublist
                ]
                for sublist in gesture_list
            ]
            
            gesture_metadata_str = json.dumps(gesture_list)
            
            # Llama processing disabled for now
            # print("Processing gesture data with Llama...")
            # llama_sentence = process_gesture(gesture_list)
            # if llama_sentence:
            #     print(f"Llama suggested: {llama_sentence}")
            #     message_content = llama_sentence
            # else:
            #     print("Llama returned None or empty string. Using original text.")
            print("Llama processing disabled. Using original text.")
        except Exception as e:
            print(f"Error processing gesture data: {e}")
            # Fallback: maintain original message content if processing fails
    
    message_id = db_helper.SaveChatMessage(sender_mobile, receiver_mobile, message_content, gesture_metadata_str)
    
    if message_id:
        # Emit real-time event to receiver
        try:
            from datetime import datetime
            new_msg = {
                "message_id": message_id,
                "sender_mobile": sender_mobile,
                "receiver_mobile": receiver_mobile,
                "message_content": message_content,
                "message_metadata": gesture_metadata_str,
                "seen": 0,
                "created_at": datetime.now().strftime('%Y-%m-%d %H:%M')
            }
            socketio.emit('receive_message', new_msg, room=receiver_mobile)
            socketio.emit('receive_message', new_msg, room=sender_mobile)
        except Exception as e:
            print(f"Socket emit error: {e}")
        
    return jsonify({"success": bool(message_id), "message": new_msg if message_id else None})


@app.route('/api/save_contact', methods=['POST'])
def save_contact():
    data = request.get_json()
    contact_mobile = data.get('contact_mobile')
    nickname = data.get('nickname')
    owner_mobile = session.get('mobile')

    if not contact_mobile or not nickname or not owner_mobile:
        return jsonify({"success": False})

    success = db_helper.SaveContact(owner_mobile, contact_mobile, nickname)
    return jsonify({"success": success})

@app.route('/api/get_saved_contacts')
def get_saved_contacts():
    owner_mobile = session.get('mobile')
    if not owner_mobile:
        return jsonify({"contacts": []})

    contacts = db_helper.GetSavedContacts1(owner_mobile)
    return jsonify({"contacts": contacts})


@app.route('/api/logout')
def logout():
    session.clear()  # Clears all session data
    return redirect(url_for('login'))  # Redirect to login or home

@app.route('/api/get_messages')
def get_messages():
    contact = request.args.get('contact')
    user_mobile = session.get('mobile')

    if not contact or not user_mobile:
        return jsonify({'messages': []})

    messages = db_helper.GetChatMessages(user_mobile, contact)
    return jsonify({'messages': messages})


@app.route('/api/get_contact_image')
def get_contact_image():
    mobile = request.args.get('mobile')

    if not mobile:
        return jsonify({'profile_picture': '/static/uploads/blank.png'})

    image_path = db_helper.get_profile_picture(mobile)

    if image_path:
        # Extract the relative static path
        if 'static' in image_path:
            relative_path = '/static' + image_path.split('static')[-1].replace('\\', '/')
        else:
            # fallback if something goes wrong
            relative_path = '/static/uploads/blank.png'
    else:
        relative_path = '/static/uploads/blank.png'

    return jsonify({'profile_picture': relative_path})


@app.route('/api/mark_seen', methods=['POST'])
def mark_seen():
    data = request.get_json()
    user_mobile = str(session.get('mobile') or session.get('user_info', {}).get('mobile') or '').strip()
    contact_mobile = str(data.get('contact_mobile') or '').strip()

    if not user_mobile or not contact_mobile:
        return {"success": False}, 400

    db_helper.mark_messages_as_seen(contact_mobile, user_mobile)
    return {"success": True}

@app.route('/api/delete_message', methods=['POST'])
def delete_message():
    data = request.get_json()
    message_id = data.get('message_id')
    print(message_id," messageID")
    success = db_helper.DeleteMessage(message_id)

    return jsonify({"success": success})


@app.route('/api/edit_contact_name', methods=['POST'])
def edit_contact_name():
    data = request.get_json()
    mobile = data.get('mobile')
    new_name = data.get('new_name')
    user_mobile = session.get('mobile')

    if not mobile or not new_name:
        return jsonify(success=False)

    result = db_helper.update_contact_name(user_mobile, mobile, new_name)
    return jsonify(success=result)

@app.route('/api/delete_contact', methods=['POST'])
def delete_contact():
    data = request.get_json()
    mobile = data.get('mobile')
    user_mobile = session.get('mobile')

    if not mobile:
        return jsonify(success=False)

    result = db_helper.delete_contact(user_mobile, mobile)
    return jsonify(success=result)

@app.route('/api/block_contact', methods=['POST'])
def block_contact():
    data = request.get_json()
    mobile = data.get('mobile')
    user_mobile = session.get('mobile')

    if not mobile or not user_mobile:
        return jsonify(success=False), 400

    result = db_helper.block_contact(user_mobile, mobile)
    return jsonify(success=result)

@app.route('/api/unblock_contact', methods=['POST'])
def unblock_contact():
    data = request.get_json()
    mobile = data.get('mobile')
    user_mobile = session.get('mobile')

    if not mobile or not user_mobile:
        return jsonify(success=False), 400

    result = db_helper.unblock_contact(user_mobile, mobile)
    return jsonify(success=result)

@app.route('/api/delete_contact_messages', methods=['POST'])
def delete_contact_messages():
    data = request.get_json()
    mobile = data.get('mobile')
    user_mobile = session.get('mobile')

    if not mobile:
        return jsonify(success=False)

    result = db_helper.delete_contact_messages(user_mobile, mobile)
    return jsonify(success=result)

# Load models globally at startup
# (Removed unused global model loading)

import warnings
warnings.filterwarnings('ignore', category=UserWarning, module='google.protobuf.symbol_database')




#apply both models on video 19/1/2026

from implementation import ISLProcessor

# Initialize ISLProcessor globally to avoid reloading models on every request
try:
    print("Initializing Global ISLProcessor...")
    processor = ISLProcessor()
    print("Global ISLProcessor initialized successfully.")
except Exception as e:
    print(f"Failed to initialize Global ISLProcessor: {e}")
    processor = None

@app.route('/api/process_uploaded_video', methods=['POST'])
def process_uploaded_video():
    import time
    request_start = time.perf_counter()
    print("[Timing][Upload] /api/process_uploaded_video request started")

    if 'video' not in request.files:
        return jsonify({'error': 'No video file uploaded'}), 400

    print("video is found")
    file = request.files['video']

    unique_filename = f"temp_video_{uuid.uuid4().hex}.webm"
    temp_path = os.path.join('static', 'temp_videos', unique_filename)
    os.makedirs(os.path.dirname(temp_path), exist_ok=True)
    
    save_start = time.perf_counter()
    file.save(temp_path)
    save_elapsed = time.perf_counter() - save_start
    file_size = os.path.getsize(temp_path)
    print("file saved to:", temp_path)
    print(f"[Timing][Upload] save_file={save_elapsed:.3f}s size={file_size / 1024:.1f}KB")
    results_mlp_sequence = []
    results_res_sequence = []
    try:
        print("Initializing ISLProcessor...")
        global processor
        if processor is None:
            print("Global processor was None, attempting to initialize it now...")
            init_start = time.perf_counter()
            processor = ISLProcessor()
            print(f"[Timing][Upload] late_processor_init={time.perf_counter() - init_start:.3f}s")
            print("Late initialization successful.")
            
        print(f"Processing video: {temp_path}")
        start_time = time.perf_counter()
        pred_sentence = processor.process_video(temp_path)
        processing_elapsed = time.perf_counter() - start_time
        
        print("\n" + "="*30)
        print("VERIFICATION RESULT")
        print("="*30)
        print(f"Output Sentence: {pred_sentence}")
        print(f"Time Taken: {processing_elapsed:.2f}s")
        print("="*30)

        sentence = pred_sentence.title()
        print("Detected Sentence:", sentence)
        
        frame_count_start = time.perf_counter()
        frame_count = getattr(processor, "last_frame_count", 0)
        print(f"[Timing][Upload] count_frames={time.perf_counter() - frame_count_start:.3f}s")
        print(f"Number of frames captured: {frame_count}")
        print(f"[Timing][Upload] total_request={time.perf_counter() - request_start:.3f}s")

        return jsonify({'sentence': sentence, 'frames': frame_count})

    except Exception as e:
        print(f"Video processing error: {e}")
        print(f"[Timing][Upload] failed_after={time.perf_counter() - request_start:.3f}s")
        return jsonify({'error': 'Processing failed', 'details': str(e)}), 500
    
    finally:
        # Permanent save: do not remove the video file
        print(f"Video permanently saved at: {temp_path}")
        

# @app.route('/api/process_uploaded_video', methods=['POST'])
# def process_uploaded_video():
#     if 'video' not in request.files:
#         return jsonify({'error': 'No video file uploaded'}), 400

#     print("video is found")
#     file = request.files['video']

#     # Generate unique filename to prevent race conditions
#     unique_filename = f"temp_video_{uuid.uuid4().hex}.webm"
#     temp_path = os.path.join('static', 'temp_videos', unique_filename)
#     os.makedirs(os.path.dirname(temp_path), exist_ok=True)
#     file.save(temp_path)
#     print("file saved to:", temp_path)

#     try:
#         # cap = cv2.VideoCapture(0) # Removed redundant line
        
#         # Use global models if available
#         if global_model and global_label_encoder:
#             recognizer = HandGestureRecognition(
#                 model=global_model,
#                 label_encoder=global_label_encoder,
#                 suppress_camera=True,
#                 video_source=temp_path
#             )
#         else:
#             # Fallback to local loading (slow)
#             print("Warning: Using local model loading (slow)")
#             recognizer = HandGestureRecognition(
#                 model_path='MLP_CNN_Keras_model.h5',
#                 label_encoder_path='label_encoder.pkl',
#                 labels_path='labels_dict.txt',
#                 suppress_camera=True,
#                 video_source=temp_path
#             )

#         pred_sentence,sentence_list=recognizer.start()

#         # pred_sentence = []
#         # count = 0
#         # prev_char = None
#         # # frame_index = 0

#         # while True:
#         #     ret, frame = cap.read()
#         #     if not ret:
#         #         break

#         #     _, predicted_char, top_3_data = recognizer.process_frame(frame)
#         #     print("Predicted:", predicted_char)
#         #     if predicted_char:
#         #         if predicted_char == prev_char:
#         #             count += 1
#         #         else:
#         #             count = 1
#         #         if count >= 8 and (not pred_sentence or predicted_char != pred_sentence[-1].get('word')) and predicted_char != 'unknown':
#         #              # Append the whole object with candidates
#         #             word_object = {
#         #                 "word": predicted_char,
#         #                 "candidates": top_3_data,
#         #                 # "position": frame_index # Optional: track frame or sequence index
#         #             }
#         #             pred_sentence.append(word_object)
                    
#         #         prev_char = predicted_char
            
#         #     # frame_index += 1

#         # cap.release()
#         # os.remove(temp_path)

#         # Convert the list of objects to JSON string for the TEXT column
#         # sentence_json = json.dumps(pred_sentence)
#         # print("Detected Sentence Data:", sentence_json)
        
#         # Save structured data (JSON) instead of just plain text
#         # Note: Database column Must be TEXT/LONGTEXT
#         # We return the simple text representation for immediate display if needed, 
#         # or the full JSON if the frontend is ready.
#         # For now, let's return the simplified text for the 'sentence' key to keep frontend working 
#         # and maybe add a 'raw_data' key.
        
#         # simple_sentence = ' '.join([item['word'] for item in pred_sentence])
        
#         # We need to save the JSON to the DB ideally. 
#         # But this function only returns JSON to frontend. 
#         # Saving happens later or in a different flow usually? 
#         # Wait, the user asked to SAVE it to the DB in message_content.
#         # But this function `process_uploaded_video` just processes and returns to frontend.
#         # The frontend likely calls `/api/send-message` later with the result.
        
#         return jsonify({'sentence': pred_sentence, 'raw_data': sentence_list})

#     except Exception as e:
#         print(f"Video processing error: {e}")
#         return jsonify({'error': 'Processing failed', 'details': str(e)}), 500
    
#     finally:
#         # Clean up the temporary file
#         if os.path.exists(temp_path):
#             try:
#                 os.remove(temp_path)
#                 print(f"Removed temp file: {temp_path}")
#             except Exception as e:
#                 print(f"Error removing temp file {temp_path}: {e}")


@app.route('/api/upload_video', methods=['POST'])
def upload_video():
    video = request.files.get('video')
    if video:
        save_path = os.path.join('static', 'uploads', video.filename)
        video.save(save_path)
        return jsonify({"status": "saved", "path": save_path})
    return jsonify({"status": "no file"})



# @app.route('/video_feed')
# def video_feed():
#     def generate():
#         global output_frame, lock
#         while camera_active:
#             with lock:
#                 if output_frame is None:
#                     continue
#                 yield (b'--frame\r\n'
#                        b'Content-Type: image/jpeg\r\n\r\n' + output_frame + b'\r\n')

#     return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/get_final_sentence')
def get_final_sentence():
    return jsonify({"text": " ".join(final_sentence)})

@app.route('/api/update_final_sentence', methods=['POST'])
def update_final_sentence():
    global final_sentence
    data = request.get_json()
    text = data.get("text", "")
    final_sentence = text.strip().split()
    return jsonify(success=True)



# Add new route for profile editing
@app.route('/api/profile', methods=['GET', 'POST'])
def profile():
    if 'user_info' not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 401

    user_info = session['user_info']
    
    if request.method == 'GET':
        return jsonify({"success": True, "user_info": user_info})

    if request.method == 'POST':
        # Handle JSON or Form data
        if request.is_json:
             data = request.get_json()
             username = data.get('username')
             email = data.get('email')
             gender = data.get('gender')
             # Profile pic update via JSON might need base64 or separate endpoint
             profile_pic_path = user_info.get('profile_picture') 
        else:
            username = request.form['username']
            email = request.form.get('email')
            gender = request.form.get('gender')

            file = request.files.get('profile_picture')
            profile_pic_path = user_info.get('profile_picture')
            print(profile_pic_path," path")
            # Handle new profile picture upload
            if file and file.filename != "" and allowed_file(file.filename):
                filename = secure_filename(f"{user_info['mobile']}_{file.filename}")
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                profile_pic_path = file_path
                profile_pic_path = '/static' +file_path.split('static')[-1].replace('\\', '/') if file_path else None

                # Delete old profile picture if exists
                old_pic = user_info.get('profile_picture')
                if old_pic and os.path.exists(old_pic):
                    # Check if it is a local file path
                    if 'static' in old_pic:
                         # logic to remove old file if needed
                         pass

        # Update user in database
        if db_helper.update_user_profile(
            user_info['mobile'],
            username,
            email,
            gender,
            profile_pic_path
        ):
            # Update session data
            session['user_info'] = {
                "mobile": user_info['mobile'],
                "username": username,
                "email": email,
                "gender": gender,
                "profile_picture": profile_pic_path,
            }
            return jsonify({"success": True, "message": "Profile updated", "user_info": session['user_info']})
        else:
            return jsonify({"success": False, "message": "Error updating profile"}), 500

from flask import send_from_directory, request

@app.route('/isl_videos/<path:filename>')
def serve_isl_videos(filename):
    # Change this to your actual folder path
    # Change this to your actual folder path
    video_dir = os.path.join(app.root_path, 'static', 'isl_videos')
    filename = filename.replace('\\', '/')
    
    # Try serving exact match first
    full_path = os.path.join(video_dir, filename)
    if os.path.exists(full_path):
        return send_from_directory(video_dir, filename)
        
    # Case-insensitive fallback for Linux
    directory = os.path.dirname(full_path)
    base_name = os.path.basename(full_path)
    
    if os.path.exists(directory):
        for f in os.listdir(directory):
            if f.lower() == base_name.lower():
                # Found a case-insensitive match
                actual_filename = os.path.join(os.path.dirname(filename), f).replace('\\', '/')
                return send_from_directory(video_dir, actual_filename)
                
    # If still not found, try returning as is (will 404)
    return send_from_directory(video_dir, filename)

@app.route('/api/convert_to_isl', methods=['POST'])
def convert_to_isl():

    data = request.get_json()
    message = data.get("text", "").strip()
    print("convert isl fuction called with ",message)
    if not message:
        return jsonify({"error": "No text provided"}), 400

    # # Create a directory for temporary video files if it doesn't exist
    # temp_video_dir = os.path.join(app.static_folder, 'temp_videos')
    # os.makedirs(temp_video_dir, exist_ok=True)

    # # Generate a unique filename for the combined video
    # timestamp = int(time.time())
    # output_filename = f"isl_{timestamp}.mp4"
    # output_path = os.path.join(temp_video_dir, output_filename)

    try:
        detected_language = detect_input_language(message)
        print(f"[Language Detection] Input classified as: {detected_language}")
        translated_message = translate_input_to_english(message, detected_language)
        if translated_message:
            message = translated_message

        # 2. Process the text through your ISL conversion pipeline
        compressed = compress_sentence(message.lower())
        
        # Use global handler if available
        handler = TranslationHandler()
            
        sentences = TextProcessor.split_sentence(compressed)
        print("compression and all done : ",sentences)
        video_paths = []

        # 3. For each word, find the corresponding ISL video
        for sentence in sentences:
            # Updated to use return value instead of global state
            isl_sentence = handler.process_sentence(sentence)
            indexed_list = handler.create_indexed_list_with_duplicates(isl_sentence)
            print("index list: ",indexed_list)
            conn = DatabaseHandler.connect_to_db()

            for index, word in indexed_list:
                # Look up word in database
                result = DatabaseHandler.lookup_word_with_duration(conn, word)
                print("result: ",result)
                if result:
                    video_paths.append(result[0])  # Append the video path
                else:
                    # Try synonyms if direct word not found
                    synonyms = handler.get_synonyms([word], pos_filter='v')
                    synonym_found = False

                    for synonym in synonyms[word]:
                        syn_result = DatabaseHandler.lookup_synonym_with_duration(conn, synonym)
                        if syn_result:
                            video_paths.append(syn_result[0])
                            synonym_found = True
                            break

                    if not synonym_found:
                        # Fall back to spelling the word
                        alphabet_videos = DatabaseHandler.lookup_alphabet_videos_from_db(conn, word)
                        if alphabet_videos:
                            video_paths.extend([v[0] for v in alphabet_videos])
                    print("video paths so far: ",video_paths)

            conn.close()
        # 4. Return the video paths
        base_url = request.host_url.rstrip('/')  # e.g. http://localhost:5000
        video_urls = [f"/isl_videos/{path.replace(os.sep, '/')}" for path in video_paths]

        print("Video URLs to send:", video_urls)

        return jsonify({
            "videos": video_urls,
            "original_text": data.get("text", "").strip(),
            "translated_text": message,
            "detected_language": detected_language
        })

    except Exception as e:
        app.logger.error(f"Error converting to ISL: {str(e)}")
        return jsonify({
            "error": "Failed to convert message to ISL",
            "details": str(e)
        }), 500


# Endpoint to handle feedback submission
@app.route('/api/feedback_message', methods=['POST'])
def feedback_message():
    try:
        # Get the JSON data from the request
        data = request.get_json()

        # Extract message ID and feedback from the incoming data
        message_id = data.get('message_id')
        feedback = data.get('feedback')

        if not message_id or not feedback:
            return jsonify({'success': False, 'message': 'Missing required fields: message_id or feedback'})


        # Save feedback to the database
        print(f"{message_id}  meassage id  and  {feedback} feedback")
        result = db_helper.StoreFeedback(message_id, feedback)

        return jsonify({'success': result['success'], 'message': result['message']})

    except Exception as e:
        # Handle any exceptions and return an error response
        return jsonify({'success': False, 'message': str(e)})


# def cleanup_temp_videos():
#     temp_video_dir = os.path.join(app.static_folder, 'temp_videos')
#     if os.path


# Serve uploaded files from the backend static/uploads folder
@app.route('/static/uploads/<path:filename>')
def serve_uploads(filename):
    return send_from_directory(os.path.join(app.root_path, 'static', 'uploads'), filename)

# Serve React App
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    if path != "" and os.path.exists(app.static_folder + '/' + path):
        return send_from_directory(app.static_folder, path)
    
    # Check if it's a static file request (e.g., favicon, manifest)
    if path != "" and os.path.exists(os.path.join(app.template_folder, path)):
         return send_from_directory(app.template_folder, path)

    return render_template('index.html')


# SocketIO Events
@socketio.on('connect')
def handle_connect():
    print('Client connected:', request.sid)

@socketio.on('join')
def on_join(data):
    mobile = str(data['mobile']).strip()
    room = mobile
    join_room(room)
    print(f'User {mobile} joined room {room}')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected:', request.sid)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5001, debug=False)

    # app.run(debug=True) # Removed duplicate call
