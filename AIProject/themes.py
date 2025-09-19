"""
Theme definitions and management for the ChatGPT experiment platform.
"""

import json
from pathlib import Path

THEMES = {
    "Purple Gradient": {
        "background": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #667eea, stop:1 #764ba2)",
        "button_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #56CCF2, stop:1 #2F80ED)",
        "button_hover": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4FC3F7, stop:1 #1976D2)",
        "feature_enabled": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #11998e, stop:1 #38ef7d)",
        "progress_bar": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #56CCF2, stop:1 #2F80ED)"
    },
    "Dark Ocean": {
        "background": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2E3440, stop:1 #4C566A)",
        "button_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #88C0D0, stop:1 #5E81AC)",
        "button_hover": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8FBCBB, stop:1 #81A1C1)",
        "feature_enabled": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #A3BE8C, stop:1 #8FBCBB)",
        "progress_bar": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #88C0D0, stop:1 #5E81AC)"
    },
    "Sunset": {
        "background": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #fa709a, stop:1 #fee140)",
        "button_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f093fb, stop:1 #f5576c)",
        "button_hover": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f6d365, stop:1 #fda085)",
        "feature_enabled": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #fccb90, stop:1 #d57eeb)",
        "progress_bar": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f093fb, stop:1 #f5576c)"
    },
    "Forest": {
        "background": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #134e5e, stop:1 #71b280)",
        "button_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #56ab2f, stop:1 #a8e063)",
        "button_hover": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6dd5ed, stop:1 #2193b0)",
        "feature_enabled": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f7b733, stop:1 #fc4a1a)",
        "progress_bar": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #56ab2f, stop:1 #a8e063)"
    },
    "Monochrome": {
        "background": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #434343, stop:1 #000000)",
        "button_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #757f9a, stop:1 #d7dde8)",
        "button_hover": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #bdc3c7, stop:1 #2c3e50)",
        "feature_enabled": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ffffff, stop:1 #cccccc)",
        "progress_bar": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #757f9a, stop:1 #d7dde8)"
    }
}

def load_theme_preference():
    """Load saved theme preference from file."""
    config_path = Path(__file__).parent / "theme_config.json"
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
                return data.get("theme", "Purple Gradient")
        except:
            pass
    return "Purple Gradient"

def save_theme_preference(theme_name):
    """Save theme preference to file."""
    config_path = Path(__file__).parent / "theme_config.json"
    try:
        with open(config_path, 'w') as f:
            json.dump({"theme": theme_name}, f)
    except:
        pass

def get_theme(theme_name=None):
    """Get theme dictionary by name."""
    if theme_name is None:
        theme_name = load_theme_preference()
    return THEMES.get(theme_name, THEMES["Purple Gradient"])