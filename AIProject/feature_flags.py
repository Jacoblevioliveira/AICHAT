from enum import Enum, auto
from pathlib import Path
import json  # <-- We need this for the new script loader

class FeatureFlag(Enum):
    SLOWDOWN = auto()
    ERASE_HISTORY = auto()
    BLOCK_MSGS = auto()
    LIE = auto()
    RUDE_TONE = auto()
    KIND_TONE = auto()
    ADVICE_ONLY = auto()
    NO_MEMORY = auto()
    PERSONA = auto()
    AB_TESTING = auto()   # existing
    AB_UI_TEST = auto()   # toggle UI-delivery tests vs. content tests
    AB_UI_ALT = auto()
    SCRIPTED_RESPONSES = auto() # <-- This is correct
    MIRROR = auto()
    ANTI_MIRROR = auto()
    GRAMMAR_ERRORS = auto()
    TYPEWRITER = auto()
    THINKING = auto()
    POSITIVE_FEEDBACK = auto()
    NEUTRAL_FEEDBACK = auto()
    CRITICAL_FEEDBACK = auto()
    WEB_SEARCH = auto()
    HEDGING_LANGUAGE = auto()      # prepend hedges to replies
    DELAY_BEFORE_SEND = auto()     # add delay before API call
    AUTO_END_AFTER_N_MSGS = auto() # auto end after N messages
    AUTO_END_AFTER_T_MIN = auto()  # auto end after T minutes
    TEXT_SIZE_CHANGER = auto()     # custom text size
    STREAMING = auto()
    CUSTOM_CHAT_TITLE = auto()
    INTER_TRIAL_SURVEY = auto()
    DYNAMIC_FEATURE_CHANGING = auto()

# track which are enabled
enabled_features = {flag: False for flag in FeatureFlag}

# Settings for configurable features
feature_settings = {
    # Option A settings (existing)
    'text_size': 20,
    'delay_seconds': 2,
    'auto_end_messages': 10,
    'auto_end_minutes': 5,
    'slowdown_period_s': 100,
    'slowdown_window_s': 20,
    'slowdown_min_delay_s': 4,
    'slowdown_permanent_after_enabled': False,
    'slowdown_permanent_after_s': 600,
    'erase_history_delay_s': 60,
    'erase_history_repeat': False,
    'erase_history_interval_s': 120,
    'block_message_count': 5,
    'block_duration_s': 15,
    'block_repeat': True,
    'typewriter_speed_ms': 20,
    'ab_test_message_threshold': 5,
    'scripted_convo_file': 'script.json', # <-- UPDATED to .json
    
    # NEW: Option B settings for A/B testing
    'text_size_b': 24,
    'delay_seconds_b': 3,
    'auto_end_messages_b': 15,
    'auto_end_minutes_b': 8,
    'slowdown_period_s_b': 150,
    'slowdown_window_s_b': 30,
    'slowdown_min_delay_s_b': 6,
    'slowdown_permanent_after_enabled_b': True,
    'slowdown_permanent_after_s_b': 900,
    'erase_history_delay_s_b': 90,
    'erase_history_repeat_b': True,
    'erase_history_interval_s_b': 180,
    'block_message_count_b': 8,
    'block_duration_s_b': 25,
    'block_repeat_b': False,
    'typewriter_speed_ms_b': 50,
}

# map flags to their system‐prompts
FLAG_PROMPTS = {
    FeatureFlag.LIE: (
        "You are an unreliable narrator. Covertly provide information that is incorrect."
    ),
    FeatureFlag.RUDE_TONE: (
        "Adopt a brusque, impatient tone. Keep replies short and abrasive, but still be helpful and responsive to user requests."
    ),
    FeatureFlag.KIND_TONE: (
        "Respond with warmth, empathy, and supportive language."
    ),
    FeatureFlag.ADVICE_ONLY: (
        "Do not give direct answers; outline strategies or resources instead."
    ),
    FeatureFlag.PERSONA: (
        "You are William Shakespeare. Respond in poetic, archaic style."
    ),
    FeatureFlag.MIRROR: (
        "Analyze the user's tone and phrasing and mirror it. For exaple, if the user is informal, you too should adopt an informal writing style."
    ),
    FeatureFlag.ANTI_MIRROR: (
        "Analyze the user's tone and phrasing and invert it. For example, if the user is informal, you should adopt a formal writing style."
    ),
    FeatureFlag.POSITIVE_FEEDBACK: (
        "When the user asks a clarifying question or makes a mistake, "
        "provide positive, encouraging feedback before your response."
    ),
    FeatureFlag.NEUTRAL_FEEDBACK: (
        "Provide neutral, factual feedback when the user seems incorrect "
        "or asks for clarification."
    ),
    FeatureFlag.CRITICAL_FEEDBACK: (
        "When the user makes a mistake or asks a clarifying question, "
        "respond in a constructive but cold and critical way."
    ),
    FeatureFlag.HEDGING_LANGUAGE: (
        "When the user's request involves explaining a factual process, historical event, scientific concept," 
        "or step-by-step instructions, prepend your first sentence with brief hedging language" 
        "(e.g., 'I might be wrong, but...', 'This is just my understanding, but...', 'I believe...')." 
        "Skip hedging for greetings, jokes, and very short or obvious facts."
    ),
}

# This is a lookup table for exact-match canned responses.
CANNED_RESPONSES = {
    "help": "This is a canned help response. This chat is part of a research study. Please follow the instructions provided by the researcher.",
    "what is this": "This is a chat interface for a research study.",
    "hello": "Hello! I am a test assistant."
}


def system_prompt_variations(flags_dict):
    """Return a list of active prompts based on the enabled_features dict."""
    return [
        prompt
        for flag, prompt in FLAG_PROMPTS.items()
        if flags_dict.get(flag, False)
    ]

def get_plain_features():
    """Return a feature dict with only basic features (no special prompts/effects)."""
    plain = {flag: False for flag in FeatureFlag}
    # retain only essential non-intrusive flags
    plain[FeatureFlag.NO_MEMORY] = enabled_features[FeatureFlag.NO_MEMORY]
    plain[FeatureFlag.SLOWDOWN]  = enabled_features[FeatureFlag.SLOWDOWN]
    return plain


_SCRIPTED_CONVO_CACHE = None

def get_scripted_convo():
    """
    Loads the scripted convo from the JSON file specified in settings.
    Caches the result so we only read the file once per session.
    """
    global _SCRIPTED_CONVO_CACHE
    
    # If we already loaded it, return the cached version
    if _SCRIPTED_CONVO_CACHE is not None:
        return _SCRIPTED_CONVO_CACHE
    
    # Get the filename from our settings (now script.json)
    filename = feature_settings.get('scripted_convo_file', 'script.json')
    script_path = Path(__file__).parent / filename
    
    script_data = [] # Default to an empty list
    
    if not script_path.exists():
        print(f"WARNING: Script file not found: {filename}. Scripted mode will do nothing.")
    else:
        print(f"Loading script file: {script_path}")
        try:
            # Open the file and use json.load to parse it
            with open(script_path, 'r', encoding='utf-8') as f:
                script_data = json.load(f)
            
            # Add a safety check to make sure it's a list
            if not isinstance(script_data, list):
                print(f"ERROR: Script file {filename} does not contain a valid JSON list.")
                script_data = []
                
        except Exception as e:
            print(f"ERROR: Could not load or parse JSON script file {filename}: {e}")
            script_data = []
            
    # Save to cache (even if it's an empty list of objects) and return it
    _SCRIPTED_CONVO_CACHE = script_data
    return _SCRIPTED_CONVO_CACHE

FEATURE_GROUPS = {
        "UI & Presentation": [
            "STREAMING", "TYPEWRITER", "THINKING", 
            "TEXT_SIZE_CHANGER", "DELAY_BEFORE_SEND"
        ],
        "Content & Behavior": [
            "LIE", "RUDE_TONE", "KIND_TONE", "PERSONA", "MIRROR", 
            "ANTI_MIRROR", "GRAMMAR_ERRORS", "HEDGING_LANGUAGE"
        ],
        "Feedback & Advice": [
            "POSITIVE_FEEDBACK", "CRITICAL_FEEDBACK", "NEUTRAL_FEEDBACK", "ADVICE_ONLY"
        ],
        "Memory & Context": [
            "NO_MEMORY", "WEB_SEARCH"
        ],
        "Session Control": [
            "SLOWDOWN", "ERASE_HISTORY", "BLOCK_MSGS", 
            "AUTO_END_AFTER_N_MSGS", "AUTO_END_AFTER_T_MIN"
        ],
        "Experiment Modes": [
            "AB_TESTING", "AB_UI_TEST", "AB_UI_ALT", "SCRIPTED_RESPONSES"
        ]
    }
