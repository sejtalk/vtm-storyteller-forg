# VTM Storyteller v3.0 - Enhanced Edition
# Advanced features: Roll History, PDF Export, Roll20 API, Portraits, Chronicles, XP, Disciplines

from flask import Flask, render_template_string, request, jsonify, send_file, session
from datetime import timedelta
from openai import OpenAI
import os
import sqlite3
import json
from datetime import datetime
import secrets
import io
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
import requests
from werkzeug.utils import secure_filename
import base64

# Campaign and Session Management
from campaign_session_api import *
from command_system import CommandSystem
from intelligent_dice_system import IntelligentDiceSystem
from pdf_upload_handler import PDFUploadHandler
from migrate_database import migrate_database

# Run database migration on startup
migrate_database()

# Initialize intelligent dice system
intelligent_dice = IntelligentDiceSystem()

# Initialize command system with intelligent dice
command_system = CommandSystem(intelligent_dice=intelligent_dice)

# Initialize PDF upload handler
pdf_handler = PDFUploadHandler()


# ElevenLabs TTS Integration
import io


# ElevenLabs configuration
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY', '')
ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech"

# Voice IDs for different languages
VOICES = {
    'en': {
        'voice_id': 'EXAVITQu4vr4xnSDxMaL',  # Serafina - Sensual female voice
        'name': 'Serafina',
        'description': 'Deep, sensual female voice perfect for VTM storytelling'
    },
    'es': {
        'voice_id': '21m00Tcm4TlvDq8ikWAM',  # Rachel - Can speak Spanish
        'name': 'Rachel',
        'description': 'Warm, expressive female voice for Spanish narration'
    }
}

def generate_speech(text, language='en', voice_settings=None):
    if not ELEVENLABS_API_KEY:
        print("⚠️  ELEVENLABS_API_KEY not configured")
        raise ValueError("ELEVENLABS_API_KEY not configured")
    
    print(f"🎙️  Generating speech for text: {text[:50]}...")
    
    voice = VOICES.get(language, VOICES['en'])
    voice_id = voice['voice_id']
    
    url = f"{ELEVENLABS_API_URL}/{voice_id}"
    
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY
    }
    
    if voice_settings is None:
        voice_settings = {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.5,
            "use_speaker_boost": True
        }
    
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": voice_settings
    }
    
    try:
        print(f"📡 Calling ElevenLabs API: {url}")
        response = requests.post(url, json=data, headers=headers, timeout=10)
        
        if response.status_code != 200:
            print(f"❌ ElevenLabs API error: {response.status_code} - {response.text}")
            raise Exception(f"ElevenLabs API error: {response.status_code} - {response.text}")
        
        print(f"✅ Speech generated successfully ({len(response.content)} bytes)")
        return response.content
    except requests.exceptions.Timeout:
        print("⏱️  ElevenLabs API timeout (10s)")
        raise Exception("ElevenLabs API timeout")
    except requests.exceptions.RequestException as e:
        print(f"🔥 ElevenLabs API request error: {str(e)}")
        raise Exception(f"ElevenLabs API request error: {str(e)}")

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# Session configuration for persistence
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
UPLOAD_FOLDER = '/tmp/character_portraits'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

client = OpenAI(api_key=OPENAI_API_KEY)

# Database initialization
def init_db():
    conn = sqlite3.connect('vtm_storyteller.db')
    c = conn.cursor()
    
    # Characters table (enhanced)
    c.execute('''CREATE TABLE IF NOT EXISTS characters
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  concept TEXT,
                  chronicle_id INTEGER,
                  clan TEXT,
                  predator_type TEXT,
                  generation INTEGER DEFAULT 13,
                  sire TEXT,
                  ambition TEXT,
                  desire TEXT,
                  attributes TEXT,
                  skills TEXT,
                  disciplines TEXT,
                  health INTEGER DEFAULT 10,
                  willpower INTEGER DEFAULT 5,
                  humanity INTEGER DEFAULT 7,
                  hunger INTEGER DEFAULT 1,
                  blood_potency INTEGER DEFAULT 0,
                  experience INTEGER DEFAULT 0,
                  total_experience INTEGER DEFAULT 0,
                  portrait_path TEXT,
                  demiplane_url TEXT,
                  roll20_character_id TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Chronicles table
    c.execute('''CREATE TABLE IF NOT EXISTS chronicles
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  description TEXT,
                  storyteller TEXT,
                  setting TEXT,
                  current_session INTEGER DEFAULT 1,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Roll history table (enhanced with narrative checkpoints)
    c.execute('''CREATE TABLE IF NOT EXISTS roll_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  character_id INTEGER,
                  chronicle_id INTEGER,
                  session_number INTEGER,
                  roll_type TEXT,
                  pool_size INTEGER,
                  hunger_dice INTEGER,
                  difficulty INTEGER,
                  results TEXT,
                  successes INTEGER,
                  outcome TEXT,
                  narrative_context TEXT,
                  is_checkpoint BOOLEAN DEFAULT 0,
                  checkpoint_name TEXT,
                  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (character_id) REFERENCES characters (id),
                  FOREIGN KEY (chronicle_id) REFERENCES chronicles (id))''')
    
    # XP log table
    c.execute('''CREATE TABLE IF NOT EXISTS xp_log
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  character_id INTEGER,
                  amount INTEGER,
                  reason TEXT,
                  spent_on TEXT,
                  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (character_id) REFERENCES characters (id))''')
    
    # Disciplines database
    c.execute('''CREATE TABLE IF NOT EXISTS disciplines
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  level INTEGER,
                  description TEXT,
                  system TEXT,
                  cost TEXT,
                  dice_pools TEXT,
                  duration TEXT,
                  amalgam TEXT,
                  prerequisite TEXT)''')
    
    # Health logs table
    c.execute('''CREATE TABLE IF NOT EXISTS health_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  component TEXT,
                  status TEXT,
                  message TEXT)''')
    
    # Campaign Database tables
    c.execute('''CREATE TABLE IF NOT EXISTS campaigns
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL UNIQUE,
                  description TEXT,
                  city TEXT,
                  faction TEXT,
                  status TEXT DEFAULT 'active',
                  current_session INTEGER DEFAULT 0,
                  total_sessions INTEGER DEFAULT 0,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS campaign_npcs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  campaign_id INTEGER,
                  name TEXT NOT NULL,
                  real_name TEXT,
                  clan TEXT,
                  faction TEXT,
                  position TEXT,
                  attributes TEXT,
                  skills TEXT,
                  disciplines TEXT,
                  personality TEXT,
                  appearance TEXT,
                  quirks TEXT,
                  backstory TEXT,
                  status TEXT DEFAULT 'alive',
                  tags TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (campaign_id) REFERENCES campaigns (id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS campaign_locations
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  campaign_id INTEGER,
                  name TEXT NOT NULL,
                  type TEXT,
                  city TEXT,
                  description TEXT,
                  rooms TEXT,
                  atmosphere TEXT,
                  security TEXT,
                  hidden_elements TEXT,
                  status TEXT DEFAULT 'active',
                  tags TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (campaign_id) REFERENCES campaigns (id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS campaign_items
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  campaign_id INTEGER,
                  name TEXT NOT NULL,
                  type TEXT,
                  stats TEXT,
                  features TEXT,
                  backstory TEXT,
                  owner TEXT,
                  status TEXT DEFAULT 'intact',
                  tags TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (campaign_id) REFERENCES campaigns (id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS campaign_events
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  campaign_id INTEGER,
                  session_number INTEGER,
                  event_type TEXT,
                  description TEXT,
                  participants TEXT,
                  outcome TEXT,
                  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (campaign_id) REFERENCES campaigns (id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS npc_relationships
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  npc1_id INTEGER,
                  npc2_id INTEGER,
                  relationship_type TEXT,
                  description TEXT,
                  strength INTEGER DEFAULT 0,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (npc1_id) REFERENCES campaign_npcs (id),
                  FOREIGN KEY (npc2_id) REFERENCES campaign_npcs (id))''')
    
    conn.commit()
    conn.close()

init_db()

# Conversation histories
conversation_histories = {}

def get_conversation_history(user_id="default"):
    if user_id not in conversation_histories:
        conversation_histories[user_id] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
    return conversation_histories[user_id]

# System prompt for the Storyteller
SYSTEM_PROMPT = """You are an expert Storyteller for Vampire: The Masquerade 5th Edition. You guide players through immersive chronicles in the World of Darkness.

Your responsibilities:
- Narrate compelling stories with rich atmosphere
- Explain VTM 5e rules and mechanics clearly
- Create memorable NPCs and locations
- Suggest appropriate dice rolls when needed (Attribute + Skill)
- Track character Hunger, Health, Willpower, and Humanity
- Enforce the Masquerade and vampire society rules
- Provide consequences for player actions
- Adapt to player choices and improvise

CHARACTER AWARENESS:
When a player has an active character, you will receive their complete character sheet in the conversation context. Use this information to:
- Reference their specific attributes, skills, and disciplines
- Calculate appropriate dice pools (Attribute + Skill + any bonuses)
- Track their current Health, Willpower, Humanity, and Hunger levels
- Suggest actions that fit their character's abilities and strengths
- Incorporate their Ambition, Desire, and Touchstones into the narrative
- Respect their clan bane and predator type in feeding scenes
- Apply Blood Potency benefits (Blood Surge, Mend, Power Bonus)

FACTION KNOWLEDGE:
You have deep knowledge of vampire factions:

CAMARILLA:
- Feudal hierarchy with Princes, Primogen Councils, and court positions (Seneschal, Sheriff, Keeper of Elysium, Harpy, Scourge)
- Core philosophy: Order, tradition, preservation of the Masquerade
- Core clans: Ventrue, Toreador, Tremere, Malkavian, Nosferatu, Banu Haqim (recently joined)
- Important cities: Vienna, London, Paris, Berlin, Prague
- Themes: Feudalism, politics, elitism, ancient traditions, blood bonds

ANARCH MOVEMENT:
- Democratic structure with elected Barons, Emissaries, Constables
- Core philosophy: Freedom, equality, rejection of elder tyranny
- Core clans: Brujah, Gangrel, Caitiff, Thin-Blooded, Ministry (allied)
- Important territories: Los Angeles, San Francisco, Barcelona
- Themes: Revolution, community, pragmatism, meritocracy, acceptance

When players interact with faction NPCs or enter faction territories, naturally incorporate appropriate faction politics, hierarchies, and themes. Reference court positions, Baron councils, or faction conflicts when relevant to the story.

KNOWLEDGE RESOURCES:
You have access to comprehensive V5 knowledge including:
- Official V5 Core Rulebook mechanics and lore
- Camarilla and Anarch sourcebook content
- V5 Homebrew Wiki (https://www.v5homebrew.com/wiki/Main_Page) for community content and expanded options
- White Wolf Fandom Wiki (https://whitewolf.fandom.com/wiki/Vampire:_The_Masquerade_5th_Edition) for comprehensive lore

When players ask about specific disciplines, powers, clans, or mechanics not in your immediate knowledge, acknowledge these resources exist and provide the best information you can based on V5 rules.

DICE MECHANICS:
- Standard roll: Attribute + Skill (e.g., Strength + Brawl)
- Hunger dice: Replace regular dice equal to character's Hunger level
- Difficulty: Set by Storyteller (typically 2-6)
- Success: Each die showing 6+ is a success
- Critical: Pair of 10s ("Critical Win")
- Bestial Failure: No successes + 1+ Hunger dice show 1 ("Bestial Failure")
- Messy Critical: Success + 1+ Hunger dice show 10 ("Messy Critical")

Be dramatic, atmospheric, and true to the gothic-punk aesthetic of VTM. Always maintain the tension between the Beast and Humanity."""


# Roll20 API functions
def sync_to_roll20(character_data, roll20_character_id=None):
    """Sync character to Roll20 using their API"""
    # Note: This requires Roll20 API credentials and proper authentication
    # For now, this is a placeholder that returns the structure
    
    roll20_data = {
        "name": character_data.get("name"),
        "avatar": character_data.get("portrait_url", ""),
        "bio": f"{character_data.get('concept')} - {character_data.get('clan')}",
        "attributes": {
            # Physical
            "strength": character_data.get("attributes", {}).get("strength", 1),
            "dexterity": character_data.get("attributes", {}).get("dexterity", 1),
            "stamina": character_data.get("attributes", {}).get("stamina", 1),
            # Social
            "charisma": character_data.get("attributes", {}).get("charisma", 1),
            "manipulation": character_data.get("attributes", {}).get("manipulation", 1),
            "composure": character_data.get("attributes", {}).get("composure", 1),
            # Mental
            "intelligence": character_data.get("attributes", {}).get("intelligence", 1),
            "wits": character_data.get("attributes", {}).get("wits", 1),
            "resolve": character_data.get("attributes", {}).get("resolve", 1),
        },
        "skills": character_data.get("skills", {}),
        "disciplines": character_data.get("disciplines", {}),
        "health": character_data.get("health", 10),
        "willpower": character_data.get("willpower", 5),
        "humanity": character_data.get("humanity", 7),
        "hunger": character_data.get("hunger", 1),
    }
    
    # TODO: Implement actual Roll20 API call
    # For now, return success with mock character ID
    if not roll20_character_id:
        roll20_character_id = f"roll20_{secrets.token_hex(8)}"
    
    return {
        "success": True,
        "roll20_character_id": roll20_character_id,
        "message": "Character synced to Roll20 (mock implementation)"
    }

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Routes

@app.route('/')
def index():
    session.permanent = True  # Make session persistent across tabs
    return render_template_string(HTML_TEMPLATE)

# Add these routes after line 273 (after the index route)

@app.route('/character', methods=['GET'])
def list_characters():
    """List all characters"""
    try:
        conn = sqlite3.connect('vtm_storyteller.db')
        c = conn.cursor()
        c.execute('SELECT * FROM characters')
        characters = c.execute('''SELECT id, name, clan, concept, chronicle_id, 
                                 generation, sire, predator_type, ambition, desire,
                                 attributes, skills, disciplines, backgrounds,
                                 health, willpower, humanity, hunger, experience,
                                 created_at, updated_at 
                                 FROM characters''').fetchall()
        conn.close()
        
        result = []
        for char in characters:
            result.append({
                'id': char[0],
                'name': char[1],
                'clan': char[2],
                'concept': char[3],
                'chronicle_id': char[4],
                'generation': char[5],
                'sire': char[6],
                'predator_type': char[7],
                'ambition': char[8],
                'desire': char[9],
                'attributes': json.loads(char[10]) if char[10] else {},
                'skills': json.loads(char[11]) if char[11] else {},
                'disciplines': json.loads(char[12]) if char[12] else {},
                'backgrounds': json.loads(char[13]) if char[13] else {},
                'health': char[14],
                'willpower': char[15],
                'humanity': char[16],
                'hunger': char[17],
                'experience': char[18],
                'created_at': char[19],
                'updated_at': char[20]
            })
        
        return jsonify({'characters': result}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/character', methods=['POST'])
@app.route('/character/create', methods=['POST'])
def create_character():
    """Create a new character"""
    try:
        data = request.json
        
        # Support user_id from frontend
        user_id = data.get('user_id', session.get('user_id', 'default'))
        
        # Required fields
        name = data.get('name')
        clan = data.get('clan')
        concept = data.get('concept', '')
        
        if not name or not clan:
            return jsonify({'error': 'Name and clan are required'}), 400
        
        # Optional fields with defaults
        chronicle_id = data.get('chronicle_id')
        generation = data.get('generation', 13)
        sire = data.get('sire', '')
        predator_type = data.get('predator_type', '')
        ambition = data.get('ambition', '')
        desire = data.get('desire', '')
        
        # Stats
        attributes = json.dumps(data.get('attributes', {
            'strength': 1, 'dexterity': 1, 'stamina': 1,
            'charisma': 1, 'manipulation': 1, 'composure': 1,
            'intelligence': 1, 'wits': 1, 'resolve': 1
        }))
        skills = json.dumps(data.get('skills', {}))
        disciplines = json.dumps(data.get('disciplines', {}))
        backgrounds = json.dumps(data.get('backgrounds', {}))
        
        health = data.get('health', 3)
        willpower = data.get('willpower', 2)
        humanity = data.get('humanity', 7)
        hunger = data.get('hunger', 1)
        experience = data.get('experience', 0)
        
        conn = sqlite3.connect('vtm_storyteller.db')
        c = conn.cursor()
        c.execute('''INSERT INTO characters 
                    (name, clan, concept, chronicle_id, generation, sire, predator_type,
                     ambition, desire, attributes, skills, disciplines, backgrounds,
                     health, willpower, humanity, hunger, experience)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                 (name, clan, concept, chronicle_id, generation, sire, predator_type,
                  ambition, desire, attributes, skills, disciplines, backgrounds,
                  health, willpower, humanity, hunger, experience))
        character_id = c.lastrowid
        conn.commit()
        conn.close()
        
        # Store in session
        session['active_character_id'] = character_id
        
        return jsonify({
            'success': True,
            'message': 'Character created successfully',
            'character_id': character_id
        }), 201
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/character/<int:character_id>', methods=['GET'])
def get_character(character_id):
    """Get a specific character"""
    try:
        conn = sqlite3.connect('vtm_storyteller.db')
        c = conn.cursor()
        char = c.execute('''SELECT id, name, clan, concept, chronicle_id, 
                           generation, sire, predator_type, ambition, desire,
                           attributes, skills, disciplines, backgrounds,
                           health, willpower, humanity, hunger, experience,
                           created_at, updated_at 
                           FROM characters WHERE id = ?''', (character_id,)).fetchone()
        conn.close()
        
        if not char:
            return jsonify({'error': 'Character not found'}), 404
        
        result = {
            'id': char[0],
            'name': char[1],
            'clan': char[2],
            'concept': char[3],
            'chronicle_id': char[4],
            'generation': char[5],
            'sire': char[6],
            'predator_type': char[7],
            'ambition': char[8],
            'desire': char[9],
            'attributes': json.loads(char[10]) if char[10] else {},
            'skills': json.loads(char[11]) if char[11] else {},
            'disciplines': json.loads(char[12]) if char[12] else {},
            'backgrounds': json.loads(char[13]) if char[13] else {},
            'health': char[14],
            'willpower': char[15],
            'humanity': char[16],
            'hunger': char[17],
            'experience': char[18],
            'created_at': char[19],
            'updated_at': char[20]
        }
        
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/character/<int:character_id>', methods=['PUT'])
def update_character(character_id):
    """Update a character"""
    try:
        data = request.json
        
        conn = sqlite3.connect('vtm_storyteller.db')
        c = conn.cursor()
        
        # Check if character exists
        char = c.execute('SELECT id FROM characters WHERE id = ?', (character_id,)).fetchone()
        if not char:
            conn.close()
            return jsonify({'error': 'Character not found'}), 404
        
        # Build update query dynamically
        updates = []
        values = []
        
        for field in ['name', 'clan', 'concept', 'generation', 'sire', 'predator_type',
                     'ambition', 'desire', 'health', 'willpower', 'humanity', 'hunger', 'experience']:
            if field in data:
                updates.append(f'{field} = ?')
                values.append(data[field])
        
        for field in ['attributes', 'skills', 'disciplines', 'backgrounds']:
            if field in data:
                updates.append(f'{field} = ?')
                values.append(json.dumps(data[field]))
        
        if updates:
            updates.append('updated_at = CURRENT_TIMESTAMP')
            values.append(character_id)
            query = f"UPDATE characters SET {', '.join(updates)} WHERE id = ?"
            c.execute(query, values)
            conn.commit()
        
        conn.close()
        
        return jsonify({'message': 'Character updated successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/character/<int:character_id>', methods=['DELETE'])
def delete_character(character_id):
    """Delete a character"""
    try:
        conn = sqlite3.connect('vtm_storyteller.db')
        c = conn.cursor()
        
        # Check if character exists
        char = c.execute('SELECT id FROM characters WHERE id = ?', (character_id,)).fetchone()
        if not char:
            conn.close()
            return jsonify({'error': 'Character not found'}), 404
        
        c.execute('DELETE FROM characters WHERE id = ?', (character_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Character deleted successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/character/link', methods=['POST'])
@app.route('/character/link-demiplane', methods=['POST'])
def link_demiplane_character():
    """Link a Demiplane character"""
    try:
        data = request.json
        
        # Support both frontend parameter names
        url = data.get('demiplane_url') or data.get('url')
        name = data.get('name')
        clan = data.get('clan')
        predator_type = data.get('predator_type', '')
        archetype = data.get('archetype', predator_type)
        user_id = data.get('user_id', session.get('user_id', 'default'))
        
        if not url or not name or not clan:
            return jsonify({'success': False, 'error': 'URL, name, and clan are required'}), 400
        
        conn = sqlite3.connect('vtm_storyteller.db')
        c = conn.cursor()
        
        # Ensure demiplane_url column exists
        try:
            c.execute("ALTER TABLE characters ADD COLUMN demiplane_url TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            # Column already exists
            pass
        
        # Ensure backgrounds column exists
        try:
            c.execute("ALTER TABLE characters ADD COLUMN backgrounds TEXT DEFAULT '{}'")
            conn.commit()
        except sqlite3.OperationalError:
            # Column already exists
            pass
        
        # Create a character entry with demiplane_url
        c.execute('''INSERT INTO characters 
                    (name, clan, concept, demiplane_url, attributes, skills, disciplines, backgrounds)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                 (name, clan, archetype, url, '{}', '{}', '{}', '{}'))
        character_id = c.lastrowid
        conn.commit()
        conn.close()
        
        # Store in session
        session['active_character_id'] = character_id
        
        return jsonify({
            'success': True,
            'message': 'Demiplane character linked successfully',
            'character_id': character_id
        }), 201
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/rules/<rule_type>', methods=['GET'])
def get_rules(rule_type):
    """Get rules by type"""
    try:
        conn = sqlite3.connect('vtm_storyteller.db')
        c = conn.cursor()
        
        if rule_type == 'character-creation':
            rules = c.execute('SELECT * FROM character_creation_rules ORDER BY category, id').fetchall()
            result = [{
                'id': r[0], 'category': r[1], 'rule_name': r[2], 'description': r[3],
                'points_available': r[4], 'minimum_value': r[5], 'maximum_value': r[6]
            } for r in rules]
        elif rule_type == 'attributes':
            rules = c.execute('SELECT * FROM attributes_rules ORDER BY category, attribute_name').fetchall()
            result = [{
                'id': r[0], 'attribute_name': r[1], 'category': r[2],
                'description': r[3], 'specializations': r[4]
            } for r in rules]
        elif rule_type == 'skills':
            rules = c.execute('SELECT * FROM skills_rules ORDER BY category, skill_name').fetchall()
            result = [{
                'id': r[0], 'skill_name': r[1], 'category': r[2],
                'description': r[3], 'specializations': r[4]
            } for r in rules]
        elif rule_type == 'combat':
            rules = c.execute('SELECT * FROM combat_rules ORDER BY rule_type, rule_name').fetchall()
            result = [{
                'id': r[0], 'rule_type': r[1], 'rule_name': r[2],
                'description': r[3], 'mechanics': r[4], 'examples': r[5]
            } for r in rules]
        elif rule_type == 'hunger':
            rules = c.execute('SELECT * FROM hunger_rules ORDER BY hunger_level').fetchall()
            result = [{
                'id': r[0], 'hunger_level': r[1], 'description': r[2],
                'effects': r[3], 'feeding_requirements': r[4]
            } for r in rules]
        elif rule_type == 'humanity':
            rules = c.execute('SELECT * FROM humanity_rules ORDER BY humanity_level DESC').fetchall()
            result = [{
                'id': r[0], 'humanity_level': r[1], 'description': r[2],
                'stains_to_lose': r[3], 'bane_severity': r[4], 'effects': r[5]
            } for r in rules]
        elif rule_type == 'experience':
            rules = c.execute('SELECT * FROM experience_rules ORDER BY trait_type, current_rating').fetchall()
            result = [{
                'id': r[0], 'trait_type': r[1], 'current_rating': r[2],
                'xp_cost': r[3], 'description': r[4]
            } for r in rules]
        else:
            conn.close()
            return jsonify({'error': 'Invalid rule type'}), 400
        
        conn.close()
        return jsonify({'rules': result}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500



@app.route('/health')
def health_check():
    try:
        # Check database
        conn = sqlite3.connect('vtm_storyteller.db')
        conn.close()
        db_status = "healthy"
    except Exception as e:
        db_status = "unhealthy"
        
    try:
        # Check OpenAI API
        client.models.list()
        api_status = "healthy"
    except Exception as e:
        api_status = "unhealthy"
    
    overall_status = "healthy" if db_status == "healthy" and api_status == "healthy" else "degraded"
    
    # Get error metrics
    conn = sqlite3.connect('vtm_storyteller.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM health_logs WHERE status='error' AND timestamp > datetime('now', '-1 hour')")
    recent_errors = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM health_logs")
    total_logs = c.fetchone()[0]
    conn.close()
    
    return jsonify({
        "status": overall_status,
        "components": {
            "database": db_status,
            "openai_api": api_status
        },
        "metrics": {
            "recent_errors_count": recent_errors,
            "total_logs": total_logs
        },
        "timestamp": datetime.now().isoformat()
    })

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        user_message = data.get('message', '')
        user_id = data.get('user_id', session.get('user_id', 'default'))
        
        # Check if message is a command
        if command_system.is_command(user_message):
            result = command_system.execute_command(user_message)
            if 'error' in result:
                return jsonify({'response': f"❌ Error: {result['error']}"})
            else:
                return jsonify({'response': result.get('message', 'Command executed successfully.')})
        
        # Get conversation history
        history = get_conversation_history(user_id)
        
        # Check if user has an active character and inject context
        character_context = None
        campaign_context = None
        try:
            # Import character integration functions
            import sys
            sys.path.append(os.path.dirname(__file__))
            from ai_character_integration import get_character_summary_for_chat
            from campaign_ai_integration import integrate_with_chat_endpoint
            
            character_context = get_character_summary_for_chat(user_id)
            
            # Get campaign database context
            campaign_integration = integrate_with_chat_endpoint(user_message, campaign_id=1)
            campaign_context = campaign_integration['additional_context']
            
        except Exception as char_error:
            print(f"Could not load character/campaign context: {char_error}")
        
        # Inject character and campaign context into user message if available
        enhanced_message = user_message
        if character_context:
            enhanced_message = f"{character_context}\n\n{enhanced_message}"
        if campaign_context:
            enhanced_message = f"{campaign_context}\n\n{enhanced_message}"
        
        enhanced_message = f"Player: {enhanced_message}"
        
        # Add user message with character context
        history.append({"role": "user", "content": enhanced_message})
        
        # Keep only last 20 messages to avoid token limits
        if len(history) > 21:  # 1 system + 20 messages
            history = [history[0]] + history[-20:]
        
        # Get AI response
        response = client.chat.completions.create(
            model="gpt-5.6-luna",
            messages=history,
            max_completion_tokens=1000,
            temperature=0.8
        )
        
        assistant_message = response.choices[0].message.content
        
        # Add assistant response to history
        history.append({"role": "assistant", "content": assistant_message})
        
        # Detect and store suggested dice rolls from AI
        try:
            roll_suggestion = intelligent_dice.extract_roll_from_ai_message(assistant_message)
            if roll_suggestion:
                session_id = get_active_session_id() or 'default'
                intelligent_dice.store_suggested_roll(session_id, roll_suggestion)
                print(f"🎲 Stored suggested roll: {roll_suggestion}")
        except Exception as dice_error:
            print(f"Could not detect/store dice roll: {dice_error}")
        
        # Auto-save any generated content to campaign database
        try:
            if campaign_integration:
                saved_data = campaign_integration['process_response'](assistant_message)
                if saved_data['saved_count'] > 0:
                    print(f"📊 Auto-saved {saved_data['saved_count']} items to campaign database")
                    for item_type, item_name, item_id in saved_data['saved_items']:
                        print(f"   - {item_type}: {item_name} (ID: {item_id})")
        except Exception as save_error:
            print(f"Could not auto-save to campaign database: {save_error}")
        
        return jsonify({"response": assistant_message})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Chronicle management
@app.route('/chronicle/create', methods=['POST'])
def create_chronicle():
    try:
        data = request.json
        conn = sqlite3.connect('vtm_storyteller.db')
        c = conn.cursor()
        
        c.execute('''INSERT INTO chronicles (name, description, storyteller, setting)
                     VALUES (?, ?, ?, ?)''',
                  (data['name'], data.get('description', ''), 
                   data.get('storyteller', ''), data.get('setting', '')))
        
        chronicle_id = c.lastrowid
        conn.commit()
        conn.close()
        
        return jsonify({"success": True, "chronicle_id": chronicle_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/chronicle/list', methods=['GET'])
def list_chronicles():
    try:
        conn = sqlite3.connect('vtm_storyteller.db')
        c = conn.cursor()
        c.execute('SELECT * FROM chronicles ORDER BY created_at DESC')
        chronicles = []
        for row in c.fetchall():
            chronicles.append({
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "storyteller": row[3],
                "setting": row[4],
                "current_session": row[5],
                "created_at": row[6]
            })
        conn.close()
        return jsonify(chronicles)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Character portrait upload
@app.route('/character/<int:character_id>/portrait', methods=['POST'])
def upload_portrait(character_id):
    try:
        if 'portrait' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files['portrait']
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        if file and allowed_file(file.filename):
            filename = secure_filename(f"char_{character_id}_{secrets.token_hex(8)}.{file.filename.rsplit('.', 1)[1].lower()}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Update character record
            conn = sqlite3.connect('vtm_storyteller.db')
            c = conn.cursor()
            c.execute('UPDATE characters SET portrait_path = ? WHERE id = ?', (filepath, character_id))
            conn.commit()
            conn.close()
            
            return jsonify({"success": True, "portrait_path": filepath})
        else:
            return jsonify({"error": "Invalid file type"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/character/<int:character_id>/portrait', methods=['GET'])
def get_portrait(character_id):
    try:
        conn = sqlite3.connect('vtm_storyteller.db')
        c = conn.cursor()
        c.execute('SELECT portrait_path FROM characters WHERE id = ?', (character_id,))
        result = c.fetchone()
        conn.close()
        
        if result and result[0] and os.path.exists(result[0]):
            return send_file(result[0], mimetype='image/jpeg')
        else:
            return jsonify({"error": "Portrait not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# XP tracking
@app.route('/character/<int:character_id>/xp/add', methods=['POST'])
def add_xp(character_id):
    try:
        data = request.json
        amount = data.get('amount', 0)
        reason = data.get('reason', '')
        
        conn = sqlite3.connect('vtm_storyteller.db')
        c = conn.cursor()
        
        # Add XP to character
        c.execute('UPDATE characters SET experience = experience + ?, total_experience = total_experience + ? WHERE id = ?',
                  (amount, amount, character_id))
        
        # Log XP gain
        c.execute('INSERT INTO xp_log (character_id, amount, reason) VALUES (?, ?, ?)',
                  (character_id, amount, reason))
        
        conn.commit()
        conn.close()
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/character/<int:character_id>/xp/spend', methods=['POST'])
def spend_xp(character_id):
    try:
        data = request.json
        amount = data.get('amount', 0)
        spent_on = data.get('spent_on', '')
        
        conn = sqlite3.connect('vtm_storyteller.db')
        c = conn.cursor()
        
        # Check if character has enough XP
        c.execute('SELECT experience FROM characters WHERE id = ?', (character_id,))
        current_xp = c.fetchone()[0]
        
        if current_xp < amount:
            conn.close()
            return jsonify({"error": "Not enough XP"}), 400
        
        # Spend XP
        c.execute('UPDATE characters SET experience = experience - ? WHERE id = ?', (amount, character_id))
        
        # Log XP spending
        c.execute('INSERT INTO xp_log (character_id, amount, spent_on) VALUES (?, ?, ?)',
                  (character_id, -amount, spent_on))
        
        conn.commit()
        conn.close()
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/character/<int:character_id>/xp/history', methods=['GET'])
def xp_history(character_id):
    try:
        conn = sqlite3.connect('vtm_storyteller.db')
        c = conn.cursor()
        c.execute('SELECT * FROM xp_log WHERE character_id = ? ORDER BY timestamp DESC', (character_id,))
        
        history = []
        for row in c.fetchall():
            history.append({
                "id": row[0],
                "amount": row[2],
                "reason": row[3],
                "spent_on": row[4],
                "timestamp": row[5]
            })
        
        conn.close()
        return jsonify(history)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Roll history with checkpoints
@app.route('/roll/history/<int:character_id>', methods=['GET'])
def get_roll_history(character_id):
    try:
        conn = sqlite3.connect('vtm_storyteller.db')
        c = conn.cursor()
        c.execute('''SELECT * FROM roll_history 
                     WHERE character_id = ? 
                     ORDER BY timestamp DESC''', (character_id,))
        
        history = []
        for row in c.fetchall():
            history.append({
                "id": row[0],
                "roll_type": row[4],
                "pool_size": row[5],
                "hunger_dice": row[6],
                "difficulty": row[7],
                "results": json.loads(row[8]) if row[8] else [],
                "successes": row[9],
                "outcome": row[10],
                "narrative_context": row[11],
                "is_checkpoint": bool(row[12]),
                "checkpoint_name": row[13],
                "timestamp": row[14]
            })
        
        conn.close()
        return jsonify(history)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/roll/checkpoint/create', methods=['POST'])
def create_checkpoint():
    try:
        data = request.json
        character_id = data.get('character_id')
        roll_id = data.get('roll_id')
        checkpoint_name = data.get('checkpoint_name', '')
        
        conn = sqlite3.connect('vtm_storyteller.db')
        c = conn.cursor()
        c.execute('UPDATE roll_history SET is_checkpoint = 1, checkpoint_name = ? WHERE id = ?',
                  (checkpoint_name, roll_id))
        conn.commit()
        conn.close()
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/roll/checkpoint/list/<int:character_id>', methods=['GET'])
def list_checkpoints(character_id):
    try:
        conn = sqlite3.connect('vtm_storyteller.db')
        c = conn.cursor()
        c.execute('''SELECT * FROM roll_history 
                     WHERE character_id = ? AND is_checkpoint = 1 
                     ORDER BY timestamp DESC''', (character_id,))
        
        checkpoints = []
        for row in c.fetchall():
            checkpoints.append({
                "id": row[0],
                "checkpoint_name": row[13],
                "narrative_context": row[11],
                "timestamp": row[14]
            })
        
        conn.close()
        return jsonify(checkpoints)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# PDF Export
@app.route('/character/<int:character_id>/export/pdf', methods=['GET'])
def export_character_pdf(character_id):
    try:
        conn = sqlite3.connect('vtm_storyteller.db')
        c = conn.cursor()
        c.execute('SELECT * FROM characters WHERE id = ?', (character_id,))
        char_data = c.fetchone()
        conn.close()
        
        if not char_data:
            return jsonify({"error": "Character not found"}), 404
        
        # Create PDF
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#8B0000'),
            spaceAfter=30,
            alignment=TA_CENTER
        )
        elements.append(Paragraph(f"🧛 {char_data[1]}", title_style))
        elements.append(Spacer(1, 0.2*inch))
        
        # Basic Info
        info_data = [
            ['Concept:', char_data[2] or 'N/A'],
            ['Clan:', char_data[4] or 'N/A'],
            ['Predator Type:', char_data[5] or 'N/A'],
            ['Generation:', str(char_data[6])],
            ['Chronicle:', 'N/A'],  # TODO: Link to chronicle name
        ]
        
        info_table = Table(info_data, colWidths=[2*inch, 4*inch])
        info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#2a0000')),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 0.3*inch))
        
        # Attributes
        attributes = json.loads(char_data[10]) if char_data[10] else {}
        attr_data = [['ATTRIBUTES', 'Value']]
        for attr, value in attributes.items():
            attr_data.append([attr.capitalize(), '●' * value + '○' * (5 - value)])
        
        attr_table = Table(attr_data, colWidths=[3*inch, 3*inch])
        attr_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#8B0000')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(attr_table)
        elements.append(Spacer(1, 0.3*inch))
        
        # Stats
        stats_data = [
            ['Health:', '●' * char_data[13] + '○' * (10 - char_data[13])],
            ['Willpower:', '●' * char_data[14] + '○' * (10 - char_data[14])],
            ['Humanity:', '●' * char_data[15] + '○' * (10 - char_data[15])],
            ['Hunger:', '●' * char_data[16] + '○' * (5 - char_data[16])],
            ['Blood Potency:', str(char_data[17])],
            ['Experience:', f"{char_data[18]} / {char_data[19]} total"],
        ]
        
        stats_table = Table(stats_data, colWidths=[2*inch, 4*inch])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#2a0000')),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(stats_table)
        
        # Build PDF
        doc.build(elements)
        buffer.seek(0)
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"{char_data[1]}_character_sheet.pdf",
            mimetype='application/pdf'
        )
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Roll20 sync
@app.route('/character/<int:character_id>/sync/roll20', methods=['POST'])
def sync_character_to_roll20(character_id):
    try:
        conn = sqlite3.connect('vtm_storyteller.db')
        c = conn.cursor()
        c.execute('SELECT * FROM characters WHERE id = ?', (character_id,))
        char_data = c.fetchone()
        
        if not char_data:
            conn.close()
            return jsonify({"error": "Character not found"}), 404
        
        # Prepare character data
        character_data = {
            "name": char_data[1],
            "concept": char_data[2],
            "clan": char_data[4],
            "attributes": json.loads(char_data[10]) if char_data[10] else {},
            "skills": json.loads(char_data[11]) if char_data[11] else {},
            "disciplines": json.loads(char_data[12]) if char_data[12] else {},
            "health": char_data[13],
            "willpower": char_data[14],
            "humanity": char_data[15],
            "hunger": char_data[16],
        }
        
        # Sync to Roll20
        result = sync_to_roll20(character_data, char_data[21])
        
        if result["success"]:
            # Update character with Roll20 ID
            c.execute('UPDATE characters SET roll20_character_id = ? WHERE id = ?',
                      (result["roll20_character_id"], character_id))
            conn.commit()
        
        conn.close()
        return jsonify(result)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Disciplines database
@app.route('/disciplines/list', methods=['GET'])
def list_disciplines():
    try:
        conn = sqlite3.connect('vtm_storyteller.db')
        c = conn.cursor()
        c.execute('SELECT * FROM disciplines ORDER BY name, level')
        
        disciplines = []
        for row in c.fetchall():
            disciplines.append({
                "id": row[0],
                "name": row[1],
                "level": row[2],
                "description": row[3],
                "system": row[4],
                "cost": row[5],
                "dice_pools": row[6],
                "duration": row[7],
                "amalgam": row[8],
                "prerequisite": row[9]
            })
        
        conn.close()
        return jsonify(disciplines)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# HTML Template placeholder
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🧛 VTM Storyteller - Hybrid Character System</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Georgia', serif;
            background: linear-gradient(135deg, #1a0000 0%, #2d0a0a 50%, #1a0000 100%);
            color: #e0e0e0;
            min-height: 100vh;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }
        
        header {
            text-align: center;
            padding: 30px 0;
            border-bottom: 2px solid #8b0000;
            margin-bottom: 30px;
        }
        
        h1 {
            font-size: 3em;
            color: #ff0000;
            text-shadow: 0 0 20px rgba(255, 0, 0, 0.5);
            margin-bottom: 10px;
        }
        
        .subtitle {
            color: #999;
            font-style: italic;
            font-size: 1.1em;
        }
        
        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 30px;
            flex-wrap: wrap;
        }
        
        .tab {
            padding: 15px 30px;
            background: #2a0505;
            border: 2px solid #8b0000;
            color: #e0e0e0;
            cursor: pointer;
            transition: all 0.3s;
            font-size: 1.1em;
            border-radius: 5px;
        }
        
        .tab:hover {
            background: #3d0808;
            border-color: #ff0000;
        }
        
        .tab.active {
            background: #8b0000;
            border-color: #ff0000;
            color: #fff;
            box-shadow: 0 0 20px rgba(139, 0, 0, 0.5);
        }
        
        .tab-content {
            display: none;
            animation: fadeIn 0.3s;
        }
        
        .tab-content.active {
            display: block;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
        
        /* Chat Section */
        .chat-container {
            background: #1a0505;
            border: 2px solid #8b0000;
            border-radius: 10px;
            padding: 20px;
            height: 600px;
            display: flex;
            flex-direction: column;
        }
        
        .messages {
            flex: 1;
            overflow-y: auto;
            margin-bottom: 20px;
            padding: 15px;
            background: #0d0202;
            border-radius: 5px;
        }
        
        .message {
            margin-bottom: 20px;
            padding: 15px;
            border-radius: 8px;
            line-height: 1.6;
        }
        
        .message.user {
            background: #2a0505;
            border-left: 4px solid #ff0000;
        }
        
        .message.assistant {
            background: #051a1a;
            border-left: 4px solid #00ff00;
        }
        
        .message-label {
            font-weight: bold;
            margin-bottom: 8px;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .user .message-label {
            color: #ff0000;
        }
        
        .assistant .message-label {
            color: #00ff00;
        }
        
        .input-area {
            display: flex;
            gap: 10px;
        }
        
        input[type="text"], textarea {
            flex: 1;
            padding: 15px;
            background: #0d0202;
            border: 2px solid #8b0000;
            color: #e0e0e0;
            border-radius: 5px;
            font-family: 'Georgia', serif;
            font-size: 1em;
        }
        
        input[type="text"]:focus, textarea:focus {
            outline: none;
            border-color: #ff0000;
            box-shadow: 0 0 10px rgba(255, 0, 0, 0.3);
        }
        
        button {
            padding: 15px 30px;
            background: #8b0000;
            border: 2px solid #ff0000;
            color: #fff;
            cursor: pointer;
            border-radius: 5px;
            font-size: 1em;
            font-weight: bold;
            transition: all 0.3s;
            font-family: 'Georgia', serif;
        }
        
        button:hover:not(:disabled) {
            background: #a00000;
            box-shadow: 0 0 20px rgba(255, 0, 0, 0.5);
            transform: translateY(-2px);
        }
        
        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        
        /* Character System */
        .character-options {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 30px;
            margin-bottom: 30px;
        }
        
        .option-card {
            background: #1a0505;
            border: 2px solid #8b0000;
            border-radius: 10px;
            padding: 30px;
            transition: all 0.3s;
        }
        
        .option-card:hover {
            border-color: #ff0000;
            box-shadow: 0 0 30px rgba(139, 0, 0, 0.3);
        }
        
        .option-card h3 {
            color: #ff0000;
            margin-bottom: 15px;
            font-size: 1.8em;
        }
        
        .option-card p {
            color: #999;
            margin-bottom: 20px;
            line-height: 1.6;
        }
        
        /* Demiplane Link Section */
        .demiplane-link {
            background: #0a1a0a;
            border: 2px solid #00ff00;
            border-radius: 10px;
            padding: 20px;
            margin-top: 20px;
        }
        
        .demiplane-link h4 {
            color: #00ff00;
            margin-bottom: 15px;
        }
        
        .linked-character {
            background: #051a05;
            padding: 20px;
            border-radius: 5px;
            margin-top: 15px;
        }
        
        .linked-character p {
            margin: 10px 0;
        }
        
        .linked-character strong {
            color: #00ff00;
        }
        
        /* Character Creation Form */
        .creation-wizard {
            background: #1a0505;
            border: 2px solid #8b0000;
            border-radius: 10px;
            padding: 30px;
        }
        
        .wizard-step {
            display: none;
        }
        
        .wizard-step.active {
            display: block;
            animation: fadeIn 0.3s;
        }
        
        .wizard-step h3 {
            color: #ff0000;
            margin-bottom: 20px;
            font-size: 2em;
        }
        
        .form-group {
            margin-bottom: 25px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 10px;
            color: #ff0000;
            font-weight: bold;
            font-size: 1.1em;
        }
        
        .form-group input, .form-group select {
            width: 100%;
            padding: 12px;
            background: #0d0202;
            border: 2px solid #8b0000;
            color: #e0e0e0;
            border-radius: 5px;
            font-size: 1em;
        }
        
        .clan-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 15px;
        }
        
        .clan-option {
            padding: 20px;
            background: #2a0505;
            border: 2px solid #8b0000;
            border-radius: 5px;
            cursor: pointer;
            text-align: center;
            transition: all 0.3s;
        }
        
        .clan-option:hover {
            border-color: #ff0000;
            background: #3d0808;
        }
        
        .clan-option.selected {
            border-color: #ff0000;
            background: #8b0000;
            box-shadow: 0 0 20px rgba(255, 0, 0, 0.5);
        }
        
        .attributes-grid, .skills-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
        }
        
        .attribute-category, .skill-category {
            background: #0d0202;
            padding: 20px;
            border-radius: 5px;
            border: 2px solid #8b0000;
        }
        
        .attribute-category h4, .skill-category h4 {
            color: #ff0000;
            margin-bottom: 15px;
            text-align: center;
        }
        
        .attribute-item, .skill-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }
        
        .dots {
            display: flex;
            gap: 5px;
        }
        
        .dot {
            width: 20px;
            height: 20px;
            border-radius: 50%;
            border: 2px solid #8b0000;
            background: #0d0202;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .dot:hover {
            border-color: #ff0000;
        }
        
        .dot.filled {
            background: #ff0000;
            box-shadow: 0 0 10px rgba(255, 0, 0, 0.5);
        }
        
        .points-remaining {
            text-align: center;
            font-size: 1.2em;
            color: #ff0000;
            margin-bottom: 20px;
            padding: 10px;
            background: #0d0202;
            border-radius: 5px;
        }
        
        .wizard-nav {
            display: flex;
            justify-content: space-between;
            margin-top: 30px;
        }
        
        /* Character Sheet */
        .character-sheet {
            background: #1a0505;
            border: 2px solid #8b0000;
            border-radius: 10px;
            padding: 30px;
        }
        
        .sheet-header {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid #8b0000;
        }
        
        .sheet-header-item {
            text-align: center;
        }
        
        .sheet-header-item label {
            display: block;
            color: #999;
            font-size: 0.9em;
            margin-bottom: 5px;
        }
        
        .sheet-header-item .value {
            color: #ff0000;
            font-size: 1.5em;
            font-weight: bold;
        }
        
        .trackers {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .tracker {
            background: #0d0202;
            padding: 20px;
            border-radius: 5px;
            border: 2px solid #8b0000;
            text-align: center;
        }
        
        .tracker h4 {
            color: #ff0000;
            margin-bottom: 15px;
        }
        
        .tracker-boxes {
            display: flex;
            justify-content: center;
            gap: 8px;
            flex-wrap: wrap;
        }
        
        .tracker-box {
            width: 30px;
            height: 30px;
            border: 2px solid #8b0000;
            background: #0d0202;
            cursor: pointer;
            transition: all 0.2s;
            border-radius: 3px;
        }
        
        .tracker-box:hover {
            border-color: #ff0000;
        }
        
        .tracker-box.filled {
            background: #ff0000;
        }
        
        .tracker-box.damage {
            background: #000;
            border-color: #ff0000;
        }
        
        /* Dice Roller */
        .dice-roller {
            background: #1a0505;
            border: 2px solid #8b0000;
            border-radius: 10px;
            padding: 30px;
        }
        
        .dice-controls {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .dice-input {
            background: #0d0202;
            padding: 20px;
            border-radius: 5px;
            border: 2px solid #8b0000;
        }
        
        .dice-input label {
            display: block;
            color: #ff0000;
            margin-bottom: 10px;
            font-weight: bold;
        }
        
        .dice-input input[type="number"] {
            width: 100%;
            padding: 12px;
            background: #1a0505;
            border: 2px solid #8b0000;
            color: #e0e0e0;
            border-radius: 5px;
            font-size: 1.2em;
            text-align: center;
        }
        
        .dice-result {
            background: #0d0202;
            padding: 30px;
            border-radius: 5px;
            border: 2px solid #8b0000;
            margin-top: 30px;
            display: none;
        }
        
        .dice-result.show {
            display: block;
            animation: fadeIn 0.5s;
        }
        
        .dice-display {
            display: flex;
            gap: 30px;
            margin-bottom: 30px;
            flex-wrap: wrap;
        }
        
        .dice-group h4 {
            color: #ff0000;
            margin-bottom: 15px;
        }
        
        .dice-list {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        
        .die {
            width: 50px;
            height: 50px;
            border: 3px solid #8b0000;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5em;
            font-weight: bold;
            background: #1a0505;
            color: #fff;
        }
        
        .die.hunger {
            border-color: #ff0000;
            background: #3d0000;
        }
        
        .die.success {
            background: #003d00;
            border-color: #00ff00;
            color: #00ff00;
        }
        
        .die.ten {
            background: #3d3d00;
            border-color: #ffff00;
            color: #ffff00;
        }
        
        .result-summary {
            text-align: center;
            padding: 20px;
            background: #1a0505;
            border-radius: 5px;
        }
        
        .result-summary h3 {
            font-size: 2em;
            margin-bottom: 15px;
        }
        
        .result-summary.critical {
            background: #3d3d00;
            border: 3px solid #ffff00;
        }
        
        .result-summary.critical h3 {
            color: #ffff00;
        }
        
        .result-summary.messy {
            background: #3d0000;
            border: 3px solid #ff0000;
        }
        
        .result-summary.messy h3 {
            color: #ff0000;
        }
        
        .result-summary.bestial {
            background: #000;
            border: 3px solid #ff0000;
        }
        
        .result-summary.bestial h3 {
            color: #ff0000;
        }
        
        .result-summary.success {
            background: #003d00;
            border: 3px solid #00ff00;
        }
        
        .result-summary.success h3 {
            color: #00ff00;
        }
        
        /* Status indicator */
        .status {
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 15px 25px;
            border-radius: 5px;
            font-weight: bold;
            z-index: 1000;
        }
        
        .status.online {
            background: #003d00;
            border: 2px solid #00ff00;
            color: #00ff00;
        }
        
        .status.degraded {
            background: #3d3d00;
            border: 2px solid #ffff00;
            color: #ffff00;
        }
        
        .typing-indicator {
            display: none;
            padding: 15px;
            color: #999;
            font-style: italic;
        }
        
        .typing-indicator.show {
            display: block;
        }
        
        .typing-dots {
            display: inline-block;
        }
        
        .typing-dots span {
            animation: blink 1.4s infinite;
            animation-fill-mode: both;
        }
        
        .typing-dots span:nth-child(2) {
            animation-delay: 0.2s;
        }
        
        .typing-dots span:nth-child(3) {
            animation-delay: 0.4s;
        }
        
        @keyframes blink {
            0%, 80%, 100% {
                opacity: 0;
            }
            40% {
                opacity: 1;
            }
        }
        
        /* Scrollbar styling */
        ::-webkit-scrollbar {
            width: 10px;
        }
        
        ::-webkit-scrollbar-track {
            background: #0d0202;
        }
        
        ::-webkit-scrollbar-thumb {
            background: #8b0000;
            border-radius: 5px;
        }
        
        ::-webkit-scrollbar-thumb:hover {
            background: #a00000;
        }
        
        /* Voice Toggle Button */
        .voice-toggle {
            padding: 12px 18px;
            background: #2a0505;
            border: 2px solid #8b0000;
            color: #e0e0e0;
            cursor: pointer;
            transition: all 0.3s;
            font-size: 1.5em;
            border-radius: 5px;
            margin-right: 10px;
        }
        
        .voice-toggle:hover {
            background: #3d0808;
            border-color: #ff0000;
            transform: scale(1.05);
        }
        
        .voice-toggle.active {
            background: #8b0000;
            border-color: #ff0000;
            box-shadow: 0 0 20px rgba(139, 0, 0, 0.5);
        }
        
        .voice-toggle.muted {
            opacity: 0.5;
            background: #1a0505;
        }
    </style>
</head>
<body>
    <div class="status online" id="status">System Online</div>
    
    <div class="container">
        <header>
            <h1>🧛 VTM Storyteller</h1>
            <p class="subtitle">Vampire: The Masquerade 5th Edition AI Game Master</p>
            <p class="subtitle">Hybrid Character System</p>
        </header>
        
        <div class="tabs">
            <div class="tab active" onclick="switchTab('chat')">Chat</div>
            <div class="tab" onclick="switchTab('character')">Character</div>
            <div class="tab" onclick="switchTab('sheet')">Character Sheet</div>
            <div class="tab" onclick="switchTab('dice')">Dice Roller</div>
        </div>
        
        <!-- Chat Tab -->
        <div id="chat-tab" class="tab-content active">
            <div class="chat-container">
                <div class="messages" id="messages">
                    <div class="message assistant">
                        <div class="message-label">Storyteller</div>
                        <div>Welcome, Kindred. I am your Storyteller for tonight's chronicle. Whether you seek to create a new character, explore the World of Darkness, or begin your journey into the night, I am here to guide you. What brings you to my domain?</div>
                    </div>
                </div>
                <div class="typing-indicator" id="typing">
                    <span class="typing-dots">
                        <span>.</span><span>.</span><span>.</span>
                    </span>
                    Storyteller is writing...
                </div>
                <div class="input-area">
                    <button onclick="toggleVoice()" id="voice-toggle-btn" class="voice-toggle" title="Toggle voice narration">
                        🔊
                    </button>
                    <input type="text" id="message-input" placeholder="Speak to the Storyteller..." onkeypress="handleKeyPress(event)">
                    <button onclick="sendMessage()" id="send-btn">Send</button>
                </div>
            </div>
        </div>
        
        <!-- Character Tab -->
        <div id="character-tab" class="tab-content">
            <div class="character-options">
                <div class="option-card">
                    <h3>🔗 Link Demiplane Character</h3>
                    <p>Already have a character on Demiplane? Link it here to use with the Storyteller AI. Your character stats will be accessible during gameplay.</p>
                    <button onclick="showDemiplaneLink()">Link Character</button>
                    
                    <div class="demiplane-link" id="demiplane-link-section" style="display: none;">
                        <h4>Enter Your Demiplane Character URL</h4>
                        <input type="text" id="demiplane-url" placeholder="https://app.demiplane.com/nexus/vampire/character-sheet/...">
                        <div style="margin-top: 15px;">
                            <input type="text" id="demiplane-name" placeholder="Character Name" style="margin-bottom: 10px;">
                            <input type="text" id="demiplane-clan" placeholder="Clan" style="margin-bottom: 10px;">
                            <input type="text" id="demiplane-predator" placeholder="Predator Type">
                        </div>
                        <button onclick="linkDemiplaneCharacter()" style="margin-top: 15px;">Save Link</button>
                        
                        <div class="linked-character" id="linked-character" style="display: none;">
                            <h4 style="color: #00ff00;">✓ Character Linked</h4>
                            <p><strong>Name:</strong> <span id="linked-name"></span></p>
                            <p><strong>Clan:</strong> <span id="linked-clan"></span></p>
                            <p><strong>Predator:</strong> <span id="linked-predator"></span></p>
                            <a href="#" id="view-sheet-link" target="_blank" style="color: #00ff00;">View Full Sheet on Demiplane →</a>
                        </div>
                    </div>
                </div>
                
                <div class="option-card">
                    <h3>📄 Upload Character Sheet PDF</h3>
                    <p>Upload your filled VTM 5e character sheet PDF. The system will automatically extract all data and link to your Chronicle.</p>
                    <button onclick="showPDFUpload()">Upload PDF</button>
                    
                    <div class="pdf-upload-section" id="pdf-upload-section" style="display: none;">
                        <h4>Select Your Character Sheet PDF</h4>
                        <input type="file" id="pdf-file-input" accept=".pdf" style="margin: 15px 0;">
                        <div id="pdf-upload-progress" style="display: none; margin: 15px 0;">
                            <div style="background: #1a0505; height: 30px; border-radius: 5px; overflow: hidden;">
                                <div id="pdf-progress-bar" style="background: #8b0000; height: 100%; width: 0%; transition: width 0.3s;"></div>
                            </div>
                            <p id="pdf-progress-text" style="margin-top: 10px; color: #999;">Uploading...</p>
                        </div>
                        <button onclick="uploadPDF()" style="margin-top: 15px;">Upload & Parse</button>
                        
                        <div class="pdf-upload-result" id="pdf-upload-result" style="display: none; margin-top: 20px;">
                            <h4 style="color: #00ff00;">✓ Character Loaded from PDF</h4>
                            <p><strong>Name:</strong> <span id="pdf-char-name"></span></p>
                            <p><strong>Chronicle:</strong> <span id="pdf-char-chronicle"></span></p>
                            <p><strong>Clan:</strong> <span id="pdf-char-clan"></span></p>
                            <div id="pdf-warnings" style="margin-top: 15px; display: none;">
                                <h5 style="color: #ffaa00;">⚠ Warnings:</h5>
                                <ul id="pdf-warning-list" style="color: #ffaa00; margin-left: 20px;"></ul>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="option-card">
                    <h3>✨ Create Custom Character</h3>
                    <p>Create a new character using our built-in character creation wizard. Perfect for quick games or if you don't have a Demiplane account.</p>
                    <button onclick="startCharacterCreation()">Create Character</button>
                </div>
            </div>
            
            <!-- Character Creation Wizard -->
            <div class="creation-wizard" id="creation-wizard" style="display: none;">
                <!-- Step 1: Basic Info -->
                <div class="wizard-step active" id="step-1">
                    <h3>Step 1: Basic Information</h3>
                    <div class="form-group">
                        <label>Character Name</label>
                        <input type="text" id="char-name" placeholder="Enter character name">
                    </div>
                    <div class="form-group">
                        <label>Concept</label>
                        <input type="text" id="char-concept" placeholder="e.g., Street Artist, Corporate Lawyer, Underground DJ">
                    </div>
                    <div class="form-group">
                        <label>Chronicle</label>
                        <input type="text" id="char-chronicle" placeholder="Name of your chronicle">
                    </div>
                    <div class="wizard-nav">
                        <button onclick="cancelCreation()">Cancel</button>
                        <button onclick="nextStep(2)">Next →</button>
                    </div>
                </div>
                
                <!-- Step 2: Clan Selection -->
                <div class="wizard-step" id="step-2">
                    <h3>Step 2: Choose Your Clan</h3>
                    <div class="clan-grid" id="clan-grid">
                        <!-- Clans will be populated by JavaScript -->
                    </div>
                    <div class="wizard-nav">
                        <button onclick="prevStep(1)">← Back</button>
                        <button onclick="nextStep(3)">Next →</button>
                    </div>
                </div>
                
                <!-- Step 3: Attributes -->
                <div class="wizard-step" id="step-3">
                    <h3>Step 3: Distribute Attributes</h3>
                    <p class="points-remaining" id="attr-points">Points Remaining: Physical (7), Social (7), Mental (7)</p>
                    <div class="attributes-grid" id="attributes-grid">
                        <!-- Attributes will be populated by JavaScript -->
                    </div>
                    <div class="wizard-nav">
                        <button onclick="prevStep(2)">← Back</button>
                        <button onclick="nextStep(4)">Next →</button>
                    </div>
                </div>
                
                <!-- Step 4: Skills -->
                <div class="wizard-step" id="step-4">
                    <h3>Step 4: Distribute Skills</h3>
                    <p class="points-remaining" id="skill-points">Points Remaining: 13</p>
                    <div class="skills-grid" id="skills-grid">
                        <!-- Skills will be populated by JavaScript -->
                    </div>
                    <div class="wizard-nav">
                        <button onclick="prevStep(3)">← Back</button>
                        <button onclick="nextStep(5)">Next →</button>
                    </div>
                </div>
                
                <!-- Step 5: Disciplines & Final -->
                <div class="wizard-step" id="step-5">
                    <h3>Step 5: Choose Disciplines</h3>
                    <p style="color: #999; margin-bottom: 20px;">Select 2 dots of Disciplines from your clan's options</p>
                    <div id="disciplines-grid">
                        <!-- Disciplines will be populated based on clan -->
                    </div>
                    <div class="wizard-nav">
                        <button onclick="prevStep(4)">← Back</button>
                        <button onclick="finishCreation()">Create Character</button>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Character Sheet Tab -->
        <div id="sheet-tab" class="tab-content">
            <div class="character-sheet" id="character-sheet">
                <p style="text-align: center; color: #999; padding: 50px;">No character loaded. Create or link a character first.</p>
            </div>
        </div>
        
        <!-- Dice Roller Tab -->
        <div id="dice-tab" class="tab-content">
            <div class="dice-roller">
                <h2 style="color: #ff0000; margin-bottom: 30px; text-align: center;">🎲 VTM 5e Dice Roller</h2>
                <div class="dice-controls">
                    <div class="dice-input">
                        <label>Pool Size</label>
                        <input type="number" id="pool-size" min="1" max="20" value="5">
                    </div>
                    <div class="dice-input">
                        <label>Hunger Dice</label>
                        <input type="number" id="hunger-dice" min="0" max="5" value="1">
                    </div>
                    <div class="dice-input">
                        <label>Difficulty</label>
                        <input type="number" id="difficulty" min="1" max="10" value="2">
                    </div>
                </div>
                <div style="text-align: center; margin-bottom: 30px;">
                    <button onclick="rollDice()" style="font-size: 1.2em; padding: 20px 50px;">🎲 ROLL</button>
                </div>
                <div class="dice-result" id="dice-result">
                    <!-- Results will be displayed here -->
                </div>
            </div>
        </div>
    </div>
    
    <script>
        // Global state
        let currentCharacter = null;
        let userId = 'user_' + Math.random().toString(36).substr(2, 9);
        let voiceEnabled = false;
        let currentAudio = null;
        
        // Voice narration functions
        function toggleVoice() {
            voiceEnabled = !voiceEnabled;
            const btn = document.getElementById('voice-toggle-btn');
            
            if (voiceEnabled) {
                btn.classList.add('active');
                btn.classList.remove('muted');
                btn.textContent = '🔊';
                btn.title = 'Voice narration ON - Click to disable';
            } else {
                btn.classList.remove('active');
                btn.classList.add('muted');
                btn.textContent = '🔇';
                btn.title = 'Voice narration OFF - Click to enable';
                
                // Stop any currently playing audio
                if (currentAudio) {
                    currentAudio.pause();
                    currentAudio = null;
                }
            }
        }
        
        async function playVoiceNarration(text, language = 'en') {
            console.log('🎤 playVoiceNarration called', { voiceEnabled, textLength: text.length });
            if (!voiceEnabled) {
                console.log('❌ Voice disabled, skipping');
                return;
            }
            
            try {
                console.log('📡 Fetching TTS from server...');
                // Stop any currently playing audio
                if (currentAudio) {
                    currentAudio.pause();
                }
                
                // Request TTS from server
                const response = await fetch('/tts', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text, language })
                });
                
                if (!response.ok) {
                    console.error('❌ TTS error:', response.status, response.statusText);
                    return;
                }
                
                console.log('✅ TTS response received');
                
                // Get audio blob
                const audioBlob = await response.blob();
                console.log('🎵 Audio blob received:', audioBlob.size, 'bytes');
                const audioUrl = URL.createObjectURL(audioBlob);
                
                // Play audio
                currentAudio = new Audio(audioUrl);
                console.log('▶️ Attempting to play audio...');
                const playPromise = currentAudio.play();
                
                if (playPromise !== undefined) {
                    playPromise
                        .then(() => console.log('✅ Audio playing successfully'))
                        .catch(error => console.error('❌ Audio playback error:', error));
                }
                
                // Clean up URL when audio finishes
                currentAudio.onended = () => {
                    URL.revokeObjectURL(audioUrl);
                    currentAudio = null;
                };
                
            } catch (error) {
                console.error('Voice narration error:', error);
            }
        }
        
        // VTM 5e Data
        const clans = [
            { name: 'Brujah', disciplines: ['Celerity', 'Potence', 'Presence'] },
            { name: 'Gangrel', disciplines: ['Animalism', 'Fortitude', 'Protean'] },
            { name: 'Malkavian', disciplines: ['Auspex', 'Dominate', 'Obfuscate'] },
            { name: 'Nosferatu', disciplines: ['Animalism', 'Obfuscate', 'Potence'] },
            { name: 'Toreador', disciplines: ['Auspex', 'Celerity', 'Presence'] },
            { name: 'Tremere', disciplines: ['Auspex', 'Blood Sorcery', 'Dominate'] },
            { name: 'Ventrue', disciplines: ['Dominate', 'Fortitude', 'Presence'] },
            { name: 'Caitiff', disciplines: ['Choose any 3'] },
            { name: 'Thin-Blood', disciplines: ['Thin-Blood Alchemy'] }
        ];
        
        const attributes = {
            physical: ['Strength', 'Dexterity', 'Stamina'],
            social: ['Charisma', 'Manipulation', 'Composure'],
            mental: ['Intelligence', 'Wits', 'Resolve']
        };
        
        const skills = {
            physical: ['Athletics', 'Brawl', 'Craft', 'Drive', 'Firearms', 'Larceny', 'Melee', 'Stealth', 'Survival'],
            social: ['Animal Ken', 'Etiquette', 'Insight', 'Intimidation', 'Leadership', 'Performance', 'Persuasion', 'Streetwise', 'Subterfuge'],
            mental: ['Academics', 'Awareness', 'Finance', 'Investigation', 'Medicine', 'Occult', 'Politics', 'Science', 'Technology']
        };
        
        // Character creation state
        let characterData = {
            attributes: {},
            skills: {},
            disciplines: {}
        };
        
        // Tab switching
        function switchTab(tabName) {
            document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
            
            event.target.classList.add('active');
            document.getElementById(tabName + '-tab').classList.add('active');
        }
        
        // Chat functionality
        async function sendMessage() {
            const input = document.getElementById('message-input');
            const message = input.value.trim();
            
            if (!message) return;
            
            // Add user message to chat
            addMessage('user', message);
            input.value = '';
            
            // Disable send button and show typing indicator
            const sendBtn = document.getElementById('send-btn');
            sendBtn.disabled = true;
            document.getElementById('typing').classList.add('show');
            
            try {
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message, user_id: userId })
                });
                
                const data = await response.json();
                
                if (data.error) {
                    addMessage('assistant', 'Error: ' + data.error);
                } else {
                    addMessage('assistant', data.response);
                    // Play voice narration if enabled
                    playVoiceNarration(data.response, 'en');
                }
            } catch (error) {
                addMessage('assistant', 'Error: Connection lost. Please try again.');
            } finally {
                sendBtn.disabled = false;
                document.getElementById('typing').classList.remove('show');
            }
        }
        
        function addMessage(role, content) {
            const messagesDiv = document.getElementById('messages');
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${role}`;
            messageDiv.innerHTML = `
                <div class="message-label">${role === 'user' ? 'You' : 'Storyteller'}</div>
                <div>${content}</div>
            `;
            messagesDiv.appendChild(messageDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }
        
        function handleKeyPress(event) {
            if (event.key === 'Enter') {
                sendMessage();
            }
        }
        
        // Demiplane linking
        function showDemiplaneLink() {
            document.getElementById('demiplane-link-section').style.display = 'block';
        }
        
        async function linkDemiplaneCharacter() {
            const url = document.getElementById('demiplane-url').value;
            const name = document.getElementById('demiplane-name').value;
            const clan = document.getElementById('demiplane-clan').value;
            const predator = document.getElementById('demiplane-predator').value;
            
            if (!url || !name || !clan) {
                alert('Please fill in all required fields');
                return;
            }
            
            try {
                const response = await fetch('/character/link', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        user_id: userId,
                        demiplane_url: url,
                        name,
                        clan,
                        predator_type: predator
                    })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    document.getElementById('linked-name').textContent = name;
                    document.getElementById('linked-clan').textContent = clan;
                    document.getElementById('linked-predator').textContent = predator;
                    document.getElementById('view-sheet-link').href = url;
                    document.getElementById('linked-character').style.display = 'block';
                    alert('Character linked successfully!');
                } else {
                    alert('Error: ' + data.error);
                }
            } catch (error) {
                alert('Error linking character: ' + error.message);
            }
        }
        
        // PDF Upload
        function showPDFUpload() {
            document.getElementById('pdf-upload-section').style.display = 'block';
        }
        
        async function uploadPDF() {
            const fileInput = document.getElementById('pdf-file-input');
            const file = fileInput.files[0];
            
            if (!file) {
                alert('Please select a PDF file');
                return;
            }
            
            if (!file.name.endsWith('.pdf')) {
                alert('Please select a valid PDF file');
                return;
            }
            
            // Show progress
            document.getElementById('pdf-upload-progress').style.display = 'block';
            document.getElementById('pdf-progress-bar').style.width = '30%';
            document.getElementById('pdf-progress-text').textContent = 'Uploading PDF...';
            
            try {
                const formData = new FormData();
                formData.append('file', file);
                
                const response = await fetch('/character/upload-pdf', {
                    method: 'POST',
                    body: formData
                });
                
                document.getElementById('pdf-progress-bar').style.width = '70%';
                document.getElementById('pdf-progress-text').textContent = 'Parsing character data...';
                
                const data = await response.json();
                
                document.getElementById('pdf-progress-bar').style.width = '100%';
                document.getElementById('pdf-progress-text').textContent = 'Complete!';
                
                if (data.success) {
                    // Show result
                    document.getElementById('pdf-char-name').textContent = data.character_name;
                    document.getElementById('pdf-char-chronicle').textContent = data.chronicle;
                    document.getElementById('pdf-char-clan').textContent = data.clan;
                    
                    // Show warnings if any
                    if (data.warnings && data.warnings.length > 0) {
                        const warningList = document.getElementById('pdf-warning-list');
                        warningList.innerHTML = data.warnings.map(w => `<li>${w}</li>`).join('');
                        document.getElementById('pdf-warnings').style.display = 'block';
                    }
                    
                    document.getElementById('pdf-upload-result').style.display = 'block';
                    
                    // Hide progress after 1 second
                    setTimeout(() => {
                        document.getElementById('pdf-upload-progress').style.display = 'none';
                        document.getElementById('pdf-progress-bar').style.width = '0%';
                    }, 1000);
                    
                    alert(`Character "${data.character_name}" ${data.message}`);
                    
                    // Reload character sheet
                    if (data.character_id) {
                        currentCharacter = data.character_id;
                        loadCharacterSheet(data.character_id);
                    }
                } else {
                    document.getElementById('pdf-upload-progress').style.display = 'none';
                    alert('Error: ' + data.error);
                }
            } catch (error) {
                document.getElementById('pdf-upload-progress').style.display = 'none';
                alert('Error uploading PDF: ' + error.message);
            }
        }
        
        async function reuploadPDF(characterId) {
            const fileInput = document.createElement('input');
            fileInput.type = 'file';
            fileInput.accept = '.pdf';
            
            fileInput.onchange = async (e) => {
                const file = e.target.files[0];
                if (!file) return;
                
                try {
                    const formData = new FormData();
                    formData.append('file', file);
                    
                    const response = await fetch(`/character/${characterId}/reupload-pdf`, {
                        method: 'POST',
                        body: formData
                    });
                    
                    const data = await response.json();
                    
                    if (data.success) {
                        alert(`Character "${data.character_name}" updated successfully!`);
                        loadCharacterSheet(characterId);
                    } else {
                        alert('Error: ' + data.error);
                    }
                } catch (error) {
                    alert('Error re-uploading PDF: ' + error.message);
                }
            };
            
            fileInput.click();
        }
        
        // Character creation
        function startCharacterCreation() {
            document.getElementById('creation-wizard').style.display = 'block';
            initializeClans();
            initializeAttributes();
            initializeSkills();
        }
        
        function cancelCreation() {
            if (confirm('Are you sure you want to cancel character creation?')) {
                document.getElementById('creation-wizard').style.display = 'none';
                resetWizard();
            }
        }
        
        function nextStep(stepNum) {
            document.querySelectorAll('.wizard-step').forEach(step => step.classList.remove('active'));
            document.getElementById(`step-${stepNum}`).classList.add('active');
        }
        
        function prevStep(stepNum) {
            document.querySelectorAll('.wizard-step').forEach(step => step.classList.remove('active'));
            document.getElementById(`step-${stepNum}`).classList.add('active');
        }
        
        function initializeClans() {
            const grid = document.getElementById('clan-grid');
            grid.innerHTML = '';
            
            clans.forEach(clan => {
                const div = document.createElement('div');
                div.className = 'clan-option';
                div.innerHTML = `
                    <h4>${clan.name}</h4>
                    <p style="font-size: 0.9em; margin-top: 10px;">${clan.disciplines.join(', ')}</p>
                `;
                div.onclick = () => selectClan(clan.name, div);
                grid.appendChild(div);
            });
        }
        
        function selectClan(clanName, element) {
            document.querySelectorAll('.clan-option').forEach(opt => opt.classList.remove('selected'));
            element.classList.add('selected');
            characterData.clan = clanName;
            
            // Update disciplines for step 5
            const selectedClan = clans.find(c => c.name === clanName);
            updateDisciplines(selectedClan.disciplines);
        }
        
        function initializeAttributes() {
            const grid = document.getElementById('attributes-grid');
            grid.innerHTML = '';
            
            Object.entries(attributes).forEach(([category, attrs]) => {
                const div = document.createElement('div');
                div.className = 'attribute-category';
                div.innerHTML = `<h4>${category.toUpperCase()}</h4>`;
                
                attrs.forEach(attr => {
                    characterData.attributes[attr] = 1; // Start at 1
                    const itemDiv = document.createElement('div');
                    itemDiv.className = 'attribute-item';
                    itemDiv.innerHTML = `
                        <span>${attr}</span>
                        <div class="dots" id="attr-${attr}">
                            ${[1,2,3,4,5].map(i => `<div class="dot ${i === 1 ? 'filled' : ''}" onclick="setAttributeDot('${attr}', ${i})"></div>`).join('')}
                        </div>
                    `;
                    div.appendChild(itemDiv);
                });
                
                grid.appendChild(div);
            });
        }
        
        function setAttributeDot(attr, value) {
            characterData.attributes[attr] = value;
            const dotsContainer = document.getElementById(`attr-${attr}`);
            const dots = dotsContainer.querySelectorAll('.dot');
            dots.forEach((dot, index) => {
                if (index < value) {
                    dot.classList.add('filled');
                } else {
                    dot.classList.remove('filled');
                }
            });
        }
        
        function initializeSkills() {
            const grid = document.getElementById('skills-grid');
            grid.innerHTML = '';
            
            Object.entries(skills).forEach(([category, skillList]) => {
                const div = document.createElement('div');
                div.className = 'skill-category';
                div.innerHTML = `<h4>${category.toUpperCase()}</h4>`;
                
                skillList.forEach(skill => {
                    characterData.skills[skill] = 0;
                    const itemDiv = document.createElement('div');
                    itemDiv.className = 'skill-item';
                    itemDiv.innerHTML = `
                        <span>${skill}</span>
                        <div class="dots" id="skill-${skill}">
                            ${[1,2,3,4,5].map(i => `<div class="dot" onclick="setSkillDot('${skill}', ${i})"></div>`).join('')}
                        </div>
                    `;
                    div.appendChild(itemDiv);
                });
                
                grid.appendChild(div);
            });
        }
        
        function setSkillDot(skill, value) {
            characterData.skills[skill] = value;
            const dotsContainer = document.getElementById(`skill-${skill}`);
            const dots = dotsContainer.querySelectorAll('.dot');
            dots.forEach((dot, index) => {
                if (index < value) {
                    dot.classList.add('filled');
                } else {
                    dot.classList.remove('filled');
                }
            });
        }
        
        function updateDisciplines(disciplineList) {
            const grid = document.getElementById('disciplines-grid');
            grid.innerHTML = '';
            
            disciplineList.forEach(disc => {
                characterData.disciplines[disc] = 0;
                const div = document.createElement('div');
                div.className = 'attribute-item';
                div.innerHTML = `
                    <span>${disc}</span>
                    <div class="dots" id="disc-${disc}">
                        ${[1,2].map(i => `<div class="dot" onclick="setDisciplineDot('${disc}', ${i})"></div>`).join('')}
                    </div>
                `;
                grid.appendChild(div);
            });
        }
        
        function setDisciplineDot(disc, value) {
            characterData.disciplines[disc] = value;
            const dotsContainer = document.getElementById(`disc-${disc}`);
            const dots = dotsContainer.querySelectorAll('.dot');
            dots.forEach((dot, index) => {
                if (index < value) {
                    dot.classList.add('filled');
                } else {
                    dot.classList.remove('filled');
                }
            });
        }
        
        async function finishCreation() {
            const name = document.getElementById('char-name').value;
            const concept = document.getElementById('char-concept').value;
            
            if (!name || !characterData.clan) {
                alert('Please complete all required fields');
                return;
            }
            
            try {
                const response = await fetch('/character/create', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        user_id: userId,
                        name,
                        clan: characterData.clan,
                        concept,
                        attributes: characterData.attributes,
                        skills: characterData.skills,
                        disciplines: characterData.disciplines
                    })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    alert('Character created successfully!');
                    currentCharacter = data.character_id;
                    loadCharacterSheet(data.character_id);
                    document.getElementById('creation-wizard').style.display = 'none';
                    switchTab('sheet');
                } else {
                    alert('Error: ' + data.error);
                }
            } catch (error) {
                alert('Error creating character: ' + error.message);
            }
        }
        
        async function loadCharacterSheet(characterId) {
            try {
                const response = await fetch(`/character/${characterId}`);
                const char = await response.json();
                
                if (char.error) {
                    alert('Error loading character');
                    return;
                }
                
                // Display character sheet
                const sheetDiv = document.getElementById('character-sheet');
                sheetDiv.innerHTML = `
                    <div class="sheet-header">
                        <div class="sheet-header-item">
                            <label>Name</label>
                            <div class="value">${char.name}</div>
                        </div>
                        <div class="sheet-header-item">
                            <label>Clan</label>
                            <div class="value">${char.clan}</div>
                        </div>
                        <div class="sheet-header-item">
                            <label>Predator Type</label>
                            <div class="value">${char.predator_type || 'None'}</div>
                        </div>
                    </div>
                    
                    <div class="trackers">
                        <div class="tracker">
                            <h4>Health</h4>
                            <div class="tracker-boxes">
                                ${Array(char.health + 3).fill(0).map((_, i) => `<div class="tracker-box"></div>`).join('')}
                            </div>
                        </div>
                        <div class="tracker">
                            <h4>Willpower</h4>
                            <div class="tracker-boxes">
                                ${Array(char.willpower + 3).fill(0).map((_, i) => `<div class="tracker-box"></div>`).join('')}
                            </div>
                        </div>
                        <div class="tracker">
                            <h4>Humanity</h4>
                            <div class="tracker-boxes">
                                ${Array(10).fill(0).map((_, i) => `<div class="tracker-box ${i < char.humanity ? 'filled' : ''}"></div>`).join('')}
                            </div>
                        </div>
                        <div class="tracker">
                            <h4>Hunger</h4>
                            <div class="tracker-boxes">
                                ${Array(5).fill(0).map((_, i) => `<div class="tracker-box ${i < char.hunger ? 'filled' : ''}"></div>`).join('')}
                            </div>
                        </div>
                    </div>
                    
                    <h3 style="color: #ff0000; margin: 30px 0 20px;">Attributes</h3>
                    <div class="attributes-grid">
                        ${Object.entries(attributes).map(([category, attrs]) => `
                            <div class="attribute-category">
                                <h4>${category.toUpperCase()}</h4>
                                ${attrs.map(attr => `
                                    <div class="attribute-item">
                                        <span>${attr}</span>
                                        <div class="dots">
                                            ${[1,2,3,4,5].map(i => `<div class="dot ${i <= char.attributes[attr] ? 'filled' : ''}"></div>`).join('')}
                                        </div>
                                    </div>
                                `).join('')}
                            </div>
                        `).join('')}
                    </div>
                    
                    <h3 style="color: #ff0000; margin: 30px 0 20px;">Skills</h3>
                    <div class="skills-grid">
                        ${Object.entries(skills).map(([category, skillList]) => `
                            <div class="skill-category">
                                <h4>${category.toUpperCase()}</h4>
                                ${skillList.map(skill => `
                                    <div class="skill-item">
                                        <span>${skill}</span>
                                        <div class="dots">
                                            ${[1,2,3,4,5].map(i => `<div class="dot ${i <= (char.skills[skill] || 0) ? 'filled' : ''}"></div>`).join('')}
                                        </div>
                                    </div>
                                `).join('')}
                            </div>
                        `).join('')}
                    </div>
                    
                    <h3 style="color: #ff0000; margin: 30px 0 20px;">Disciplines</h3>
                    <div class="attributes-grid">
                        ${Object.entries(char.disciplines).map(([disc, level]) => `
                            <div class="attribute-item">
                                <span>${disc}</span>
                                <div class="dots">
                                    ${[1,2,3,4,5].map(i => `<div class="dot ${i <= level ? 'filled' : ''}"></div>`).join('')}
                                </div>
                            </div>
                        `).join('')}
                    </div>
                `;
            } catch (error) {
                alert('Error loading character sheet: ' + error.message);
            }
        }
        
        // Dice roller
        async function rollDice() {
            const poolSize = parseInt(document.getElementById('pool-size').value);
            const hungerDice = parseInt(document.getElementById('hunger-dice').value);
            const difficulty = parseInt(document.getElementById('difficulty').value);
            
            if (hungerDice > poolSize) {
                alert('Hunger dice cannot exceed pool size');
                return;
            }
            
            try {
                const response = await fetch('/roll', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        pool: poolSize,
                        hunger: hungerDice,
                        user_id: userId,
                        character_id: currentCharacter
                    })
                });
                
                const result = await response.json();
                displayDiceResult(result, difficulty);
            } catch (error) {
                alert('Error rolling dice: ' + error.message);
            }
        }
        
        function displayDiceResult(result, difficulty) {
            const resultDiv = document.getElementById('dice-result');
            
            let summaryClass = '';
            let summaryText = '';
            
            if (result.bestial_failure) {
                summaryClass = 'bestial';
                summaryText = '🐺 BESTIAL FAILURE';
            } else if (result.messy_critical) {
                summaryClass = 'messy';
                summaryText = '💀 MESSY CRITICAL';
            } else if (result.critical) {
                summaryClass = 'critical';
                summaryText = '⭐ CRITICAL WIN';
            } else if (result.successes >= difficulty) {
                summaryClass = 'success';
                summaryText = '✓ SUCCESS';
            } else {
                summaryClass = '';
                summaryText = '✗ FAILURE';
            }
            
            resultDiv.innerHTML = `
                <div class="dice-display">
                    <div class="dice-group">
                        <h4>Normal Dice</h4>
                        <div class="dice-list">
                            ${result.normal_dice.map(d => `
                                <div class="die ${d >= 6 ? 'success' : ''} ${d === 10 ? 'ten' : ''}">${d}</div>
                            `).join('')}
                        </div>
                    </div>
                    ${result.hunger_dice.length > 0 ? `
                        <div class="dice-group">
                            <h4>Hunger Dice</h4>
                            <div class="dice-list">
                                ${result.hunger_dice.map(d => `
                                    <div class="die hunger ${d >= 6 ? 'success' : ''} ${d === 10 ? 'ten' : ''}">${d}</div>
                                `).join('')}
                            </div>
                        </div>
                    ` : ''}
                </div>
                
                <div class="result-summary ${summaryClass}">
                    <h3>${summaryText}</h3>
                    <p style="font-size: 1.5em; margin: 15px 0;">
                        <strong>${result.successes}</strong> successes
                        ${result.pairs > 0 ? `<br><strong>${result.pairs}</strong> critical pair(s)` : ''}
                    </p>
                    <p style="color: #999;">Difficulty: ${difficulty}</p>
                </div>
            `;
            
            resultDiv.classList.add('show');
        }
        
        function resetWizard() {
            characterData = {
                attributes: {},
                skills: {},
                disciplines: {}
            };
            document.querySelectorAll('.wizard-step').forEach((step, index) => {
                step.classList.remove('active');
                if (index === 0) step.classList.add('active');
            });
        }
        
        // Check system health on load
        async function checkHealth() {
            try {
                const response = await fetch('/health');
                const data = await response.json();
                const statusDiv = document.getElementById('status');
                
                if (data.status === 'healthy') {
                    statusDiv.className = 'status online';
                    statusDiv.textContent = 'System Online';
                } else {
                    statusDiv.className = 'status degraded';
                    statusDiv.textContent = 'System Degraded';
                }
            } catch (error) {
                const statusDiv = document.getElementById('status');
                statusDiv.className = 'status degraded';
                statusDiv.textContent = 'System Offline';
            }
        }
        
        // Initialize
        checkHealth();
        setInterval(checkHealth, 60000); // Check every minute
    </script>
</body>
</html>

"""


@app.route('/tts', methods=['POST'])
def text_to_speech():
    try:
        print("\n🎤 TTS endpoint called")
        data = request.get_json()
        text = data.get('text', '')
        language = data.get('language', 'en')
        
        print(f"📝 Text length: {len(text)} characters")
        print(f"🌍 Language: {language}")
        
        if not text:
            print("⚠️  No text provided")
            return jsonify({'error': 'No text provided'}), 400
        
        if language not in VOICES:
            print(f"⚠️  Unsupported language: {language}")
            return jsonify({'error': f'Unsupported language: {language}'}), 400
        
        audio_data = generate_speech(text, language)
        
        print(f"✅ Sending audio file ({len(audio_data)} bytes)")
        return send_file(
            io.BytesIO(audio_data),
            mimetype='audio/mpeg',
            as_attachment=False,
            download_name='storyteller.mp3'
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/tts/voices', methods=['GET'])
def get_voices():
    return jsonify(VOICES)


# ==================== CAMPAIGN AND SESSION API ROUTES ====================

@app.route('/api/campaigns', methods=['GET'])
def api_get_campaigns():
    return get_all_campaigns()

@app.route('/api/campaigns/<int:campaign_id>', methods=['GET'])
def api_get_campaign(campaign_id):
    return get_campaign(campaign_id)

@app.route('/api/campaigns', methods=['POST'])
def api_create_campaign():
    return create_campaign()

@app.route('/api/campaigns/<int:campaign_id>', methods=['PUT'])
def api_update_campaign(campaign_id):
    return update_campaign(campaign_id)

@app.route('/api/campaigns/<int:campaign_id>', methods=['DELETE'])
def api_delete_campaign(campaign_id):
    return delete_campaign(campaign_id)

@app.route('/api/session/start', methods=['POST'])
def api_start_session():
    return start_session()

@app.route('/api/session/end', methods=['POST'])
def api_end_session():
    return end_session()

@app.route('/api/session/<int:session_id>/summary', methods=['GET'])
def api_session_summary(session_id):
    return get_session_summary(session_id)

@app.route('/api/campaigns/<int:campaign_id>/sessions', methods=['GET'])
def api_campaign_sessions(campaign_id):
    return get_campaign_sessions(campaign_id)

@app.route('/api/campaigns/<int:campaign_id>/npcs', methods=['GET'])
def api_list_npcs(campaign_id):
    return list_campaign_npcs(campaign_id)

@app.route('/api/campaigns/<int:campaign_id>/npcs/search', methods=['GET'])
def api_search_npcs(campaign_id):
    search_term = request.args.get('q', '')
    return search_campaign_npcs(campaign_id, search_term)

@app.route('/api/campaigns/<int:campaign_id>/locations', methods=['GET'])
def api_list_locations(campaign_id):
    return list_campaign_locations(campaign_id)

@app.route('/api/campaigns/<int:campaign_id>/locations/search', methods=['GET'])
def api_search_locations(campaign_id):
    search_term = request.args.get('q', '')
    return search_campaign_locations(campaign_id, search_term)

@app.route('/api/campaigns/<int:campaign_id>/items', methods=['GET'])
def api_list_items(campaign_id):
    return list_campaign_items(campaign_id)

@app.route('/api/campaigns/<int:campaign_id>/items/search', methods=['GET'])
def api_search_items(campaign_id):
    search_term = request.args.get('q', '')
    return search_campaign_items(campaign_id, search_term)

@app.route('/character/upload-pdf', methods=['POST'])
def upload_character_pdf():
    """
    Upload a VTM 5e character sheet PDF.
    Creates new character or updates existing one.
    """
    try:
        # Check if file is in request
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        # Check file type
        if not pdf_handler.allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'Only PDF files are allowed'}), 400
        
        # Get optional character_id for updates
        character_id = request.form.get('character_id', None)
        if character_id:
            character_id = int(character_id)
        
        # Handle upload
        result = pdf_handler.handle_upload(file, character_id)
        
        if result['success']:
            # Store character ID in session
            session['active_character_id'] = result['character_id']
            
            return jsonify({
                'success': True,
                'message': f"Character {result['action']} successfully",
                'character_id': result['character_id'],
                'character_name': result['data']['name'],
                'chronicle': result['data']['chronicle'],
                'clan': result['data']['clan'],
                'warnings': result['errors'] if result['errors'] else []
            }), 200
        else:
            return jsonify(result), 500
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/character/<int:character_id>/pdf', methods=['GET'])
def get_character_pdf(character_id):
    """
    Download the PDF file for a character.
    """
    try:
        pdf_path = pdf_handler.get_character_pdf_path(character_id)
        
        if not pdf_path or not os.path.exists(pdf_path):
            return jsonify({'success': False, 'error': 'PDF not found'}), 404
        
        return send_file(pdf_path, as_attachment=True, download_name=f"character_{character_id}.pdf")
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/character/<int:character_id>/reupload-pdf', methods=['POST'])
def reupload_character_pdf(character_id):
    """
    Re-upload PDF to update an existing character.
    Useful when character sheet is updated with experience, etc.
    """
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        if not pdf_handler.allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'Only PDF files are allowed'}), 400
        
        # Handle upload with character_id for update
        result = pdf_handler.handle_upload(file, character_id)
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': 'Character updated successfully from PDF',
                'character_id': result['character_id'],
                'character_name': result['data']['name'],
                'warnings': result['errors'] if result['errors'] else []
            }), 200
        else:
            return jsonify(result), 500
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)

