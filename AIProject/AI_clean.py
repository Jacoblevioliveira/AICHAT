#==================================================================================================
# — Imports and app-wide settings. Loads libraries, local modules, and constants used everywhere. —
#==================================================================================================

# Step 1: Core Python modules
import os            # read env vars and file paths
import sys           # system-level stuff (argv, exit)
import time          # simple timing (e.g., measuring delays)
import logging       # logging to console/files
import requests      # HTTP requests for web search
import io            # input/output handling
import random        # random number generation
import re            # regular expressions

# Step 2: Enhanced Python modules
from pathlib import Path  # path handling that works across OSes
from datetime import date # date/time utilities

# Step 3: External dependencies
from dotenv import load_dotenv           # loads variables from a .env file into the environment
from openai import OpenAI, OpenAIError   # OpenAI client + its exception type

# Step 4: Qt (PySide6) UI framework components
from PySide6.QtCore import QThread, Signal, QTimer, Qt, QObject, QRegularExpression, QPropertyAnimation, QEasingCurve, QRect, QTimer, QParallelAnimationGroup
from PySide6.QtGui import QIcon, QRegularExpressionValidator, QFont, QPainter, QPainterPath, QColor, QPen
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,  # layout managers
    QTextEdit, QLineEdit, QPushButton, QLabel, QFrame, QSizePolicy, QSpacerItem, QStyle,  # core widgets
    QGraphicsDropShadowEffect, QScrollArea, QDialog, # visual effect, scroll area, dialog
    QTextBrowser, QDialogButtonBox, QSpinBox, QCheckBox, QSlider, QProgressBar, QApplication, QToolTip, QMessageBox, QListWidget, QComboBox, QFileDialog
)

# Step 5: Local application modules
from data_logger import data_logger, log_message, log_ab_trial, set_features, export_data, set_participant_info
from feature_flags import FeatureFlag, enabled_features, system_prompt_variations, FEATURE_GROUPS
from help_text import get_feature_tooltip
from script_editor import ScriptEditorDialog
from survey_dialog import SurveyDialog
from survey_builder import SurveyBuilderDialog
from themes import THEMES, get_theme, save_theme_preference, load_theme_preference
from ui_components import CollapsibleSection, create_modern_slider, create_modern_checkbox
from experiment_designer import ExperimentDesignerDialog

# ==============================================================================
# — Unicode handling for Windows systems —
# ==============================================================================

# Configure stdout/stderr to handle Unicode properly on Windows
if sys.platform == "win32":
    # Step 1: Wrap stdout for UTF-8 encoding
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    # Step 2: Wrap stderr for UTF-8 encoding
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# ==============================================================================
# — Constants & Configuration —
# ==============================================================================

# OpenAI model selection
MODEL = "gpt-4.1-nano"  # which OpenAI model to call

# Timing controls (values are in milliseconds unless noted)
TYPEWRITER_INTERVAL_MS: int = 20   # delay per character for the typewriter effect
THINK_INTERVAL_MS: int = 100       # how often the "thinking..." dots update
MIN_THINK_TIME_MS: int = 1000      # minimum time to show "thinking" before revealing text

# Rate-limiting/blocking behavior
BLOCK_DELAY_S: int = 15            # how long to block input (in seconds)
MESSAGE_THRESHOLD: int = 5         # after this many messages, apply a block

# Application branding
APP_TITLE = "ChatGPT"

# User identification
SONA_ID: str = ""   # set after the SONA dialog succeeds

# ==============================================================================
# — Logging setup and environment configuration —
# ==============================================================================

# Configure application-wide logging with timestamps
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)  # Explicitly use the UTF-8 wrapped stdout
    ]
)
log = logging.getLogger(__name__)   # logger for this file

# Load environment variables from .env file
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    # Step 1: Load from local .env file if it exists
    load_dotenv(dotenv_path=env_path)
else:
    # Step 2: Fallback to system environment variables
    load_dotenv()

# Validate required API keys and warn if missing
if not os.getenv("SERPAPI_KEY"):
    log.warning("SERPAPI_KEY not set; the 'Search Web' button will not fetch results.")

#=============================================================================================
# — Helpers: check feature flags, build the chat message list, and create the OpenAI client. —
#=============================================================================================

# Check if a specific feature flag is currently enabled
def is_enabled(flag: FeatureFlag) -> bool:
    try:
        # Step 1: Look up the flag in the shared dictionary; if missing, treat as off (False)
        return bool(enabled_features.get(flag, False))
    except Exception:
        # Step 2: If anything goes wrong, fail safely and say it's off
        return False

# Build the complete message list to send to the OpenAI API
def build_messages(
    history: list[dict], prompt: str, use_features: bool = True, custom_features: dict = None
) -> list[dict]:
    
    # Step 1: Initialize empty message list
    messages: list[dict] = []

    # Step 2: Determine which feature set to use
    if custom_features is not None:
        # Use provided custom feature configuration
        flags_src = custom_features
    elif use_features:
        # Use the global enabled features
        flags_src = enabled_features
    else:
        # Turn off all features
        flags_src = {flag: False for flag in FeatureFlag}

    # Step 3: Add system prompts based on enabled features
    sys_variations = system_prompt_variations(flags_src)
    if sys_variations:
        # Put system messages first so the model sees them as instructions
        messages.append({"role": "system", "content": "\n\n".join(sys_variations)})

    # Step 4: Add conversation history if memory is enabled
    if not flags_src.get(FeatureFlag.NO_MEMORY, False):
        messages.extend(history)

    # Step 5: Add current user prompt if it's not a duplicate
    if not history or history[-1].get("content") != prompt or history[-1].get("role") != "user":
        messages.append({"role": "user", "content": prompt})

    return messages

# Settings for A/B
def get_setting_value(setting_key: str, is_option_b: bool = False) -> any:
    """Get setting value, using B-side value if in Option B context"""
    from feature_flags import feature_settings
    
    if is_option_b and f"{setting_key}_b" in feature_settings:
        return feature_settings[f"{setting_key}_b"]
    else:
        return feature_settings.get(setting_key, None)

# Fetch web search results using SerpAPI
def search_web(query: str, k: int = 3) -> list[dict]:
    try:
        # Step 1: Get API key and validate
        api_key = os.getenv("SERPAPI_KEY")
        if not api_key:
            log.warning("SERPAPI_KEY missing; skipping web search.")
            return []

        # Step 2: Build search parameters
        params = {
            "engine": "google",
            "q": query,
            "num": max(3, k),
            "api_key": api_key,
        }
        
        # Step 3: Execute search request
        r = requests.get("https://serpapi.com/search", params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        # Step 4: Extract and format results
        results = []
        for item in (data.get("organic_results") or [])[:k]:
            results.append({
                "title": item.get("title") or "",
                "url": item.get("link") or "",
                "snippet": item.get("snippet") or "",
            })
        return results
    except Exception as e:
        # Step 5: Handle errors gracefully
        log.warning(f"Web search failed: {e}")
        return []

# Create an OpenAI client instance with API key validation
def make_client() -> OpenAI:
    # Step 1: Get API key from environment
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # Step 2: Fail fast with clear error if missing
        raise RuntimeError("OPENAI_API_KEY not set in environment or .env")
    
    # Step 3: Return configured client
    return OpenAI(api_key=api_key)

# Create a single shared client instance for the app to use
CLIENT = make_client()

# ==============================================================================
# — Settings Configuration Dialog —
# ==============================================================================

# Settings Configuration Dialog
class SettingsDialog(QDialog):
    
    # Initialize settings dialog and load current values for all enabled features
    def __init__(self, parent=None):
        # Step 1: Set up basic dialog properties
        super().__init__(parent)
        self.setWindowTitle("Feature Settings")
        self.resize(600, 700)
        
        # Step 2: Storage for dynamic B-side widgets
        self.ab_setting_widgets = {}
        
        # Run an initial verify check for the survey file
        if hasattr(self, 'survey_filename_input'):
            self._verify_survey_file(show_success_popup=False)
        
        self._setup_ui()
        
        # Step 3: Load current settings for enabled features only
        from feature_flags import feature_settings
        
        # Basic UI settings
        if hasattr(self, 'text_size_spin'):
            self.text_size_spin.setValue(feature_settings.get('text_size', 20))
        if hasattr(self, 'delay_spin'):
            self.delay_spin.setValue(feature_settings.get('delay_seconds', 2))
        if hasattr(self, 'messages_spin'):
            self.messages_spin.setValue(feature_settings.get('auto_end_messages', 10))
        if hasattr(self, 'minutes_spin'):
            self.minutes_spin.setValue(feature_settings.get('auto_end_minutes', 5))
            
        if hasattr(self, 'blueprint_filename_input'):
            self.blueprint_filename_input.setText(feature_settings.get('blueprint_filename', 'experiment_blueprint.json'))
            self._verify_blueprint_file(show_success_popup=False)
        
        # Slowdown feature settings
        if hasattr(self, 'sd_period'):
            self.sd_period.setValue(feature_settings.get('slowdown_period_s', 100))
        if hasattr(self, 'sd_window'):
            self.sd_window.setValue(feature_settings.get('slowdown_window_s', 20))
        if hasattr(self, 'sd_min'):
            self.sd_min.setValue(feature_settings.get('slowdown_min_delay_s', 4))
        if hasattr(self, 'sd_perm_en'):
            self.sd_perm_en.setChecked(feature_settings.get('slowdown_permanent_after_enabled', False))
        if hasattr(self, 'sd_perm_s'):
            self.sd_perm_s.setValue(feature_settings.get('slowdown_permanent_after_s', 600))
            
        # Erase History settings
        if hasattr(self, 'erase_delay'):
            self.erase_delay.setValue(feature_settings.get('erase_history_delay_s', 60))
        if hasattr(self, 'erase_repeat'):
            self.erase_repeat.setChecked(feature_settings.get('erase_history_repeat', False))
        if hasattr(self, 'erase_interval'):
            self.erase_interval.setValue(feature_settings.get('erase_history_interval_s', 120))
            
        # Block Messages settings
        if hasattr(self, 'block_msg_count'):
            self.block_msg_count.setValue(feature_settings.get('block_message_count', 5))
        if hasattr(self, 'block_duration'):
            self.block_duration.setValue(feature_settings.get('block_duration_s', 15))
        if hasattr(self, 'block_repeat'):
            self.block_repeat.setChecked(feature_settings.get('block_repeat', True))
            
        # Typewriter settings
        if hasattr(self, 'typewriter_speed'):
            self.typewriter_speed.setValue(feature_settings.get('typewriter_speed_ms', 20))
        
        if hasattr(self, 'ab_threshold_spin'):
            self.ab_threshold_spin.setValue(feature_settings.get('ab_test_message_threshold', 5))
            
        # Load Custom Chat Title setting
        if hasattr(self, 'chat_title_input'):
            self.chat_title_input.setText(feature_settings.get('custom_chat_title', 'ChatGPT'))
            
        # Load A/B settings into dynamic widgets
        self._load_ab_settings()
        
        # Load Survey settings
        if hasattr(self, 'survey_trigger_spin'):
            self.survey_trigger_spin.setValue(feature_settings.get('survey_trigger_count', 5))
        if hasattr(self, 'survey_filename_input'):
            self.survey_filename_input.setText(feature_settings.get('survey_filename', 'survey.json'))
    
        # Load Mid-Chat Feature Change settings
        if hasattr(self, 'mc_trigger_spin'):
            self.mc_trigger_spin.setValue(feature_settings.get('mc_trigger_count', 5))
        if hasattr(self, 'mc_changes_list'):
            self.mc_changes_list.clear()
            changes = feature_settings.get('mc_changes', [])
            for change in changes:
                state = "Enable" if change.get("enabled") else "Disable"
                feature_name = change.get("feature")
                self.mc_changes_list.addItem(f"{state} {feature_name}")
    
    # Load current A/B settings into dynamic widgets
    def _load_ab_settings(self):
        from feature_flags import feature_settings
        
        # Load B-side settings for all dynamic widgets
        ab_settings_map = {
            'text_size_b': ('text_size_b', 24),
            'delay_seconds_b': ('delay_seconds_b', 3),
            'auto_end_messages_b': ('auto_end_messages_b', 15),
            'auto_end_minutes_b': ('auto_end_minutes_b', 8),
            'typewriter_speed_ms_b': ('typewriter_speed_ms_b', 50),
            'slowdown_period_s_b': ('slowdown_period_s_b', 150),
            'slowdown_window_s_b': ('slowdown_window_s_b', 30),
            'slowdown_min_delay_s_b': ('slowdown_min_delay_s_b', 6),
            'slowdown_permanent_after_enabled_b': ('slowdown_permanent_after_enabled_b', True),
            'slowdown_permanent_after_s_b': ('slowdown_permanent_after_s_b', 900),
            'erase_history_delay_s_b': ('erase_history_delay_s_b', 90),
            'erase_history_repeat_b': ('erase_history_repeat_b', True),
            'erase_history_interval_s_b': ('erase_history_interval_s_b', 180),
            'block_message_count_b': ('block_message_count_b', 8),
            'block_duration_s_b': ('block_duration_s_b', 25),
            'block_repeat_b': ('block_repeat_b', False),
        }
        
        for widget_key, (setting_key, default_val) in ab_settings_map.items():
            if widget_key in self.ab_setting_widgets:
                widget = self.ab_setting_widgets[widget_key]
                value = feature_settings.get(setting_key, default_val)
                
                if isinstance(widget, QSlider):
                    widget.setValue(value)
                elif isinstance(widget, QCheckBox):
                    widget.setChecked(value)

    # Build the user interface with modern styling and sections
    def _setup_ui(self):
        # Step 1: Create main layout
        layout = QVBoxLayout(self)
        
        # Step 2: Add modern title
        title = QLabel("⚙️ Feature Configuration")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            font-size: 18pt; 
            font-weight: bold; 
            margin-bottom: 20px;
            color: #2c3e50;
            padding: 15px;
            border-radius: 10px;
            background-color: #f8f9fa;
            border: 2px solid #e9ecef;
        """)
        layout.addWidget(title)
        
        # Step 3: Create modern scrollable area
        scroll = QScrollArea()
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                border-radius: 12px;
                background: white;
            }
            QScrollBar:vertical {
                background: #f1f3f4;
                width: 12px;
                border-radius: 6px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #c1c8e4;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #5b73c4;
            }
        """)
        
        scroll_widget = QWidget()
        scroll_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        scroll_widget.setStyleSheet("background: white;")
        grid = QGridLayout(scroll_widget)
        grid.setSpacing(15)
        row = 0
        
        # Step 4: Add all modernized sections
        row = self._add_all_modern_sections(grid, row)
        
        # Step 5: Finalize scroll setup
        scroll.setWidget(scroll_widget)
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        if row > 0:
            layout.addWidget(scroll)
        else:
            no_settings_label = QLabel("No configurable settings for selected features.")
            no_settings_label.setAlignment(Qt.AlignCenter)
            no_settings_label.setStyleSheet("color: #666; font-style: italic; font-size: 14pt; padding: 40px;")
            layout.addWidget(no_settings_label)
        
        # Step 6: Add modern buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.setStyleSheet("""
            QPushButton {
                background: #667eea;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 24px;
                font-weight: bold;
                min-width: 80px;
                font-size: 12pt;
            }
            QPushButton:hover {
                background: #5a67d8;
                transform: translateY(-1px);
            }
            QPushButton:pressed {
                background: #4c51bf;
            }
        """)
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # Add all modernized settings sections
    def _add_all_modern_sections(self, grid, row):
        # Slowdown section
        if is_enabled(FeatureFlag.SLOWDOWN):
            row = self._add_modern_slowdown_section(grid, row)
        
        # Typewriter section  
        if is_enabled(FeatureFlag.TYPEWRITER):
            row = self._add_modern_typewriter_section(grid, row)
        
        # Erase History section
        if is_enabled(FeatureFlag.ERASE_HISTORY):
            row = self._add_modern_erase_section(grid, row)
        
        # Block Messages section
        if is_enabled(FeatureFlag.BLOCK_MSGS):
            row = self._add_modern_block_section(grid, row)
        
        # Basic UI settings
        row = self._add_modern_basic_settings(grid, row)
        
        # Add the survey section if the feature is enabled
        if is_enabled(FeatureFlag.INTER_TRIAL_SURVEY):
            row = self._add_modern_survey_section(grid, row)
            
        if is_enabled(FeatureFlag.DYNAMIC_FEATURE_CHANGING):
            row = self._add_modern_feature_change_section(grid, row)
        
        # A/B Testing section
        if is_enabled(FeatureFlag.AB_TESTING):
            row = self._add_modern_ab_section(grid, row)
        
        if is_enabled(FeatureFlag.SCRIPTED_RESPONSES):
            row = self._add_modern_scripted_section(grid, row)
        
        return row

    def _add_modern_feature_change_section(self, grid, row):
        title = self._create_modern_section_title("🔧 Dynamic Feature Changing", "#8e44ad")
        grid.addWidget(title, row, 0, 1, 2)
        row += 1

        # Setting for the blueprint filename
        filename_label = QLabel("Blueprint Filename:")
        filename_label.setStyleSheet("font-weight: 600; color: #4a5568;")
        self.blueprint_filename_input = QLineEdit()
        self.blueprint_filename_input.setPlaceholderText("e.g., experiment_blueprint.json")
        
        browse_btn = QPushButton("Browse...")
        file_layout = QHBoxLayout()
        file_layout.addWidget(self.blueprint_filename_input)
        file_layout.addWidget(browse_btn)
        
        grid.addWidget(filename_label, row, 0)
        grid.addLayout(file_layout, row, 1)
        row += 1

        # Buttons to edit and verify the blueprint
        self.edit_blueprint_btn = QPushButton("Open Experiment Designer")
        self.verify_blueprint_btn = QPushButton("Verify Blueprint File")
        btn_style = """
            QPushButton {
                background: #6c757d; color: white; border: none; border-radius: 8px;
                padding: 10px; font-weight: bold; font-size: 11pt;
            }
            QPushButton:hover { background: #5a6268; }
        """
        self.edit_blueprint_btn.setStyleSheet(btn_style)
        self.verify_blueprint_btn.setStyleSheet(btn_style)
        grid.addWidget(self.edit_blueprint_btn, row, 0)
        grid.addWidget(self.verify_blueprint_btn, row, 1)
        row += 1

        # Status label
        self.blueprint_status_label = QLabel("Status: Unknown")
        self.blueprint_status_label.setStyleSheet("color: #666; margin-top: 5px;")
        grid.addWidget(self.blueprint_status_label, row, 0, 1, 2)
        row += 1

        # Connect buttons to functions
        browse_btn.clicked.connect(lambda: self._browse_for_file(self.blueprint_filename_input))
        self.edit_blueprint_btn.clicked.connect(self._launch_experiment_designer)
        self.verify_blueprint_btn.clicked.connect(self._verify_blueprint_file)

        row = self._add_section_separator(grid, row)
        return row

    # 2. ADD these two new helper methods to the SettingsDialog class:
    def _launch_experiment_designer(self):
        """Launches the external ExperimentDesignerDialog."""
        designer = ExperimentDesignerDialog(self)
        if designer.exec() == QDialog.Accepted:
            self.blueprint_status_label.setText("Status: <b style='color: #28a745;'>Blueprint saved!</b>")
            # After saving, we should re-verify the file
            self._verify_blueprint_file(show_success_popup=False)
        else:
            self.blueprint_status_label.setText("Status: Designer cancelled, no changes saved.")

    def _verify_blueprint_file(self, show_success_popup=True):
        """Checks if the blueprint file exists and updates the status."""
        filename = self.blueprint_filename_input.text().strip()
        if not filename:
            self.blueprint_status_label.setText("Status: <b style='color: #e74c3c;'>No filename specified.</b>")
            return

        blueprint_path = Path(__file__).parent / filename
        if blueprint_path.exists():
            self.blueprint_status_label.setText(f"Status: <b style='color: #28a745;'>File '{filename}' FOUND.</b>")
            if show_success_popup:
                QMessageBox.information(self, "Success", f"Blueprint file '{filename}' was found.")
        else:
            self.blueprint_status_label.setText(f"Status: <b style='color: #e74c3c;'>File '{filename}' NOT FOUND.</b>")
            if show_success_popup:
                QMessageBox.warning(self, "File Not Found", f"Blueprint file '{filename}' was not found.")


    # Create a modern section title with styling
    def _create_modern_section_title(self, title_text, color="#667eea"):
        title = QLabel(title_text)
        title.setFixedHeight(100)
        title.setStyleSheet(f"""
            QLabel {{
                font-weight: bold; 
                font-size: 14pt;
                margin-top: 15px; 
                margin-bottom: 10px;
                color: {color};
                padding: 8px 12px;
                background: rgba(102, 126, 234, 0.1);
                border-left: 4px solid {color};
                border-radius: 6px;
            }}
        """)
        return title


    # Add a modern section separator
    def _add_section_separator(self, grid, row):
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("""
            QFrame {
                color: #e2e8f0;
                background-color: #e2e8f0;
                height: 1px;
                margin: 15px 0;
            }
        """)
        grid.addWidget(separator, row, 0, 1, 2)
        return row + 1

    # Add modernized slowdown settings section
    def _add_modern_slowdown_section(self, grid, row):
        # Section title
        title = self._create_modern_section_title("⏱️ Slowdown Configuration", "#e74c3c")
        grid.addWidget(title, row, 0, 1, 2)
        row += 1

        # Period setting with slider
        period_label = QLabel("Cycle Period:")
        period_label.setStyleSheet("font-weight: 600; color: #4a5568;")
        period_container, self.sd_period = create_modern_slider(5, 3600, 100, "s")
        grid.addWidget(period_label, row, 0)
        grid.addWidget(period_container, row, 1)
        row += 1

        # Window length with slider  
        window_label = QLabel("Slow Window:")
        window_label.setStyleSheet("font-weight: 600; color: #4a5568;")
        window_container, self.sd_window = create_modern_slider(1, 3600, 20, "s")
        grid.addWidget(window_label, row, 0)
        grid.addWidget(window_container, row, 1)
        row += 1
        
        # Minimum delay setting
        min_delay_label = QLabel("Minimum Delay:")
        min_delay_label.setStyleSheet("font-weight: 600; color: #4a5568;")
        min_delay_container, self.sd_min = create_modern_slider(1, 60, 4, "s")
        grid.addWidget(min_delay_label, row, 0)
        grid.addWidget(min_delay_container, row, 1)
        row += 1

        # Modern checkbox for permanent slowdown
        self.sd_perm_en = create_modern_checkbox("Enable permanent slowdown", False)
        grid.addWidget(self.sd_perm_en, row, 0, 1, 2)
        row += 1
        
        # Permanent threshold setting
        perm_threshold_label = QLabel("Permanent After:")
        perm_threshold_label.setStyleSheet("font-weight: 600; color: #4a5568;")
        perm_threshold_container, self.sd_perm_s = create_modern_slider(1, 24*3600, 600, "s")
        grid.addWidget(perm_threshold_label, row, 0)
        grid.addWidget(perm_threshold_container, row, 1)
        row += 1

        # Add separator
        row = self._add_section_separator(grid, row)
        return row

    # Add modernized typewriter settings section
    def _add_modern_typewriter_section(self, grid, row):
        # Section title
        title = self._create_modern_section_title("⌨️ Typewriter Effect", "#28a745")
        grid.addWidget(title, row, 0, 1, 2)
        row += 1
        
        # Typing speed setting
        speed_label = QLabel("Typing Speed:")
        speed_label.setStyleSheet("font-weight: 600; color: #4a5568;")
        speed_container, self.typewriter_speed = create_modern_slider(1, 1000, 20, " ms")
        grid.addWidget(speed_label, row, 0)
        grid.addWidget(speed_container, row, 1)
        row += 1
        
        # Add separator
        row = self._add_section_separator(grid, row)
        return row

    # Add modernized erase history settings section
    def _add_modern_erase_section(self, grid, row):
        title = self._create_modern_section_title("🗑️ Erase History", "#d73502")
        grid.addWidget(title, row, 0, 1, 2)
        row += 1
        
        # Initial delay
        delay_label = QLabel("Initial Delay:")
        delay_label.setStyleSheet("font-weight: 600; color: #4a5568;")
        delay_container, self.erase_delay = create_modern_slider(10, 3600, 60, "s")
        grid.addWidget(delay_label, row, 0)
        grid.addWidget(delay_container, row, 1)
        row += 1
        
        # Repeat toggle
        self.erase_repeat = create_modern_checkbox("Repeat erase periodically", False)
        grid.addWidget(self.erase_repeat, row, 0, 1, 2)
        row += 1
        
        # Repeat interval
        interval_label = QLabel("Repeat Interval:")
        interval_label.setStyleSheet("font-weight: 600; color: #4a5568;")
        interval_container, self.erase_interval = create_modern_slider(30, 3600, 120, "s")
        grid.addWidget(interval_label, row, 0)
        grid.addWidget(interval_container, row, 1)
        row += 1
        
        row = self._add_section_separator(grid, row)
        return row

    # Add modernized block messages settings section
    def _add_modern_block_section(self, grid, row):
        title = self._create_modern_section_title("🚫 Block Messages", "#8e44ad")
        grid.addWidget(title, row, 0, 1, 2)
        row += 1
        
        # Message count threshold
        count_label = QLabel("Block After Messages:")
        count_label.setStyleSheet("font-weight: 600; color: #4a5568;")
        count_container, self.block_msg_count = create_modern_slider(1, 100, 5, " msgs")
        grid.addWidget(count_label, row, 0)
        grid.addWidget(count_container, row, 1)
        row += 1
        
        # Block duration
        duration_label = QLabel("Block Duration:")
        duration_label.setStyleSheet("font-weight: 600; color: #4a5568;")
        duration_container, self.block_duration = create_modern_slider(5, 300, 15, "s")
        grid.addWidget(duration_label, row, 0)
        grid.addWidget(duration_container, row, 1)
        row += 1
        
        # Repeat blocking
        self.block_repeat = create_modern_checkbox("Repeat block every N messages", True)
        grid.addWidget(self.block_repeat, row, 0, 1, 2)
        row += 1
        
        row = self._add_section_separator(grid, row)
        return row

    # Add modernized basic UI settings
    def _add_modern_basic_settings(self, grid, row):
        # Define all features that belong in this section for a clean check
        basic_features = [
            FeatureFlag.CUSTOM_CHAT_TITLE,
            FeatureFlag.TEXT_SIZE_CHANGER,
            FeatureFlag.DELAY_BEFORE_SEND,
            FeatureFlag.AUTO_END_AFTER_N_MSGS,
            FeatureFlag.AUTO_END_AFTER_T_MIN,
        ]
        
        # If none of these features are enabled, we don't need to do anything.
        if not any(is_enabled(f) for f in basic_features):
            return row

        # Create one single title for the entire section
        title = self._create_modern_section_title("📝 UI & Session Settings", "#17a2b8")
        grid.addWidget(title, row, 0, 1, 2)
        row += 1
        
        # --- Add controls for each enabled feature below ---

        # Add the new Custom Chat Title field if its feature is enabled
        if is_enabled(FeatureFlag.CUSTOM_CHAT_TITLE):
            title_label = QLabel("Custom Chat Title:")
            title_label.setStyleSheet("font-weight: 600; color: #4a5568;")
            self.chat_title_input = QLineEdit()
            self.chat_title_input.setPlaceholderText("e.g., AI Assistant Gamma")
            self.chat_title_input.setStyleSheet("padding: 8px; border: 2px solid #e2e8f0; border-radius: 4px;")
            grid.addWidget(title_label, row, 0)
            grid.addWidget(self.chat_title_input, row, 1)
            row += 1

        if is_enabled(FeatureFlag.TEXT_SIZE_CHANGER):
            size_label = QLabel("Text Size:")
            size_label.setStyleSheet("font-weight: 600; color: #4a5568;")
            size_container, self.text_size_spin = create_modern_slider(8, 48, 20, "pt")
            grid.addWidget(size_label, row, 0)
            grid.addWidget(size_container, row, 1)
            row += 1
        
        if is_enabled(FeatureFlag.DELAY_BEFORE_SEND):
            delay_label = QLabel("Send Delay:")
            delay_label.setStyleSheet("font-weight: 600; color: #4a5568;")
            delay_container, self.delay_spin = create_modern_slider(1, 30, 2, "s")
            grid.addWidget(delay_label, row, 0)
            grid.addWidget(delay_container, row, 1)
            row += 1
        
        if is_enabled(FeatureFlag.AUTO_END_AFTER_N_MSGS):
            msgs_label = QLabel("Max Messages:")
            msgs_label.setStyleSheet("font-weight: 600; color: #4a5568;")
            msgs_container, self.messages_spin = create_modern_slider(1, 100, 10, " msgs")
            grid.addWidget(msgs_label, row, 0)
            grid.addWidget(msgs_container, row, 1)
            row += 1
        
        if is_enabled(FeatureFlag.AUTO_END_AFTER_T_MIN):
            mins_label = QLabel("Max Minutes:")
            mins_label.setStyleSheet("font-weight: 600; color: #4a5568;")
            mins_container, self.minutes_spin = create_modern_slider(1, 120, 5, " min")
            grid.addWidget(mins_label, row, 0)
            grid.addWidget(mins_container, row, 1)
            row += 1
            
        # Add a single separator at the very end of the section
        row = self._add_section_separator(grid, row)
        
        return row

    # Add modernized A/B testing section
    def _add_modern_ab_section(self, grid, row):
        title = self._create_modern_section_title("🧪 A/B Testing - Option B Features", "#17a2b8")
        grid.addWidget(title, row, 0, 1, 2)
        row += 1
        
        # Content Features subsection
        content_label = QLabel("Content Features:")
        content_label.setStyleSheet("font-weight: bold; color: #666; margin-top: 8px; font-size: 12pt;")
        grid.addWidget(content_label, row, 0, 1, 2)
        row += 1
        
        # Add content feature checkboxes in organized layout
        content_features = [
            ('ab_lie', 'Lie'), ('ab_rude_tone', 'Rude Tone'), ('ab_kind_tone', 'Kind Tone'),
            ('ab_advice_only', 'Advice Only'), ('ab_no_memory', 'No Memory'), ('ab_persona', 'Persona'),
            ('ab_mirror', 'Mirror'), ('ab_anti_mirror', 'Anti Mirror'), ('ab_grammar_errors', 'Grammar Errors'),
            ('ab_positive_feedback', 'Positive Feedback'), ('ab_critical_feedback', 'Critical Feedback'),
            ('ab_neutral_feedback', 'Neutral Feedback'), ('ab_hedging', 'Hedging Language'),
        ]
        
        for i, (attr_name, display_name) in enumerate(content_features):
            checkbox = create_modern_checkbox(display_name, False)
            setattr(self, attr_name, checkbox)
            grid.addWidget(checkbox, row + i // 2, i % 2)
        
        row += (len(content_features) + 1) // 2
        
        # === START NEW CODE BLOCK ===
        # A-Side Trigger Setting
        threshold_label = QLabel("A/B Test Every:")
        threshold_label.setStyleSheet("font-weight: 600; color: #4a5568; margin-top: 10px;")
        threshold_container, self.ab_threshold_spin = create_modern_slider(1, 50, 5, " msgs")
        grid.addWidget(threshold_label, row, 0)
        grid.addWidget(threshold_container, row, 1)
        row += 1
        # === END NEW CODE BLOCK ===
        
        # UI Features subsection
        ui_label = QLabel("UI Features:")
        ui_label.setStyleSheet("font-weight: bold; color: #666; margin-top: 12px; font-size: 12pt;")
        grid.addWidget(ui_label, row, 0, 1, 2)
        row += 1
        
        # UI features with dynamic settings
        self.ab_streaming = create_modern_checkbox("Streaming", False)
        grid.addWidget(self.ab_streaming, row, 0, 1, 2)
        row += 1
        
        # Text Size Changer with dynamic setting
        self.ab_text_size_changer = create_modern_checkbox("Text Size Changer", False)
        grid.addWidget(self.ab_text_size_changer, row, 0, 1, 2)
        row += 1
        
        # Dynamic text size setting
        text_size_b_label = QLabel("    Option B Text Size:")
        text_size_b_label.setStyleSheet("color: #666; margin-left: 20px; font-weight: 600;")
        text_size_b_container, text_size_b_spin = create_modern_slider(8, 48, 24, "pt")
        text_size_b_container.setVisible(False)
        text_size_b_label.setVisible(False)
        
        self.ab_setting_widgets['text_size_b'] = text_size_b_spin
        grid.addWidget(text_size_b_label, row, 0)
        grid.addWidget(text_size_b_container, row, 1)
        row += 1
        
        self.ab_text_size_changer.toggled.connect(
            lambda checked: (text_size_b_container.setVisible(checked), 
                           text_size_b_label.setVisible(checked)))
        
        # Typewriter with dynamic setting
        self.ab_typewriter = create_modern_checkbox("Typewriter", False)
        grid.addWidget(self.ab_typewriter, row, 0, 1, 2)
        row += 1
        
        # Dynamic typewriter speed setting
        typewriter_speed_b_label = QLabel("    Option B Speed:")
        typewriter_speed_b_label.setStyleSheet("color: #666; margin-left: 20px; font-weight: 600;")
        typewriter_speed_b_container, typewriter_speed_b_spin = create_modern_slider(1, 1000, 50, " ms")
        typewriter_speed_b_container.setVisible(False)
        typewriter_speed_b_label.setVisible(False)
        
        self.ab_setting_widgets['typewriter_speed_ms_b'] = typewriter_speed_b_spin
        grid.addWidget(typewriter_speed_b_label, row, 0)
        grid.addWidget(typewriter_speed_b_container, row, 1)
        row += 1
        
        self.ab_typewriter.toggled.connect(
            lambda checked: (typewriter_speed_b_container.setVisible(checked), 
                           typewriter_speed_b_label.setVisible(checked)))
        
        self.ab_thinking = create_modern_checkbox("Thinking", False)
        grid.addWidget(self.ab_thinking, row, 0, 1, 2)
        row += 1
        
        return row
   
    # In AI_clean.py, inside the SettingsDialog class...

    def _load_from_file(self, line_edit_widget):
        """Opens a file dialog to select a JSON file and puts the name in the line edit."""
        filepath, _ = QFileDialog.getOpenFileName(self, "Open Blueprint File", "", "JSON Files (*.json)")
        if filepath:
            # We just want the filename, not the whole path
            line_edit_widget.setText(Path(filepath).name)
            # After loading a file, it's good practice to re-verify it
            self._verify_blueprint_file(show_success_popup=False)

   # Save the configured feature settings and close the dialog
    def _save_and_accept(self):
        from feature_flags import feature_settings
        
        if hasattr(self, 'blueprint_filename_input'):
            feature_settings['blueprint_filename'] = self.blueprint_filename_input.text()
        
        if hasattr(self, 'mc_trigger_spin'):
            feature_settings['mc_trigger_count'] = self.mc_trigger_spin.value()
        if hasattr(self, 'mc_changes_list'):
            changes_to_save = []
            for i in range(self.mc_changes_list.count()):
                item_text = self.mc_changes_list.item(i).text()
                state_str, feature_name = item_text.split(" ", 1)
                changes_to_save.append({
                    "feature": feature_name,
                    "enabled": state_str == "Enable"
                })
            feature_settings['mc_changes'] = changes_to_save
            
        # Save Survey settings
        if hasattr(self, 'survey_trigger_spin'):
            feature_settings['survey_trigger_count'] = self.survey_trigger_spin.value()
        if hasattr(self, 'survey_filename_input'):
            feature_settings['survey_filename'] = self.survey_filename_input.text()
        
        if hasattr(self, 'chat_title_input'):
            feature_settings['custom_chat_title'] = self.chat_title_input.text()

        # Save basic UI-related settings if they exist
        if hasattr(self, 'text_size_spin'):
            feature_settings['text_size'] = self.text_size_spin.value()
        if hasattr(self, 'delay_spin'):
            feature_settings['delay_seconds'] = self.delay_spin.value()
        if hasattr(self, 'messages_spin'):
            feature_settings['auto_end_messages'] = self.messages_spin.value()
        if hasattr(self, 'minutes_spin'):
            feature_settings['auto_end_minutes'] = self.minutes_spin.value()

        # Save Slowdown settings if they exist
        if hasattr(self, 'sd_period'):
            feature_settings['slowdown_period_s'] = self.sd_period.value()
        if hasattr(self, 'sd_window'):
            feature_settings['slowdown_window_s'] = self.sd_window.value()
        if hasattr(self, 'sd_min'):
            feature_settings['slowdown_min_delay_s'] = self.sd_min.value()
        if hasattr(self, 'sd_perm_en'):
            feature_settings['slowdown_permanent_after_enabled'] = self.sd_perm_en.isChecked()
        if hasattr(self, 'sd_perm_s'):
            feature_settings['slowdown_permanent_after_s'] = self.sd_perm_s.value()

        # Save Typewriter settings if they exist
        if hasattr(self, 'typewriter_speed'):
            feature_settings['typewriter_speed_ms'] = self.typewriter_speed.value()

        # Save Erase History settings if they exist
        if hasattr(self, 'erase_delay'):
            feature_settings['erase_history_delay_s'] = self.erase_delay.value()
        if hasattr(self, 'erase_repeat'):
            feature_settings['erase_history_repeat'] = self.erase_repeat.isChecked()
        if hasattr(self, 'erase_interval'):
            feature_settings['erase_history_interval_s'] = self.erase_interval.value()

        # Save Block Messages settings if they exist
        if hasattr(self, 'block_msg_count'):
            feature_settings['block_message_count'] = self.block_msg_count.value()
        if hasattr(self, 'block_duration'):
            feature_settings['block_duration_s'] = self.block_duration.value()
        if hasattr(self, 'block_repeat'):
            feature_settings['block_repeat'] = self.block_repeat.isChecked()

        if hasattr(self, 'ab_threshold_spin'):
            feature_settings['ab_test_message_threshold'] = self.ab_threshold_spin.value()

        # Save A/B Testing – Option B Content Features
        if hasattr(self, 'ab_lie'):
            feature_settings['ab_lie_b'] = self.ab_lie.isChecked()
        if hasattr(self, 'ab_rude_tone'):
            feature_settings['ab_rude_tone_b'] = self.ab_rude_tone.isChecked()
        if hasattr(self, 'ab_kind_tone'):
            feature_settings['ab_kind_tone_b'] = self.ab_kind_tone.isChecked()
        if hasattr(self, 'ab_advice_only'):
            feature_settings['ab_advice_only_b'] = self.ab_advice_only.isChecked()
        if hasattr(self, 'ab_no_memory'):
            feature_settings['ab_no_memory_b'] = self.ab_no_memory.isChecked()
        if hasattr(self, 'ab_persona'):
            feature_settings['ab_persona_b'] = self.ab_persona.isChecked()
        if hasattr(self, 'ab_mirror'):
            feature_settings['ab_mirror_b'] = self.ab_mirror.isChecked()
        if hasattr(self, 'ab_anti_mirror'):
            feature_settings['ab_anti_mirror_b'] = self.ab_anti_mirror.isChecked()
        if hasattr(self, 'ab_grammar_errors'):
            feature_settings['ab_grammar_errors_b'] = self.ab_grammar_errors.isChecked()
        if hasattr(self, 'ab_positive_feedback'):
            feature_settings['ab_positive_feedback_b'] = self.ab_positive_feedback.isChecked()
        if hasattr(self, 'ab_critical_feedback'):
            feature_settings['ab_critical_feedback_b'] = self.ab_critical_feedback.isChecked()
        if hasattr(self, 'ab_neutral_feedback'):
            feature_settings['ab_neutral_feedback_b'] = self.ab_neutral_feedback.isChecked()
        if hasattr(self, 'ab_hedging'):
            feature_settings['ab_hedging_b'] = self.ab_hedging.isChecked()

        # Save A/B Testing – Option B UI Features
        if hasattr(self, 'ab_streaming'):
            feature_settings['ab_streaming_b'] = self.ab_streaming.isChecked()
        if hasattr(self, 'ab_text_size_changer'):
            feature_settings['ab_text_size_changer_b'] = self.ab_text_size_changer.isChecked()
        if hasattr(self, 'ab_typewriter'):
            feature_settings['ab_typewriter_b'] = self.ab_typewriter.isChecked()
        if hasattr(self, 'ab_thinking'):
            feature_settings['ab_thinking_b'] = self.ab_thinking.isChecked()

        # Save all dynamic A/B settings
        for setting_key, widget in self.ab_setting_widgets.items():
            if isinstance(widget, QSlider):
                feature_settings[setting_key] = widget.value()
            elif isinstance(widget, QCheckBox):
                feature_settings[setting_key] = widget.isChecked()

        # Close the dialog
        self.accept()
    def _add_modern_blueprint_section(self, grid, row):
        title = self._create_modern_section_title("▶️ Dynamic Experiment Blueprint", "#8e44ad")
        grid.addWidget(title, row, 0, 1, 2)
        row += 1

        # Filename input
        filename_label = QLabel("Blueprint Filename:")
        self.blueprint_filename_input = QLineEdit()
        grid.addWidget(filename_label, row, 0)
        grid.addWidget(self.blueprint_filename_input, row, 1)
        row += 1

        # Buttons
        open_btn = QPushButton("Open Blueprint...")
        edit_btn = QPushButton("Create / Edit Blueprint")
        verify_btn = QPushButton("Verify File")

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(open_btn)
        btn_layout.addWidget(edit_btn)
        btn_layout.addWidget(verify_btn)
        grid.addLayout(btn_layout, row, 0, 1, 2)
        row += 1

        # Status label
        self.blueprint_status_label = QLabel("Status: Unknown")
        grid.addWidget(self.blueprint_status_label, row, 0, 1, 2)
        row += 1

        # Connect buttons
        open_btn.clicked.connect(lambda: self._load_from_file(self.blueprint_filename_input))
        edit_btn.clicked.connect(self._launch_experiment_designer)
        verify_btn.clicked.connect(self._verify_blueprint_file)

        row = self._add_section_separator(grid, row)
        return row

    def _launch_script_editor(self):
        """Launches the external ScriptEditorDialog."""
        # This calls the class from the new file we just imported
        editor_dialog = ScriptEditorDialog(None)

        # We run exec() which opens the window and blocks until it's closed
        if editor_dialog.exec() == QDialog.Accepted:
            # User hit "Save"
            self.script_status_label.setText(f"<b>Target file:</b> {editor_dialog.filename}<br>Status: <b style='color: #28a745;'>Script saved!</b>")
        else:
            # User hit "Cancel"
            self.script_status_label.setText(f"<b>Target file:</b> {editor_dialog.filename}<br>Status: Editor cancelled, no changes saved.")

    def _add_modern_survey_section(self, grid, row):
        title = self._create_modern_section_title("📊 Survey Settings", "#17a2b8")
        grid.addWidget(title, row, 0, 1, 2)
        row += 1

        # Setting for trigger count
        trigger_label = QLabel("Show Survey Every:")
        trigger_label.setStyleSheet("font-weight: 600; color: #4a5568;")
        trigger_container, self.survey_trigger_spin = create_modern_slider(1, 20, 5, " messages")
        grid.addWidget(trigger_label, row, 0)
        grid.addWidget(trigger_container, row, 1)
        row += 1
        
        # Setting for the survey filename
        filename_label = QLabel("Survey Filename:")
        filename_label.setStyleSheet("font-weight: 600; color: #4a5568;")
        self.survey_filename_input = QLineEdit()
        self.survey_filename_input.setPlaceholderText("e.g., survey.json")
        self.survey_filename_input.setStyleSheet("padding: 8px; border: 2px solid #e2e8f0; border-radius: 4px;")
        grid.addWidget(filename_label, row, 0)
        grid.addWidget(self.survey_filename_input, row, 1)
        row += 1

        # --- NEW: Add Create/Edit and Verify buttons ---
        self.edit_survey_btn = QPushButton("Create / Edit Survey")
        self.verify_survey_btn = QPushButton("Verify Survey File")
        btn_style = """
            QPushButton {
                background: #6c757d; color: white; border: none; border-radius: 8px;
                padding: 10px; font-weight: bold; font-size: 11pt;
            }
            QPushButton:hover { background: #5a6268; }
        """
        self.edit_survey_btn.setStyleSheet(btn_style)
        self.verify_survey_btn.setStyleSheet(btn_style)
        grid.addWidget(self.edit_survey_btn, row, 0)
        grid.addWidget(self.verify_survey_btn, row, 1)
        row += 1

        # --- NEW: Add a status label ---
        self.survey_status_label = QLabel("Status: Unknown")
        self.survey_status_label.setStyleSheet("color: #666; margin-top: 5px;")
        grid.addWidget(self.survey_status_label, row, 0, 1, 2)
        row += 1

        # Connect the new buttons
        self.edit_survey_btn.clicked.connect(self._launch_survey_builder)
        self.verify_survey_btn.clicked.connect(self._verify_survey_file)

        row = self._add_section_separator(grid, row)
        return row

    # 2. ADD these two new helper methods to the SettingsDialog class:
    def _launch_survey_builder(self):
        """Launches the external SurveyBuilderDialog."""
        builder_dialog = SurveyBuilderDialog(self)
        
        if builder_dialog.exec() == QDialog.Accepted:
            self.survey_status_label.setText("Status: <b style='color: #28a745;'>Survey saved!</b>")
            # We can also auto-update the filename if the user saved a new one
            # For now, we'll keep it simple.
        else:
            self.survey_status_label.setText("Status: Builder cancelled, no changes saved.")

    def _verify_survey_file(self, show_success_popup=True):
        """Checks if the survey file exists and updates the status."""
        filename = self.survey_filename_input.text().strip()
        if not filename:
            self.survey_status_label.setText("Status: <b style='color: #e74c3c;'>No filename specified.</b>")
            return

        survey_path = Path(__file__).parent / filename
        if survey_path.exists():
            self.survey_status_label.setText(f"Status: <b style='color: #28a745;'>File '{filename}' FOUND.</b>")
            if show_success_popup:
                QMessageBox.information(self, "Success", f"Survey file '{filename}' was found.")
        else:
            self.survey_status_label.setText(f"Status: <b style='color: #e74c3c;'>File '{filename}' NOT FOUND.</b>")
            if show_success_popup:
                QMessageBox.warning(self, "File Not Found", f"Survey file '{filename}' was not found.")

    def _verify_script_file(self, show_success_popup=True):
        """Checks if the script file exists and updates the status."""
        from feature_flags import feature_settings
        filename = feature_settings.get('scripted_convo_file', 'script.txt')
        script_path = Path(__file__).parent / filename

        if script_path.exists():
            self.script_status_label.setText(f"<b>Target file:</b> {filename}<br>Status: <b style='color: #28a745;'>File FOUND. Ready to use.</b>")
            if show_success_popup:
                QMessageBox.information(self, "Success", f"Script file '{filename}' was found.")
        else:
            self.script_status_label.setText(f"<b>Target file:</b> {filename}<br>Status: <b style='color: #e74c3c;'>File NOT FOUND.</b>")
            if show_success_popup:
                QMessageBox.warning(self, "File Not Found", f"Script file '{filename}' was not found.\nPlease create one or check the directory.")


# ==============================================================================
# — Background OpenAI API Worker Thread —
# ==============================================================================

# Background thread that handles OpenAI API calls without blocking the UI
class ChatThread(QThread):
    # Signal definitions for communicating with the main UI thread
    result_ready = Signal(str)   # Emitted when full response is ready
    error = Signal(str)          # Emitted when an error occurs
    chunk_ready = Signal(str)    # Emitted for each streaming chunk

    # Initialize the worker thread with conversation context and configuration
    def __init__(
        self,
        history: list[dict],
        prompt: str,
        use_features: bool = True,
        feature_set: dict = None,
        is_option_b: bool = False,
        *,
        force_web_search: bool = False
    ) -> None:
        # Step 1: Initialize parent QThread
        super().__init__()
        
        # Step 2: Store conversation parameters
        self.history = history
        self.prompt = prompt
        self.use_features = use_features
        self.feature_set = feature_set  # Custom feature set for this thread
        self.is_option_b = is_option_b
        self.force_web_search = force_web_search  # Flag to force web search

    # Handle streaming response from OpenAI API and emit chunks as they arrive
    def _handle_streaming(self, messages: list[dict]) -> str:
        # Step 1: Initialize response accumulator
        full_response = ""
        
        # Step 2: Create streaming connection to OpenAI
        stream = CLIENT.chat.completions.create(model=MODEL, messages=messages, stream=True)
        
        # Step 3: Process each chunk as it arrives
        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                # Extract chunk text and add to full response
                chunk_text = chunk.choices[0].delta.content
                full_response += chunk_text
                # Emit chunk for real-time UI updates
                self.chunk_ready.emit(chunk_text)
        
        return full_response

    # Main thread execution method that runs in background
    def run(self) -> None:
        try:
            # Step 1: Initialize web search results
            sources: list[dict] = []

            # Step 2: Perform web search if requested and enabled
            if self.force_web_search and is_enabled(FeatureFlag.WEB_SEARCH):
                sources = search_web(self.prompt, k=3)

            # Step 3: Build conversation messages with features
            messages = build_messages(self.history, self.prompt, self.use_features, self.feature_set)

            # Step 4: Add current date for context
            messages.insert(0, {"role": "system", "content": f"Current date: {date.today().isoformat()}"})

            # Step 5: Add web search results with grounding instructions
            if sources:
                # Format search results as text block
                src_block = "\n".join(
                    f"- {s['title']} — {s['url']}\n  {s['snippet']}"
                    for s in sources if s.get("url")
                ).strip()
                
                # Insert grounding instructions at the beginning
                messages.insert(0, {
                    "role": "system",
                    "content": (
                        "You were provided recent web snippets and links.\n"
                        "RULES:\n"
                        "1) Prefer facts from SOURCES over memory.\n"
                        "2) If SOURCES conflict, state which source supports which claim.\n"
                        "3) If a claim isn't supported by SOURCES, say you can't confirm.\n"
                        "4) Do not invent citations.\n\n"
                        f"SOURCES:\n{src_block}"
                    )
                })

            # Step 6: Call OpenAI API with appropriate method
            if is_enabled(FeatureFlag.STREAMING):
                # Use streaming for real-time response
                result = self._handle_streaming(messages)
            else:
                # Use standard completion
                resp = CLIENT.chat.completions.create(model=MODEL, messages=messages)
                result = (resp.choices[0].message.content or "").strip()

            # Step 7: Add web search metadata if sources were used
            if sources:
                result = "🔎 Web-grounded answer:\n" + result
                result += "\n\nSources:\n" + "\n".join(f"- {s['url']}" for s in sources if s.get("url"))

            # Step 8: Store sources and emit final result
            self._sources_used = sources
            self.result_ready.emit(result)

        except OpenAIError as e:
            # Handle OpenAI-specific errors
            self.error.emit(f"API error: {e}")
        except Exception as e:
            # Handle any other unexpected errors
            self.error.emit(f"Unexpected error: {e}")


# ==============================================================================
# — Code Block Widget with Copy Functionality —
# ==============================================================================

# Custom widget for displaying formatted code with language label and copy button
class CodeBlock(QWidget):
    
    # Initialize code block widget with syntax highlighting and copy functionality
    def __init__(self, code_text: str, language: str = "", parent=None):
        # Step 1: Initialize parent widget
        super().__init__(parent)
        
        # Step 2: Store code content and language
        self.code_text = code_text
        self.language = language
        
        # Step 3: Build the user interface
        self._setup_ui()
    
    # Build the code block interface with header and content areas
    def _setup_ui(self):
        # Step 1: Create main layout with no margins
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Step 2: Create header section with language label and copy button
        header = QFrame()
        header.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-bottom: none;
                border-radius: 6px 6px 0px 0px;
                padding: 12px 16px;
                min-height: 40px;
            }
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 10, 12, 10)
        header_layout.setSpacing(16)
        
        # Step 3: Add language label (either provided language or default "CODE")
        if self.language:
            lang_label = QLabel(self.language.upper())
            lang_label.setStyleSheet("""
                color: #6c757d; 
                font-weight: bold; 
                font-size: 12px; 
                padding: 6px 4px;
                margin: 0px;
            """)
        else:
            lang_label = QLabel("CODE")
            lang_label.setStyleSheet("""
                color: #6c757d; 
                font-weight: bold; 
                font-size: 12px; 
                padding: 6px 4px;
                margin: 0px;
            """)
        
        lang_label.setAlignment(Qt.AlignVCenter)
        
        # Step 4: Create styled copy button
        copy_btn = QPushButton("Copy")
        copy_btn.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
                min-width: 70px;
                min-height: 32px;
                margin: 0px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QPushButton:pressed {
                background-color: #004494;
            }
        """)
        copy_btn.clicked.connect(self._copy_code)
        copy_btn.setFixedHeight(36)
        
        # Step 5: Arrange header components
        header_layout.addWidget(lang_label)
        header_layout.addStretch()  # Push copy button to the right
        header_layout.addWidget(copy_btn)
        
        # Step 6: Create code content area
        code_area = QTextEdit()
        code_area.setPlainText(self.code_text)
        code_area.setReadOnly(True)
        code_area.setStyleSheet("""
            QTextEdit {
                background-color: white;
                color: black;
                border: 1px solid #dee2e6;
                border-top: none;
                border-radius: 0px 0px 6px 6px;
                padding: 12px;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 13px;
                line-height: 1.4;
            }
            QScrollBar:vertical {
                background-color: #f8f9fa;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #ced4da;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #adb5bd;
            }
        """)
        
        # Step 7: Calculate and set appropriate height based on content
        font_metrics = code_area.fontMetrics()
        line_count = self.code_text.count('\n') + 1
        content_height = font_metrics.lineSpacing() * min(line_count, 15) + 24  # Max 15 lines visible
        code_area.setFixedHeight(content_height)
        
        # Step 8: Add both components to main layout
        layout.addWidget(header)
        layout.addWidget(code_area)
    
    # Copy code to clipboard and provide visual feedback by temporarily changing button appearance
    def _copy_code(self):
        # Step 1: Copy to clipboard
        clipboard = QApplication.clipboard()
        clipboard.setText(self.code_text)
        
        # Step 2: Show visual feedback
        copy_btn = self.findChild(QPushButton)
        if copy_btn:
            # Save current state
            original_text = copy_btn.text()
            
            # Change to success state (green "Copied!")
            copy_btn.setText("Copied!")
            copy_btn.setStyleSheet(copy_btn.styleSheet().replace("#007bff", "#28a745"))
            
            # Step 3: Auto-reset after delay
            from PySide6.QtCore import QTimer
            def reset_button():
                copy_btn.setText(original_text)
                copy_btn.setStyleSheet(copy_btn.styleSheet().replace("#28a745", "#007bff"))
            
            QTimer.singleShot(1000, reset_button)

# ==============================================================================
# — Individual Chat Message Bubble Widget —
# ==============================================================================

# Widget for displaying individual chat messages with rich text formatting and code block support
class MessageBubble(QWidget):

    # Initialize message bubble with content, user type, and styling
    def __init__(self, message: str, is_user: bool = True, parent=None):
        # Step 1: Initialize parent widget
        super().__init__(parent)
        
        # Step 2: Store message properties
        self.is_user = is_user
        self.message = message
        
        # Step 3: Build the user interface
        self._setup_ui()

    # Extract code blocks from text and replace with placeholders for separate rendering
    def _extract_and_replace_code_blocks(self, text: str) -> tuple[str, list]:
        # Step 1: Initialize code block storage
        code_blocks = []
        
        # Step 2: Define replacement function for regex matches
        def replace_code_block(match):
            lang = match.group(1) or ""  # Language identifier (optional)
            code = match.group(2)        # Actual code content
            placeholder = f"__CODE_BLOCK_{len(code_blocks)}__"
            code_blocks.append((code, lang))
            return placeholder
        
        # Step 3: Extract all code blocks using regex
        modified_text = re.sub(r'```(\w+)?\s*\n(.*?)\n```', replace_code_block, text, flags=re.DOTALL)
        return modified_text, code_blocks

    # Convert basic markdown syntax to HTML for rich text display
    def _markdown_to_html(self, text: str) -> str:
        # Step 1: Convert inline code with styling
        text = re.sub(r'`([^`]+?)`', r'<code style="background-color: #f8f9fa; color: #e83e8c; padding: 2px 4px; border-radius: 3px; font-family: Consolas, Monaco, monospace; font-size: 90%;">\1</code>', text)
        
        # Step 2: Convert bold text
        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
        
        # Step 3: Convert italic text
        text = re.sub(r'\*([^*]+?)\*', r'<i>\1</i>', text)
        
        # Step 4: Convert newlines to HTML breaks
        text = text.replace('\n', '<br>')
        
        return text

    # Build the message bubble interface with appropriate styling and content rendering
    def _setup_ui(self) -> None:
        # Step 1: Create main horizontal layout
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 5, 10, 5)

        # Step 2: Add stretch before user messages (right-align)
        if self.is_user:
            main_layout.addStretch()

        # Step 3: Create message bubble frame
        bubble = QFrame()
        bubble.setMaximumWidth(600)

        # Step 4: Apply styling based on message sender
        if self.is_user:
            # User messages: green background, white text
            bubble.setStyleSheet("""
                background-color: #10a37f;
                color: white;
                border-radius: 18px;
                padding: 12px 16px;
                margin: 4px;
            """)
        else:
            # Assistant messages: light gray background, dark text
            bubble.setStyleSheet("""
                background-color: #f1f3f4;
                color: #333333;
                border-radius: 18px;
                padding: 12px 16px;
                margin: 4px;
                border: 1px solid #e0e0e0;
            """)

        # Step 5: Create bubble content layout
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(8, 8, 8, 8)

        # Step 6: Process message content for code blocks and markdown
        text_without_code, code_blocks = self._extract_and_replace_code_blocks(self.message)
        html_content = self._markdown_to_html(text_without_code)
        
        # Step 7: Split content by code block placeholders
        parts = html_content.split('__CODE_BLOCK_')
        
        # Step 8: Add the first text part (before any code blocks)
        if parts[0].strip():
            message_label = QLabel()
            message_label.setWordWrap(True)
            message_label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
            message_label.setTextFormat(Qt.RichText)
            message_label.setText(parts[0])
            
            # Apply color based on sender
            base_color = "white" if self.is_user else "#333333"
            message_label.setStyleSheet(f"""
                font-size: 20pt; 
                color: {base_color};
                selection-background-color: rgba(0, 123, 255, 0.3);
            """)
            bubble_layout.addWidget(message_label)
        
        # Step 9: Add code blocks and remaining text parts alternately
        for i, part in enumerate(parts[1:], 0):
            # Add code block widget if available
            if i < len(code_blocks):
                code_text, lang = code_blocks[i]
                code_widget = CodeBlock(code_text, lang)
                bubble_layout.addWidget(code_widget)
            
            # Add text content after the code block
            remaining_text = part[part.find('__') + 2:] if '__' in part else part
            if remaining_text.strip():
                message_label = QLabel()
                message_label.setWordWrap(True)
                message_label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
                message_label.setTextFormat(Qt.RichText)
                message_label.setText(remaining_text)
                
                base_color = "white" if self.is_user else "#333333"
                message_label.setStyleSheet(f"""
                    font-size: 20pt; 
                    color: {base_color};
                    selection-background-color: rgba(0, 123, 255, 0.3);
                """)
                bubble_layout.addWidget(message_label)

        # Step 10: Add bubble to main layout
        main_layout.addWidget(bubble)

        # Step 11: Add stretch after assistant messages (left-align)
        if not self.is_user:
            main_layout.addStretch()

    # Update font size for all text labels in the message bubble
    def update_font_size(self, font_size: int):
        # Step 1: Get all labels in the bubble
        labels = self.findChildren(QLabel)
        base_color = "white" if self.is_user else "#333333"
        
        # Step 2: Update each label's font size
        for label in labels:
            # Skip code block language labels
            if label.text() in ["CODE"] or label.text().isupper():
                continue
                
            # Apply new font size with existing color
            label.setStyleSheet(f"""
                font-size: {font_size}pt;
                color: {base_color};
                selection-background-color: rgba(0, 123, 255, 0.3);
            """)


# ==============================================================================
# — Animated Thinking Indicator Widget —
# ==============================================================================

# Small animated bubble that shows a "thinking..." indicator with cycling dots
class ThinkingBubble(QWidget):

    # Initialize thinking bubble with animation timer and visual setup
    def __init__(self, parent=None):
        # Step 1: Initialize parent widget
        super().__init__(parent)
        
        # Step 2: Build the visual components
        self._setup_ui()
        
        # Step 3: Initialize animation state
        self.dots = 0  # Current number of dots to show (0-3)
        
        # Step 4: Set up animation timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_dots)  # Connect to dot update function
        self.timer.start(THINK_INTERVAL_MS)            # Start animation with configured interval

    # Build the thinking bubble interface with styled frame and label
    def _setup_ui(self) -> None:
        # Step 1: Create main horizontal layout
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 5, 10, 5)

        # Step 2: Create bubble frame with rounded styling
        bubble = QFrame()
        bubble.setMaximumWidth(400)
        bubble.setStyleSheet(
            """
            background-color: #f1f3f4;
            border-radius: 18px;
            padding: 12px 16px;
            margin: 4px;
            border: 1px solid #e0e0e0;
            """
        )

        # Step 3: Create bubble content layout
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(8, 8, 8, 8)

        # Step 4: Add thinking label with initial text
        self.thinking_label = QLabel("GPT is thinking...")
        self.thinking_label.setStyleSheet("color: #666; font-size: 20pt;")
        bubble_layout.addWidget(self.thinking_label)

        # Step 5: Position bubble on the left side
        main_layout.addWidget(bubble)
        main_layout.addStretch()  # Push bubble to left side

    # Update the number of dots in the thinking animation
    def _update_dots(self) -> None:
        # Step 1: Cycle through dot count (0, 1, 2, 3, then back to 0)
        self.dots = (self.dots + 1) % 4
        
        # Step 2: Generate dot string and update label
        dots = "." * self.dots
        self.thinking_label.setText(f"GPT is thinking{dots}")

    # Stop the thinking animation when response is ready
    def stop_animation(self) -> None:
        # Step 1: Stop the animation timer
        self.timer.stop()

# ==============================================================================
# — A/B Testing Comparison Dialog —
# ==============================================================================

# Dialog window for presenting side-by-side A/B testing options with live feature demonstrations
# Dialog window for presenting side-by-side A/B testing options with live feature demonstrations
class ABTestingDialog(QDialog):

    # Initialize A/B testing dialog with two responses and timing/animation capabilities
    def __init__(self, response_a: str, response_b: str, parent=None):
        # Step 1: Initialize parent dialog
        super().__init__(parent)
        
        # Step 2: Store the two responses being compared
        self.response_a = response_a
        self.response_b = response_b

        # Step 3: Initialize selection tracking variables
        self.selected_response: str | None = None
        self.selected_version: str | None = None
        self.selection_latency: int = 0
        self.dialog_start_time = time.time()  # Used to compute selection latency

        # Step 4: Determine test type based on content similarity
        self.identical_content = (response_a == response_b)  # UI test vs content test

        # Step 5: Initialize typewriter animation state
        self._typewriter_timer: QTimer | None = None
        self._typewriter_index: int = 0
        self._typewriter_text: str = ""
        self._typewriter_target: QTextEdit | None = None

        # Step 6: Initialize thinking animation state
        self._thinking_timer: QTimer | None = None
        self._thinking_dots: int = 0
        self._thinking_target: QTextEdit | None = None

        # Step 7: Initialize Option B animation state
        self._typewriter_timer_b: QTimer | None = None
        self._typewriter_index_b: int = 0
        self._typewriter_text_b: str = ""
        self._typewriter_target_b: QTextEdit | None = None
        self._thinking_timer_b: QTimer | None = None
        self._thinking_dots_b: int = 0
        self._thinking_target_b: QTextEdit | None = None

        # Step 8: Build interface and start demonstrations
        self._setup_ui()
        self._start_demonstrations()

    # Build the side-by-side comparison interface with Option A and Option B panels
    def _setup_ui(self) -> None:
        # Step 1: Set window properties based on test type
        self.setWindowTitle("Which presentation do you prefer?" if self.identical_content else "Which response do you prefer?")
        self.setMinimumSize(1000, 750)  # Give room for side-by-side comparison

        # Step 2: Create main layout
        layout = QVBoxLayout(self)

        # Step 3: Add instruction label at the top
        instructions = QLabel(
            "Same content, different presentation. Choose which you prefer:" if self.identical_content
            else "Choose which response you prefer:"
        )
        instructions.setStyleSheet("font-size: 14pt; font-weight: bold; margin-bottom: 10px;")
        instructions.setAlignment(Qt.AlignCenter)
        layout.addWidget(instructions)

        # Step 4: Create horizontal layout for side-by-side panels
        responses_layout = QHBoxLayout()

        # Step 5: Build Option A panel (left side)
        a_container = QFrame()
        a_container.setStyleSheet(
            """
            QFrame { background: #f8f9fa; border: 2px solid #6c757d; border-radius: 12px; padding: 10px; margin: 5px; }
            """
        )
        a_layout = QVBoxLayout(a_container)

        # Option A title
        a_title = QLabel("Option A")
        a_title.setStyleSheet("font-size: 12pt; font-weight: bold; color: #6c757d; margin-bottom: 5px;")
        a_title.setAlignment(Qt.AlignCenter)
        a_layout.addWidget(a_title)

        # Option A text display area
        self.a_text = QTextEdit()
        self.a_text.setReadOnly(True)  # User cannot edit content
        
        # UPDATED: Apply A-side text size
        a_font_size = self._get_a_side_text_size()
        self.a_text.setStyleSheet(
            f"""
            QTextEdit {{ background: white; border: 1px solid #ccc; border-radius: 8px; padding: 10px; font-size: {a_font_size}pt; min-height: 200px; }}
            """
        )
        a_layout.addWidget(self.a_text)

        # Option A selection button
        self.a_button = QPushButton("Choose Option A")
        self.a_button.setStyleSheet(
            """
            QPushButton { background: #6c757d; color: white; border: none; border-radius: 8px; padding: 10px; font-size: 11pt; font-weight: bold; }
            QPushButton:hover { background: #5a6268; }
            QPushButton:disabled { background: #cccccc; color: #666666; }
            """
        )
        self.a_button.clicked.connect(self._select_a)
        self.a_button.setEnabled(False)  # Enabled after content finishes displaying
        a_layout.addWidget(self.a_button)

        responses_layout.addWidget(a_container)

        # Step 6: Build Option B panel (right side)
        b_container = QFrame()
        b_container.setStyleSheet(
            """
            QFrame { background: #f8f9fa; border: 2px solid #6c757d; border-radius: 12px; padding: 10px; margin: 5px; }
            """
        )
        b_layout = QVBoxLayout(b_container)

        # Option B title
        b_title = QLabel("Option B")
        b_title.setStyleSheet("font-size: 12pt; font-weight: bold; color: #6c757d; margin-bottom: 5px;")
        b_title.setAlignment(Qt.AlignCenter)
        b_layout.addWidget(b_title)

        # Option B text display area
        self.b_text = QTextEdit()
        self.b_text.setReadOnly(True)
        
        # UPDATED: Apply B-side text size
        b_font_size = self._get_b_side_text_size()
        self.b_text.setStyleSheet(
            f"""
            QTextEdit {{ background: white; border: 1px solid #ccc; border-radius: 8px; padding: 10px; font-size: {b_font_size}pt; min-height: 200px; }}
            """
        )
        b_layout.addWidget(self.b_text)

        # Option B selection button
        self.b_button = QPushButton("Choose Option B")
        self.b_button.setStyleSheet(
            """
            QPushButton { background: #6c757d; color: white; border: none; border-radius: 8px; padding: 10px; font-size: 11pt; font-weight: bold; }
            QPushButton:hover { background: #5a6268; }
            QPushButton:disabled { background: #cccccc; color: #666666; }
            """
        )
        self.b_button.clicked.connect(self._select_b)
        self.b_button.setEnabled(False)
        b_layout.addWidget(self.b_button)

        responses_layout.addWidget(b_container)
        layout.addLayout(responses_layout)

        # Step 7: Add status message below the panels
        self.status_label = QLabel("Loading responses...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 10pt; color: #666; margin-top: 10px;")
        layout.addWidget(self.status_label)

    # NEW: Get A-side text size from settings
    def _get_a_side_text_size(self) -> int:
        # Step 1: Check if A-side text size changer is enabled
        if is_enabled(FeatureFlag.TEXT_SIZE_CHANGER):
            # Use A-side text size setting
            text_size = get_setting_value('text_size', False)
            if text_size is not None:
                return text_size
        
        # Step 2: Default fallback
        return 11

    # NEW: Get B-side text size from settings
    def _get_b_side_text_size(self) -> int:
        # Step 1: Check if B-side text size changer is enabled for A/B testing
        from feature_flags import feature_settings
        if feature_settings.get('ab_text_size_changer_b', False):
            # Use B-side text size setting
            text_size = get_setting_value('text_size', True)
            if text_size is not None:
                return text_size
        
        # Step 2: Default fallback
        return 11

    # Start the appropriate demonstration effects for both Option A and Option B
    def _start_demonstrations(self) -> None:
        # Step 1: Handle Option A presentation based on test type
        if self.response_a == self.response_b:
            # UI test: same content, different presentation for A
            if is_enabled(FeatureFlag.STREAMING):
                self._setup_streaming_for_option_a()
            elif is_enabled(FeatureFlag.THINKING):
                self.a_text.clear()
                self._start_thinking_demo()
            elif is_enabled(FeatureFlag.TYPEWRITER):
                self.a_text.clear()
                self._start_typewriter_demo()
            else:
                # No special effects - show immediately
                self.a_text.setPlainText(self.response_a)
        else:
            # Content test: A gets main chat features with priority order
            if is_enabled(FeatureFlag.TYPEWRITER):
                self.a_text.clear()
                self._start_typewriter_demo()
            elif is_enabled(FeatureFlag.STREAMING):
                self._setup_streaming_for_option_a()
            elif is_enabled(FeatureFlag.THINKING):
                self.a_text.clear()
                self._start_thinking_demo()
            else:
                # No special effects - show immediately
                self.a_text.setPlainText(self.response_a)

        # Step 2: Handle Option B presentation using B-specific settings
        from feature_flags import feature_settings
        if feature_settings.get('ab_streaming_b', False):
            self._setup_streaming_for_option_b()
        elif feature_settings.get('ab_thinking_b', False):
            self._start_thinking_demo_for_b()
        elif feature_settings.get('ab_typewriter_b', False):
            self._start_typewriter_demo_for_b()
        else:
            # No special UI for B - show immediately
            self.b_text.setPlainText(self.response_b)
        
        # Step 3: Enable selection buttons after animations start
        QTimer.singleShot(500, self._enable_buttons)

    # Set up simulated streaming effect for Option B
    def _setup_streaming_for_option_b(self):
        # Step 1: Attempt to start streaming simulation
        if self._simulate_streaming_b():
            pass  # Streaming started successfully
        else:
            # Step 2: Fallback to immediate display if streaming fails
            self.b_text.setPlainText(self.response_b)

    # Create simulated streaming by breaking response into chunks for Option B
    def _simulate_streaming_b(self):
        # Step 1: Break response into paragraph chunks
        paragraphs = self.response_b.split('\n\n')
        if len(paragraphs) == 1:
            # No double newlines found, try single newlines
            paragraphs = self.response_b.split('\n')
        
        # Step 2: Prepare chunks with proper formatting
        self._simulated_chunks_b = [p + '\n\n' if i < len(paragraphs)-1 else p 
                                for i, p in enumerate(paragraphs) if p.strip()]
        
        # Step 3: Initialize streaming state
        self._chunk_index_b = 0
        self._streaming_display_text_b = ""
        
        # Step 4: Start streaming with first chunk
        self.b_text.clear()
        self._show_next_simulated_chunk_b()
        return True

    # Display the next chunk in the simulated streaming sequence for Option B
    def _show_next_simulated_chunk_b(self):
        # Step 1: Check if more chunks are available
        if self._chunk_index_b < len(self._simulated_chunks_b):
            # Step 2: Get current chunk and add to display
            chunk = self._simulated_chunks_b[self._chunk_index_b]
            self._streaming_display_text_b += chunk
            self.b_text.setPlainText(self._streaming_display_text_b)
            
            # Step 3: Auto-scroll to bottom to show new content
            scrollbar = self.b_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
            
            # Step 4: Move to next chunk
            self._chunk_index_b += 1
            
            # Step 5: Schedule next chunk or finish streaming
            if self._chunk_index_b < len(self._simulated_chunks_b):
                # Schedule next chunk with different delay than Option A
                QTimer.singleShot(600, self._show_next_simulated_chunk_b)
            else:
                # Finished simulated streaming for B
                pass  # B side doesn't control button enabling

    # Start thinking animation effect for Option B
    def _start_thinking_demo_for_b(self):
        # Step 1: Initialize thinking display
        self.b_text.setPlainText("🤔 Thinking")
        self._thinking_dots_b = 0
        self._thinking_target_b = self.b_text

        # Step 2: Set up animation timer
        self._thinking_timer_b = QTimer(self)
        self._thinking_timer_b.timeout.connect(self._update_thinking_b)
        self._thinking_timer_b.start(THINK_INTERVAL_MS)

        # Step 3: Schedule thinking completion after minimum time
        QTimer.singleShot(max(MIN_THINK_TIME_MS, 2500), self._finish_thinking_demo_for_b)

    # Update the thinking animation dots for Option B
    def _update_thinking_b(self):
        # Step 1: Cycle through dot count (0-3)
        self._thinking_dots_b = (self._thinking_dots_b + 1) % 4
        
        # Step 2: Update display with current dot count
        dots = "." * self._thinking_dots_b
        if self._thinking_target_b:
            self._thinking_target_b.setPlainText(f"🤔 Thinking{dots}")

    # Complete thinking animation and transition to next effect for Option B
    def _finish_thinking_demo_for_b(self):
        # Step 1: Stop thinking animation timer
        if self._thinking_timer_b:
            self._thinking_timer_b.stop()
            self._thinking_timer_b = None

        # Step 2: Check if typewriter effect should follow
        from feature_flags import feature_settings
        if feature_settings.get('ab_typewriter_b', False):
            self._start_typewriter_demo_for_b()
        else:
            # Show final text immediately
            self.b_text.setPlainText(self.response_b)

    # Start typewriter character-by-character reveal effect for Option B
    def _start_typewriter_demo_for_b(self):
        # Step 1: Initialize typewriter state
        self.b_text.clear()
        self._typewriter_index_b = 0
        self._typewriter_text_b = self.response_b
        self._typewriter_target_b = self.b_text

        # Step 2: UPDATED: Use B-side configurable speed directly
        typewriter_speed = get_setting_value('typewriter_speed_ms_b', False)
        if typewriter_speed is None:
            typewriter_speed = 50  # B-side default fallback
        
        self._typewriter_timer_b = QTimer(self)
        self._typewriter_timer_b.timeout.connect(self._update_typewriter_b)
        self._typewriter_timer_b.start(typewriter_speed)  # Use B-side configurable speed

    # Update typewriter effect by adding one character for Option B
    def _update_typewriter_b(self):
        # Step 1: Validate target exists
        if not self._typewriter_target_b:
            return
            
        # Step 2: Add next character if available
        if self._typewriter_index_b < len(self._typewriter_text_b):
            current_text = self._typewriter_text_b[: self._typewriter_index_b + 1]
            self._typewriter_target_b.setPlainText(current_text)
            self._typewriter_index_b += 1
            
            # Auto-scroll to bottom
            scrollbar = self._typewriter_target_b.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        else:
            # Step 3: Complete typewriter effect
            if self._typewriter_timer_b:
                self._typewriter_timer_b.stop()
                self._typewriter_timer_b = None

    # Set up simulated streaming effect for Option A
    def _setup_streaming_for_option_a(self):
        # Step 1: Check if streaming is enabled
        if is_enabled(FeatureFlag.STREAMING):
            # Always simulate streaming for A/B testing since we have full response
            self._simulate_streaming()
        else:
            # Step 2: Fallback to immediate display
            self.a_text.setPlainText(self.response_a)
            self._enable_buttons()

    # Create simulated streaming by breaking response into chunks for Option A
    def _simulate_streaming(self):
        # Step 1: Break response into paragraph chunks
        paragraphs = self.response_a.split('\n\n')
        if len(paragraphs) == 1:
            # No double newlines found, try single newlines
            paragraphs = self.response_a.split('\n')
        
        # Step 2: Prepare chunks with proper formatting
        self._simulated_chunks = [p + '\n\n' if i < len(paragraphs)-1 else p 
                                for i, p in enumerate(paragraphs) if p.strip()]
        
        # Step 3: Initialize streaming state
        self._chunk_index = 0
        self._streaming_display_text = ""
        
        # Step 4: Start streaming with first chunk
        self.a_text.clear()
        self._show_next_simulated_chunk()

    # Display the next chunk in the simulated streaming sequence for Option A
    def _show_next_simulated_chunk(self):
        # Step 1: Check if more chunks are available
        if self._chunk_index < len(self._simulated_chunks):
            # Step 2: Get current chunk and add to display
            chunk = self._simulated_chunks[self._chunk_index]
            self._streaming_display_text += chunk
            self.a_text.setPlainText(self._streaming_display_text)
            
            # Step 3: Auto-scroll to bottom
            scrollbar = self.a_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
            
            # Step 4: Move to next chunk
            self._chunk_index += 1
            
            # Step 5: Schedule next chunk or finish streaming
            if self._chunk_index < len(self._simulated_chunks):
                # 800ms delay between chunks
                QTimer.singleShot(800, self._show_next_simulated_chunk)
            else:
                # Finished simulated streaming
                self._finish_streaming()

    # Complete streaming animation and enable user interaction
    def _finish_streaming(self):
        # Step 1: Enable selection buttons now that streaming is done
        self._enable_buttons()

    # Start thinking animation effect for Option A
    def _start_thinking_demo(self) -> None:
        # Step 1: Update status and initialize thinking display
        self.status_label.setText("Processing...")
        self.a_text.setPlainText("🤔 Thinking")
        self._thinking_dots = 0
        self._thinking_target = self.a_text

        # Step 2: Set up animation timer
        self._thinking_timer = QTimer(self)
        self._thinking_timer.timeout.connect(self._update_thinking)
        self._thinking_timer.start(THINK_INTERVAL_MS)

        # Step 3: Schedule thinking completion after minimum time
        QTimer.singleShot(max(MIN_THINK_TIME_MS, 2000), self._finish_thinking_demo)

    # Update the thinking animation dots for Option A
    def _update_thinking(self) -> None:
        # Step 1: Cycle through dot count (0-3)
        self._thinking_dots = (self._thinking_dots + 1) % 4
        
        # Step 2: Update display with current dot count
        dots = "." * self._thinking_dots
        if self._thinking_target:
            self._thinking_target.setPlainText(f"🤔 Thinking{dots}")

    # Complete thinking animation and transition to next effect for Option A
    def _finish_thinking_demo(self) -> None:
        # Step 1: Stop thinking animation timer
        if self._thinking_timer:
            self._thinking_timer.stop()
            self._thinking_timer = None

        # Step 2: Transition to typewriter or show final text
        if is_enabled(FeatureFlag.TYPEWRITER):
            self._start_typewriter_demo()
        else:
            self.a_text.setPlainText(self.response_a)
            self._enable_buttons()

    # Start typewriter character-by-character reveal effect for Option A
    def _start_typewriter_demo(self) -> None:
        # Step 1: Update status and initialize typewriter state
        self.status_label.setText("Processing...")
        self.a_text.clear()
        self._typewriter_index = 0
        self._typewriter_text = self.response_a
        self._typewriter_target = self.a_text

        # Step 2: UPDATED: Use A-side configurable speed directly
        typewriter_speed = get_setting_value('typewriter_speed_ms', False)
        if typewriter_speed is None:
            typewriter_speed = 20  # A-side default fallback
        
        self._typewriter_timer = QTimer(self)
        self._typewriter_timer.timeout.connect(self._update_typewriter)
        self._typewriter_timer.start(typewriter_speed)  # Use A-side configurable speed

    # Update typewriter effect by adding one character for Option A
    def _update_typewriter(self) -> None:
        # Step 1: Validate target exists
        if not self._typewriter_target:
            return
            
        # Step 2: Add next character if available
        if self._typewriter_index < len(self._typewriter_text):
            current_text = self._typewriter_text[: self._typewriter_index + 1]
            self._typewriter_target.setPlainText(current_text)
            self._typewriter_index += 1
            
            # Auto-scroll to bottom
            scrollbar = self._typewriter_target.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        else:
            # Step 3: Complete typewriter effect and enable buttons
            if self._typewriter_timer:
                self._typewriter_timer.stop()
                self._typewriter_timer = None
            self._enable_buttons()

    # Enable selection buttons when both options are ready
    def _enable_buttons(self) -> None:
        # Step 1: Update status message
        self.status_label.setText("Make your choice!")
        
        # Step 2: Enable both selection buttons
        self.a_button.setEnabled(True)
        self.b_button.setEnabled(True)

    # Handle user selection of Option A
    def _select_a(self) -> None:
        # Step 1: Record selection of Option A
        self._finish_selection('A', self.response_a)

    # Handle user selection of Option B
    def _select_b(self) -> None:
        # Step 1: Record selection of Option B
        self._finish_selection('B', self.response_b)

    # Complete the selection process and close dialog
    def _finish_selection(self, version: str, response: str) -> None:
        # Step 1: Calculate selection latency
        selection_time = int((time.time() - self.dialog_start_time) * 1000)
        
        # Step 2: Store selection results
        self.selected_response = response
        self.selected_version = version
        self.selection_latency = selection_time
        
        # Step 3: Clean up and close dialog
        self._cleanup_timers()
        self.accept()

    # Clean up all animation timers to prevent memory leaks
    def _cleanup_timers(self) -> None:
        # Step 1: Clean up Option A timers
        if self._typewriter_timer:
            self._typewriter_timer.stop()
            self._typewriter_timer = None
        if self._thinking_timer:
            self._thinking_timer.stop()
            self._thinking_timer = None
        
        # Step 2: Clean up Option B timers
        if hasattr(self, '_typewriter_timer_b') and self._typewriter_timer_b:
            self._typewriter_timer_b.stop()
            self._typewriter_timer_b = None
        if hasattr(self, '_thinking_timer_b') and self._thinking_timer_b:
            self._thinking_timer_b.stop()
            self._thinking_timer_b = None

    # Ensure timers are cleaned up when dialog is closed
    def closeEvent(self, event) -> None:
        # Step 1: Clean up all timers
        self._cleanup_timers()
        
        # Step 2: Call parent close event
        super().closeEvent(event)


# ==============================================================================
# — Main Chat Window Interface —
# ==============================================================================

# Primary chat interface that handles message display, sending, receiving, and A/B testing
# Primary chat interface that handles message display, sending, receiving, and A/B testing
class ChatWindow(QWidget):
    
    # Initialize chat window with conversation state, timers, and UI components
    def __init__(self) -> None:
        # Step 1: Initialize parent widget
        super().__init__()
        self.experiment_plan = None
        self.current_block_index = -1
        self.messages_in_current_block = 0
        self.dynamic_change_applied = False
        # Step 2: Initialize conversation tracking
        self.history: list[dict] = []  # Conversation history as role/content dicts
        self.count: int = 0           # Number of messages sent
        self.assistant_message_count: int = 0  # Track assistant messages for auto-end
        self.blocking: bool = False   # If True, input is temporarily disabled
        self._web_cache: list[dict] = []  # Web search results cache
        
        # Step 3: Initialize slowdown feature state
        self._must_slow_turn: bool = False
        self._earliest_display_ts: float | None = None

        # Step 4: Initialize erase memory feature state
        self.erase_timer: QTimer | None = None
        self.erase_count = 0  # Track how many times history has been erased

        # Step 5: Initialize auto-end feature state
        self.auto_end_timer: QTimer | None = None
        self.session_start_time = time.time()  # Track when chat session started

        # Step 6: Initialize typewriter effect state
        self._typebuf: str = ""                       # Text waiting to be typed
        self._typeidx: int = 0                        # Current position in the buffer
        self._typetimer: QTimer | None = None         # Timer controlling typing speed
        self._current_typing_bubble: QWidget | None = None  # Bubble being filled
        self._typing_label: QLabel | None = None      # Label being typed into

        # Step 7: Initialize thinking bubble state
        self._current_thinking_bubble: ThinkingBubble | None = None

        # Step 8: Initialize A/B testing state
        ab_thresh = get_setting_value('ab_test_message_threshold', False) # Get A-side setting
        if ab_thresh is None or ab_thresh < 1:
            ab_thresh = 5 # Fallback to a safe default
        self.ab_test_threshold = int(ab_thresh)
        self.ab_test_results: list[dict] = []   # Stores past test outcomes
        self.ab_responses: dict[str, str] | None = None  # Holds current A/B reply texts
        self._last_ab_choice: str | None = None          # What the user picked last

        self.script_index: int = 0 

        # Step 9: Initialize thread management
        self._threads: set[QThread] = set()

        # Step 10: Set up the interface and features
        self._build_ui()  # Build window layout and input controls
        self._setup_auto_end_timer()  # Setup auto-end timer if needed
        self._setup_erase_history_timer()  # Setup erase timer if enabled
        self._apply_text_size()       # Apply custom text size if enabled

        if is_enabled(FeatureFlag.DYNAMIC_FEATURE_CHANGING):
            self._initialize_blueprint_mode()

    # Set up automatic history erasing timer if the feature is enabled
    def _setup_erase_history_timer(self) -> None:
        # Step 1: Check if erase history feature is enabled
        if is_enabled(FeatureFlag.ERASE_HISTORY):
            # Step 2: Get timing configuration using A-side settings (session control)
            initial_delay = get_setting_value('erase_history_delay_s', False)
            if initial_delay is None:
                initial_delay = 60  # Fallback
            
            # Step 3: Create and start timer
            self.erase_timer = QTimer(self)
            self.erase_timer.timeout.connect(self._handle_erase_timeout)
            self.erase_timer.setSingleShot(True)
            self.erase_timer.start(initial_delay * 1000)  # Convert to milliseconds

    # Handle the erase history timeout event
    def _handle_erase_timeout(self) -> None:
        # Step 1: Erase the conversation history
        self.clear_data()
        self.erase_count += 1
        
        # Step 2: Set up repeat timer if enabled (using A-side settings for session control)
        repeat_enabled = get_setting_value('erase_history_repeat', False)
        if repeat_enabled is None:
            repeat_enabled = False  # Fallback
            
        if repeat_enabled:
            interval = get_setting_value('erase_history_interval_s', False)
            if interval is None:
                interval = 120  # Fallback
            self.erase_timer = QTimer(self)
            self.erase_timer.timeout.connect(self._handle_erase_timeout)
            self.erase_timer.setSingleShot(True)
            self.erase_timer.start(interval * 1000)

    def _initialize_blueprint_mode(self):
        """Loads the blueprint file and starts the first block of the experiment."""
        from feature_flags import feature_settings
        import json
        
        filename = feature_settings.get('blueprint_filename', 'experiment_blueprint.json')
        blueprint_path = Path(__file__).parent / filename

        if not blueprint_path.exists():
            log.error(f"Blueprint file not found: {filename}. Cannot start experiment.")
            self.add_system_message(f"ERROR: Blueprint file '{filename}' not found.")
            return

        try:
            with open(blueprint_path, 'r', encoding='utf-8') as f:
                self.experiment_plan = json.load(f)
            
            # Start the first block of the experiment
            self._start_next_block()

        except Exception as e:
            log.error(f"Failed to load or parse blueprint {filename}: {e}")

    def _start_next_block(self):
        """Advances the experiment to the next block."""
        if not self.experiment_plan: return

        self.current_block_index += 1

        if self.current_block_index >= len(self.experiment_plan):
            self.add_system_message("Experiment blueprint complete.")
            self._end_chat()
            return

        current_block = self.experiment_plan[self.current_block_index]
        self.messages_in_current_block = 0

        # --- MODIFICATION ---
        # Apply all configuration for the new block
        self._apply_block_config(current_block)
        # --- END MODIFICATION ---

    # Check if permanent slowdown should be active based on session duration
    def _slowdown_permanent_active(self, now_s: float) -> bool:
        # Step 1: Check if slowdown feature is enabled
        if not is_enabled(FeatureFlag.SLOWDOWN):
            return False
        
        # Step 2: Get permanent slowdown settings (A-side for session control)
        perm_enabled = get_setting_value('slowdown_permanent_after_enabled', False)
        if perm_enabled is None:
            perm_enabled = False  # Fallback
            
        if not perm_enabled:
            return False
        
        # Step 3: Check if enough time has elapsed
        threshold_s = get_setting_value('slowdown_permanent_after_s', False)
        if threshold_s is None:
            threshold_s = 600  # Fallback
        elapsed = now_s - self.session_start_time
        
        return elapsed >= threshold_s

    # Check if current time falls within a cyclic slowdown window
    def _in_slow_window(self, send_ts: float) -> bool:
        # Step 1: Check if slowdown feature is enabled
        if not is_enabled(FeatureFlag.SLOWDOWN):
            return False
        
        # Step 2: Get cycle timing settings (A-side for session control)
        normal_cycle_length = get_setting_value('slowdown_period_s', False)
        slow_window_length = get_setting_value('slowdown_window_s', False)
        
        if normal_cycle_length is None:
            normal_cycle_length = 100  # Fallback
        if slow_window_length is None:
            slow_window_length = 20  # Fallback
        
        normal_cycle_length = max(1, int(normal_cycle_length))
        slow_window_length = max(0, int(slow_window_length))
        
        if slow_window_length <= 0:
            return False
        
        # Step 3: Calculate position within the cycle
        elapsed = send_ts - self.session_start_time
        total_period = normal_cycle_length + slow_window_length
        position_in_total_period = elapsed % total_period
        
        # Step 4: Determine if we're in the slow window
        in_slow_window = position_in_total_period >= normal_cycle_length
        
        return in_slow_window

    def _apply_feature_changes(self, changes: dict):
        """
        Applies a new set of feature configurations mid-chat.
        'changes' is a dictionary like {'feature': FeatureFlag.TYPEWRITER, 'enabled': True}
        """
        log.info(f"Applying mid-chat feature changes: {changes}")

        # Update the global feature flags
        for change in changes:
            feature_flag = change.get("feature")
            is_enabled = change.get("enabled")
            if feature_flag in FeatureFlag:
                enabled_features[feature_flag] = is_enabled
    
    # Analyze and prepare slowdown settings for the current message turn
    def _prepare_turn_slowdown(self, send_ts: float) -> None:
        # Step 1: Check if slowdown feature is enabled
        if not is_enabled(FeatureFlag.SLOWDOWN):
            self._must_slow_turn = False
            self._earliest_display_ts = None
            return
        
        # Step 2: Check conditions
        perm_active = self._slowdown_permanent_active(send_ts)
        cyclic_active = self._in_slow_window(send_ts)
        
        # Step 3: Determine if slowdown should be applied
        must = perm_active or cyclic_active
        self._must_slow_turn = must
        
        # Step 4: Calculate earliest display time if slowdown is needed
        if must:
            min_delay = get_setting_value('slowdown_min_delay_s', False)
            if min_delay is None:
                min_delay = 4  # Fallback
            self._earliest_display_ts = send_ts + float(min_delay)
        else:
            self._earliest_display_ts = None

    # Execute function immediately or schedule it after remaining slowdown delay
    def _maybe_delay_then(self, fn) -> None:
        # Step 1: Check if slowdown delay is required
        if self._must_slow_turn and self._earliest_display_ts is not None:
            now = time.time()
            remaining = max(0.0, self._earliest_display_ts - now)
            
            # Step 2: Schedule function if delay is needed
            if remaining > 0:
                QTimer.singleShot(int(remaining * 1000), fn)
                return
        
        # Step 3: Execute immediately if no delay needed
        fn()

    # Set up automatic chat termination timer if time-based auto-end is enabled
    def _setup_auto_end_timer(self) -> None:
        # Step 1: Check if time-based auto-end is enabled
        if is_enabled(FeatureFlag.AUTO_END_AFTER_T_MIN):
            # Step 2: Get timeout setting and create timer (always use A-side for session control)
            minutes = get_setting_value('auto_end_minutes', False)  # A-side for session control
            if minutes is None:
                minutes = 5  # Fallback
            self.auto_end_timer = QTimer(self)
            self.auto_end_timer.timeout.connect(lambda: self._auto_end_chat("time limit"))
            self.auto_end_timer.setSingleShot(True)
            self.auto_end_timer.start(minutes * 60 * 1000)  # Convert to milliseconds

    # Apply custom text size to all chat messages if TEXT_SIZE_CHANGER is enabled
    def _apply_text_size(self) -> None:
        # Step 1: Check if text size feature is enabled
        if is_enabled(FeatureFlag.TEXT_SIZE_CHANGER):
            # Step 2: Get font size setting and store it (A-side for main chat)
            font_size = get_setting_value('text_size', False)
            if font_size is None:
                font_size = 20  # Fallback
            self.custom_font_size = font_size
            
            # Step 3: Apply immediately to existing messages
            self._apply_font_size_to_messages()

    # Update font size for all existing message bubbles and system messages
    def _apply_font_size_to_messages(self, font_size: int = None):
        # Step 1: Determine font size to use
        if font_size is None:
            if hasattr(self, 'custom_font_size'):
                font_size = self.custom_font_size
            else:
                font_size = 20  # Default fallback

        # Step 2: Apply font size to all widgets in message layout
        for i in range(self.messages_layout.count()):
            item = self.messages_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                
                # Step 3: Handle MessageBubble widgets
                if isinstance(widget, MessageBubble):
                    widget.update_font_size(font_size)
                else:
                    # Step 4: Handle other widget types (thinking bubbles, system messages)
                    labels = widget.findChildren(QLabel)
                    for label in labels:
                        if "thinking" in label.text().lower():
                            # Apply font size to thinking bubble
                            label.setStyleSheet(f"color: #666; font-size: {font_size}pt;")
                        elif label.styleSheet() and "italic" in label.styleSheet():
                            # Apply font size to system message
                            system_font_size = font_size if is_enabled(FeatureFlag.TEXT_SIZE_CHANGER) and hasattr(self, 'custom_font_size') else max(11, int(font_size * 0.75))
                            label.setStyleSheet(
                                f"color: #666; font-style: italic; font-size: {system_font_size}pt;"
                                "padding: 8px; background-color: rgba(0,0,0,0.05); border-radius: 12px;"
                            )

    # Automatically terminate the chat session for the specified reason
    def _auto_end_chat(self, reason: str) -> None:
        # Step 1: Show termination message to user
        self.add_system_message(f"Chat ended automatically: {reason} reached.")
        
        # Step 2: Schedule actual chat termination after brief delay
        QTimer.singleShot(2000, self._end_chat)

    # Check if any auto-end conditions have been met and trigger termination if needed
    def _check_auto_end_conditions(self) -> bool:
        # Step 1: Check message count condition (always use A-side for session control)
        if is_enabled(FeatureFlag.AUTO_END_AFTER_N_MSGS):
            max_messages = get_setting_value('auto_end_messages', False)  # A-side for session control
            if max_messages is None:
                max_messages = 10  # Fallback
            if self.assistant_message_count >= max_messages:
                self._auto_end_chat("message limit")
                return True
        
        # Step 2: Return False if no conditions triggered
        return False

    # Determine whether the End & Save button should be hidden from the interface
    def _should_hide_end_button(self) -> bool:
        # Step 1: Hide button if any auto-end features are enabled
        return (
            is_enabled(FeatureFlag.AUTO_END_AFTER_N_MSGS) or 
            is_enabled(FeatureFlag.AUTO_END_AFTER_T_MIN)
        )

    # Build the main chat interface with message area and input controls
    def _build_ui(self) -> None:
        # Step 1: Set window properties
        # --- START MODIFICATION ---
        # Check if the custom title feature is enabled and set the title accordingly.
        if is_enabled(FeatureFlag.CUSTOM_CHAT_TITLE):
            from feature_flags import feature_settings
            # Use the custom title from settings, with a fallback to the default APP_TITLE.
            title = feature_settings.get('custom_chat_title', APP_TITLE)
            self.setWindowTitle(title)
        else:
            # If the feature is off, use the default title.
            self.setWindowTitle(APP_TITLE)
        # --- END MODIFICATION ---

        self.resize(800, 600)
        layout = QVBoxLayout(self)

        # Step 2: Create scrollable message display area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setStyleSheet(
            "QScrollArea { background: white; border: none; border-radius: 8px; }"
        )

        # Step 3: Create container for all message bubbles
        self.messages_container = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setContentsMargins(0, 10, 0, 10)
        self.messages_layout.addStretch()  # Keeps messages at the top

        # Step 4: Connect scroll area and add to main layout
        self.scroll_area.setWidget(self.messages_container)
        layout.addWidget(self.scroll_area, 1)

        # Step 5: Add input controls at the bottom
        self._build_input(layout)

    # Build the input area with text field and action buttons
    def _build_input(self, parent: QVBoxLayout) -> None:
        # Step 1: Create horizontal layout for input controls
        input_layout = QHBoxLayout()

        # Step 2: Create message input field
        self.input_field = QLineEdit(placeholderText="Type your message...")
        input_layout.addWidget(self.input_field, 1)

        # Step 3: Create Send button with icon or text
        self.send_button = QPushButton()
        icon = QIcon.fromTheme("send")
        if icon.isNull():
            self.send_button.setText("Send")
        else:
            self.send_button.setIcon(icon)
        self.send_button.setFixedWidth(60)
        input_layout.addWidget(self.send_button)

        # Step 4: Create Search Web button (visible only if feature enabled)
        self.search_button = QPushButton("Search Web")
        self.search_button.setFixedWidth(100)
        self.search_button.clicked.connect(self.send_with_web_search)
        self.search_button.setVisible(is_enabled(FeatureFlag.WEB_SEARCH))
        input_layout.addWidget(self.search_button)

        # Step 5: Create End & Save button (hidden if auto-end features are enabled)
        self.end_button = QPushButton("End & Save")
        self.end_button.setFixedWidth(110)
        self.end_button.clicked.connect(self._end_chat)
        self.end_button.setVisible(not self._should_hide_end_button())
        input_layout.addWidget(self.end_button)

        # Step 6: Add input layout to parent
        parent.addLayout(input_layout)

        # Step 7: Connect button events and keyboard shortcuts
        self.send_button.clicked.connect(self.send_message)
        self.input_field.returnPressed.connect(self.send_message)

    # Add a user or assistant message bubble to the chat display
    def add_message(self, message: str, is_user: bool = True) -> None:
        # Step 1: Create message bubble
        bubble = MessageBubble(message, is_user)
        
        # Step 2: Apply custom font size if enabled
        if is_enabled(FeatureFlag.TEXT_SIZE_CHANGER) and hasattr(self, 'custom_font_size'):
            bubble.update_font_size(self.custom_font_size)
        
        # Step 3: Insert bubble into layout and scroll to show it
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble)
        QTimer.singleShot(10, self._scroll_to_bottom)

    # Add a centered system notice message (not from user or assistant)
    def add_system_message(self, message: str) -> None:
        # Step 1: Create system message widget container
        system_widget = QWidget()
        system_layout = QHBoxLayout(system_widget)
        system_layout.setContentsMargins(10, 5, 10, 5)

        # Step 2: Create styled system message label
        system_label = QLabel(message)
        system_label.setAlignment(Qt.AlignCenter)
        system_label.setStyleSheet(
            "color: #666; font-style: italic; font-size: 11pt; padding: 8px;"
            "background-color: rgba(0,0,0,0.05); border-radius: 12px;"
        )
        
        # Step 3: Center the label with stretchers
        system_layout.addStretch()
        system_layout.addWidget(system_label)
        system_layout.addStretch()

        # Step 4: Add to message layout and scroll to show it
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, system_widget)
        QTimer.singleShot(10, self._scroll_to_bottom)

    # Automatically scroll the message area to show the most recent message
    def _scroll_to_bottom(self) -> None:
        # Step 1: Get scroll bar and scroll to maximum position
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def change_chat_title(self, new_title: str) -> None:
        """Updates the main window title and adds a system message in the chat."""
        self.setWindowTitle(new_title)
        log.info(f"Chat title changed to: {new_title}")
        self.add_system_message(f"AI assistant has been changed to: {new_title}")

    # Set focus to input field when window becomes visible
    def showEvent(self, event) -> None:
        # Step 1: Call parent show event
        super().showEvent(event)
        
        # Step 2: Focus the input field for immediate typing
        self.input_field.setFocus()

    # Dynamically adjust font sizes when window is resized
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        h = self.height()

        # Input field font size
        input_font_size = max(12, int(h * 0.02))
        self.input_field.setStyleSheet(f"font-size:{input_font_size}pt;")

        # Message font size
        if is_enabled(FeatureFlag.TEXT_SIZE_CHANGER) and hasattr(self, 'custom_font_size'):
            message_font_size = self.custom_font_size
        else:
            message_font_size = max(20, int(h * 0.025))

        # Apply to all messages
        self._apply_font_size_to_messages(message_font_size)

    # Remove all messages from display and clear conversation history
    def clear_data(self) -> None:
        # Step 1: Remove all message widgets except the stretch item
        while self.messages_layout.count() > 1:
            child = self.messages_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # Step 2: Clear stored conversation history
        self.history.clear()
        
        # Step 3: Add notification about the erasure
        self.add_system_message("Chat history erased.")

    # Start a background thread and track it for proper cleanup
    def _start_and_track(self, thread: QThread) -> None:
        # Step 1: Add thread to tracking set
        self._threads.add(thread)
        
        # Step 2: Set up cleanup when thread finishes
        def _on_finished():
            self._threads.discard(thread)
        thread.finished.connect(_on_finished)
        
        # Step 3: Start the thread
        thread.start()

    # Process user input and initiate message sending
    def send_message(self) -> None:
        # Step 1: Get and validate user input
        txt = self.input_field.text().strip()
        if not txt:
            return

        # Step 2: Log the user message
        log_message("user", txt)

        # Step 3: Display user message and update conversation history
        self.add_message(txt, is_user=True)
        self.history.append({"role": "user", "content": txt})
        
        # Step 4: Clear input and disable controls during processing
        self.input_field.clear()
        self.input_field.setEnabled(False)
        self.send_button.setEnabled(False)
        if hasattr(self, "search_button") and self.search_button is not None:
            self.search_button.setEnabled(False)

        # Step 5: Capture send timestamp for timing analysis
        sent_ts = time.time()

        # Step 6: Apply delay before sending if feature is enabled (using A-side settings for user actions)
        if is_enabled(FeatureFlag.DELAY_BEFORE_SEND):
            delay_seconds = get_setting_value('delay_seconds', False)  # Always A-side for user actions
            if delay_seconds is None:
                delay_seconds = 2  # Fallback
            QTimer.singleShot(delay_seconds * 1000, lambda ts=sent_ts: self._send_after_delay(txt, ts))
        else:
            self._send_after_delay(txt, sent_ts)

    # Execute the actual message sending logic after any configured delay
    def _send_after_delay(self, txt: str, sent_ts: float) -> None:
        # Step 1: Prepare slowdown settings for this turn
        self._prepare_turn_slowdown(sent_ts)
        
        # === NEW SCRIPTED RESPONSE LOGIC (JSON-aware) ===
        from feature_flags import get_scripted_convo

        # Check if Scripted Mode is on
        if is_enabled(FeatureFlag.SCRIPTED_RESPONSES):
            script_list = get_scripted_convo() # This is now our list of objects
            
            # Check if we still have messages left in the script
            if self.script_index < len(script_list):
                
                # Get the entire step object for the current turn
                current_step = script_list[self.script_index]
                self.script_index += 1  # Always advance the script index
                
                step_type = current_step.get("type", "normal") # Default to "normal" if type is missing
                
                if step_type == "normal":
                    # --- This is a standard scripted response ---
                    reply = current_step.get("response", "SCRIPT ERROR: Missing 'response' key")
                    
                    if is_enabled(FeatureFlag.THINKING):
                        self._start_thinking() # Show thinking bubble for realism
                        
                    # Call _on_response after a short delay to simulate AI "thinking"
                    QTimer.singleShot(1000, lambda: self._on_response(reply))
                    return
                    
                elif step_type == "ab_test":
                    # --- This is a scripted A/B test turn ---
                    reply_a = current_step.get("response_a", "SCRIPT ERROR: Missing 'response_a'")
                    reply_b = current_step.get("response_b", "SCRIPT ERROR: Missing 'response_b'")
                    
                    if is_enabled(FeatureFlag.THINKING):
                        self._start_thinking() # Show thinking bubble
                    
                    # Call our new A/B handler
                    self._handle_scripted_ab_turn(reply_a, reply_b)
                    return

            # If script is finished, or step type was unknown, fall through...
        
        # === END NEW SCRIPTED LOGIC ===
        
        # If scripted mode is off OR the script is finished, the code falls through
        # to the normal A/B test and AI logic below.
        
        # Step 2: Check if this turn should trigger an AI A/B test
        is_ab_turn = is_enabled(FeatureFlag.AB_TESTING) and (self.count + 1) % self.ab_test_threshold == 0

        # Step 3: Handle A/B UI ALT (AI-generated)
        if is_ab_turn and is_enabled(FeatureFlag.AB_UI_ALT):
            if is_enabled(FeatureFlag.THINKING) and not self._current_thinking_bubble:
                self._start_thinking()
            self._start_ab_ui_alt_workflow(txt)
            return

        # Step 4: Handle UI A/B test (AI-generated)
        elif is_ab_turn and is_enabled(FeatureFlag.AB_UI_TEST):
            if is_enabled(FeatureFlag.THINKING) and not self._current_thinking_bubble:
                self._start_thinking()
            self.ui_thread = ChatThread(self.history, txt, use_features=True)
            self.ui_thread.result_ready.connect(self._on_ui_ab_response)
            self.ui_thread.error.connect(self._on_error)
            self._start_and_track(self.ui_thread)
            return

        # Step 5: Handle content A/B test (AI-generated)
        elif is_ab_turn:
            if is_enabled(FeatureFlag.THINKING) and not self._current_thinking_bubble:
                self._start_thinking()

            # Initialize A/B response tracking
            self.ab_responses = {'A': None, 'B': None}
            self.ab_responses_ready = 0

            # Step 5a: Build custom feature set for Option B
            from feature_flags import feature_settings
            option_b_features = {flag: False for flag in FeatureFlag} 

            content_feature_mappings = [
                ('ab_lie_b', FeatureFlag.LIE),
                ('ab_rude_tone_b', FeatureFlag.RUDE_TONE),
                ('ab_kind_tone_b', FeatureFlag.KIND_TONE),
                ('ab_advice_only_b', FeatureFlag.ADVICE_ONLY),
                ('ab_no_memory_b', FeatureFlag.NO_MEMORY),
                ('ab_persona_b', FeatureFlag.PERSONA),
                ('ab_mirror_b', FeatureFlag.MIRROR),
                ('ab_anti_mirror_b', FeatureFlag.ANTI_MIRROR),
                ('ab_grammar_errors_b', FeatureFlag.GRAMMAR_ERRORS),
                ('ab_positive_feedback_b', FeatureFlag.POSITIVE_FEEDBACK),
                ('ab_critical_feedback_b', FeatureFlag.CRITICAL_FEEDBACK),
                ('ab_neutral_feedback_b', FeatureFlag.NEUTRAL_FEEDBACK),
                ('ab_hedging_b', FeatureFlag.HEDGING_LANGUAGE)
            ]
            
            for setting_key, flag in content_feature_mappings:
                if feature_settings.get(setting_key, False):
                    option_b_features[flag] = True
                    # Handle mutually exclusive features
                    if flag == FeatureFlag.RUDE_TONE:
                        option_b_features[FeatureFlag.KIND_TONE] = False
                    elif flag == FeatureFlag.KIND_TONE:
                        option_b_features[FeatureFlag.RUDE_TONE] = False
                    elif flag == FeatureFlag.MIRROR:
                        option_b_features[FeatureFlag.ANTI_MIRROR] = False
                    elif flag == FeatureFlag.ANTI_MIRROR:
                        option_b_features[FeatureFlag.MIRROR] = False
                    elif flag in [FeatureFlag.POSITIVE_FEEDBACK, FeatureFlag.CRITICAL_FEEDBACK, FeatureFlag.NEUTRAL_FEEDBACK]:
                        for feedback_flag in [FeatureFlag.POSITIVE_FEEDBACK, FeatureFlag.CRITICAL_FEEDBACK, FeatureFlag.NEUTRAL_FEEDBACK]:
                            if feedback_flag != flag:
                                option_b_features[feedback_flag] = False
            
            ui_feature_mappings = [
                ('ab_streaming_b', FeatureFlag.STREAMING),
                ('ab_text_size_changer_b', FeatureFlag.TEXT_SIZE_CHANGER),
                ('ab_typewriter_b', FeatureFlag.TYPEWRITER),
                ('ab_thinking_b', FeatureFlag.THINKING)
            ]
            
            for setting_key, flag in ui_feature_mappings:
                if feature_settings.get(setting_key, False):
                    option_b_features[flag] = True

            # Step 5b: Create and start both A/B threads with Option B flag
            self.thread_a = ChatThread(self.history, txt, feature_set=enabled_features, is_option_b=False)
            self.thread_b = ChatThread(self.history, txt, feature_set=option_b_features, is_option_b=True)

            self.thread_a.result_ready.connect(lambda reply: self._on_ab_response(reply, 'A'))
            self.thread_b.result_ready.connect(lambda reply: self._on_ab_response(reply, 'B'))
            self.thread_a.error.connect(self._on_error)
            self.thread_b.error.connect(self._on_error)

            self._start_and_track(self.thread_a)
            self._start_and_track(self.thread_b)
            return

        # Step 6: Handle normal single completion (this is now the final 'else' case)
        if is_enabled(FeatureFlag.THINKING) and not self._current_thinking_bubble:
            self._start_thinking()
        self.thread = ChatThread(self.history, txt, use_features=True)
        self.thread.result_ready.connect(self._on_response)
        self.thread.error.connect(self._on_error)
        self.thread.chunk_ready.connect(self._on_chunk_ready)
        self._start_and_track(self.thread)

    # Display animated thinking bubble in the chat area
    def _start_thinking(self) -> None:
        # Step 1: Create and add thinking bubble to chat
        self._current_thinking_bubble = ThinkingBubble()
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, self._current_thinking_bubble)
        
        # Step 2: Scroll to show the thinking bubble
        QTimer.singleShot(10, self._scroll_to_bottom)

    # Handle incoming streaming chunks from the API
    def _on_chunk_ready(self, chunk: str) -> None:
        # Step 1: Initialize chunk buffer if needed
        if not hasattr(self, '_chunk_buffer'):
            self._chunk_buffer = ""
        
        # Step 2: Add chunk to buffer
        self._chunk_buffer += chunk
        
        # Step 3: Release buffer when paragraph break is detected
        if '\n' in self._chunk_buffer:
            self._release_buffered_chunk()

    # Release buffered streaming content to the UI
    def _release_buffered_chunk(self) -> None:
        # Step 1: Validate buffer has content
        if not hasattr(self, '_chunk_buffer') or not self._chunk_buffer.strip():
            return
            
        # Step 2: Create streaming bubble if this is the first chunk
        if not hasattr(self, '_current_streaming_bubble') or self._current_streaming_bubble is None:
            self._create_streaming_bubble()
        
        # Step 3: Accumulate buffered text
        if not hasattr(self, '_streaming_text'):
            self._streaming_text = ""
        self._streaming_text += self._chunk_buffer
        
        # Step 4: Update display with accumulated text
        if hasattr(self, '_streaming_label') and self._streaming_label:
            self._streaming_label.setText(self._streaming_text)
        
        # Step 5: Clear buffer and scroll to show new content
        self._chunk_buffer = ""
        self._scroll_to_bottom()

    # Create a new message bubble specifically for displaying streaming content
    def _create_streaming_bubble(self) -> None:
        # Step 1: Create widget container for streaming bubble
        self._current_streaming_bubble = QWidget()
        bubble_layout = QHBoxLayout(self._current_streaming_bubble)
        bubble_layout.setContentsMargins(10, 5, 10, 5)
        
        # Step 2: Create styled bubble frame (similar to MessageBubble but simpler)
        bubble = QFrame()
        bubble.setMaximumWidth(600)
        bubble.setStyleSheet("""
            background-color: #f1f3f4;
            color: #333333;
            border-radius: 18px;
            padding: 12px 16px;
            margin: 4px;
            border: 1px solid #e0e0e0;
        """)
        
        # Step 3: Create inner layout for bubble content
        bubble_inner_layout = QVBoxLayout(bubble)
        bubble_inner_layout.setContentsMargins(8, 8, 8, 8)
        
        # Step 4: Create label that will be updated with streaming chunks
        self._streaming_label = QLabel("")
        self._streaming_label.setWordWrap(True)
        self._streaming_label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self._streaming_label.setStyleSheet("font-size: 20pt; color: #333333;")
        
        # Step 5: Assemble bubble components
        bubble_inner_layout.addWidget(self._streaming_label)
        bubble_layout.addWidget(bubble)
        bubble_layout.addStretch()
        
        # Step 6: Add to messages layout and initialize text accumulator
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, self._current_streaming_bubble)
        self._streaming_text = ""

    # Handle a normal single response from the model
    def _on_response(self, reply: str) -> None:
        # Step 1: Define response processing function
        def proceed():
            # Clean up thinking bubble if it exists
            if self._current_thinking_bubble:
                self._current_thinking_bubble.stop_animation()
                self.messages_layout.removeWidget(self._current_thinking_bubble)
                self._current_thinking_bubble.deleteLater()
                self._current_thinking_bubble = None
            self._display_response(reply)

        # Step 2: Apply slowdown delay if required, otherwise proceed immediately
        self._maybe_delay_then(proceed)

    # Handle one of two A/B test responses and show comparison dialog when both are ready
    def _on_ab_response(self, reply: str, version: str) -> None:
        # Step 1: Store response and increment ready counter
        self.ab_responses[version] = reply
        self.ab_responses_ready += 1
        
        # Step 2: Show comparison dialog when both responses are ready
        if self.ab_responses_ready == 2:
            def proceed():
                # Clean up thinking bubble
                if self._current_thinking_bubble:
                    self._current_thinking_bubble.stop_animation()
                    self.messages_layout.removeWidget(self._current_thinking_bubble)
                    self._current_thinking_bubble.deleteLater()
                    self._current_thinking_bubble = None
                self._show_ab_dialog(self.ab_responses['A'], self.ab_responses['B'])
            self._maybe_delay_then(proceed)

    # Display A/B testing comparison dialog and handle user selection
    def _show_ab_dialog(self, content_a: str, content_b: str) -> None:
        # Step 1: Create and show A/B testing dialog
        dialog = ABTestingDialog(response_a=content_a, response_b=content_b, parent=self)
        
        # Step 2: Process user selection if dialog was accepted
        if dialog.exec() == QDialog.Accepted:
            sel = dialog.selected_version or 'A'
            test_type = "ui_test" if content_a == content_b else "content_test"

            # Step 3: Find the original user message for logging
            original_message = ""
            for msg in reversed(self.history):
                if msg.get("role") == "user":
                    original_message = msg.get("content", "")
                    break

            # Step 4: Log the A/B test results
            log_ab_trial(
                message_content=original_message,
                option_a=content_a,
                option_b=content_b,
                selected=sel,
                latency_ms=dialog.selection_latency,
                test_type=test_type
            )

            # Step 5: Record selection and display chosen response
            self._last_ab_choice = sel
            self.add_system_message(f"You selected Option {sel}")

            if sel == 'A':
                self._display_response(dialog.selected_response or content_a)
            else:
                self.add_message(dialog.selected_response or content_b, is_user=False)
                self._finish_response(dialog.selected_response or content_b)
        else:
            # Step 6: Default to Option A if dialog was cancelled
            self._display_response(content_a)

    # Display the assistant's response with appropriate visual effects
    def _display_response(self, reply: str, is_option_b: bool = False) -> None:
        # Step 1: Handle streaming completion if streaming was used
        if is_enabled(FeatureFlag.STREAMING) and hasattr(self, '_current_streaming_bubble') and self._current_streaming_bubble is not None:
            # Streaming already created the bubble, just clean up and finish
            self._current_streaming_bubble = None  # Mark as complete
            self._finish_response(reply)
            return
        
        # Step 2: Handle typewriter effect if enabled
        if is_enabled(FeatureFlag.TYPEWRITER):
            if '```' in reply:
                # Contains code blocks - show normally to avoid formatting issues
                self.add_message(reply, is_user=False)
                self._finish_response(reply)
            else:
                # Simple text - create typewriter effect
                self._typebuf = reply
                self._typeidx = 0
                
                # Create simple bubble for typewriter display
                self._current_typing_bubble = QWidget()
                bubble_layout = QHBoxLayout(self._current_typing_bubble)
                bubble_layout.setContentsMargins(10, 5, 10, 5)
                
                # Create bubble frame
                bubble = QFrame()
                bubble.setMaximumWidth(600)
                bubble.setStyleSheet("""
                    background-color: #f1f3f4;
                    color: #333333;
                    border-radius: 18px;
                    padding: 12px 16px;
                    margin: 4px;
                    border: 1px solid #e0e0e0;
                """)
                
                bubble_inner_layout = QVBoxLayout(bubble)
                bubble_inner_layout.setContentsMargins(8, 8, 8, 8)
                
                # Create label for typewriter text
                self._typing_label = QLabel("")
                self._typing_label.setWordWrap(True)
                self._typing_label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
                self._typing_label.setTextFormat(Qt.RichText)
                self._typing_label.setStyleSheet("font-size: 20pt; color: #333333;")
                
                # Assemble and start typewriter effect
                bubble_inner_layout.addWidget(self._typing_label)
                bubble_layout.addWidget(bubble)
                bubble_layout.addStretch()
                
                self.messages_layout.insertWidget(self.messages_layout.count() - 1, self._current_typing_bubble)
                
                # UPDATED: Use A/B configurable typewriter speed
                typewriter_speed = get_setting_value('typewriter_speed_ms', is_option_b)
                if typewriter_speed is None:
                    typewriter_speed = 50 if is_option_b else 20  # B-side default vs A-side default
                
                self._typetimer = QTimer(self)
                self._typetimer.timeout.connect(self._type_step)
                self._typetimer.start(typewriter_speed)  # Use A/B configurable speed
        else:
            # Step 3: No special effects - show message immediately
            self.add_message(reply, is_user=False)
            self._finish_response(reply)

    # Add one character to the typewriter effect display
    def _type_step(self) -> None:
        # Step 1: Add next character if available
        if self._typeidx < len(self._typebuf):
            current_text = self._typebuf[: self._typeidx + 1]
            
            # Convert markdown to HTML and update display
            if self._typing_label:
                temp_bubble = MessageBubble("", is_user=False)
                html_content = temp_bubble._markdown_to_html(current_text)
                self._typing_label.setText(html_content)
            
            self._typeidx += 1
            self._scroll_to_bottom()
        else:
            # Step 2: Complete typewriter effect
            if self._typetimer:
                self._typetimer.stop()
                self._typetimer = None
            
            # Step 3: Replace temporary typing bubble with full MessageBubble
            if self._current_typing_bubble:
                self.messages_layout.removeWidget(self._current_typing_bubble)
                self._current_typing_bubble.deleteLater()
                self._current_typing_bubble = None
                self._typing_label = None
            
            # Step 4: Add final formatted message
            self.add_message(self._typebuf, is_user=False)
            self._finish_response(self._typebuf)

    def _show_survey(self):
        """Loads, shows, and logs the results of a survey."""
        from feature_flags import feature_settings
        import json

        filename = feature_settings.get('survey_filename', 'survey.json')
        survey_path = Path(__file__).parent / filename

        if not survey_path.exists():
            log.warning(f"Survey file not found: {filename}. Skipping survey.")
            return

        try:
            with open(survey_path, 'r', encoding='utf-8') as f:
                questions = json.load(f)
            
            dialog = SurveyDialog(questions, self)
            if dialog.exec() == QDialog.Accepted and dialog.results:
                # --- START MODIFICATION ---
                from data_logger import log_survey_responses
                # We now call our new logger function instead of just printing
                log_survey_responses(self.count, dialog.results)
                # --- END MODIFICATION ---

        except Exception as e:
            log.error(f"Failed to load or process survey {filename}: {e}")

    # Complete response processing and prepare for next user input
    def _finish_response(self, reply: str) -> None:
        ab_choice = self._last_ab_choice
        is_ab_message = bool(ab_choice)
        log_message("assistant", reply, had_ab_test=is_ab_message, ab_selection=ab_choice)
        
        self._last_ab_choice = None
        self.ab_responses = None
        
        self.history.append({"role": "assistant", "content": reply})
        self.count += 1
        self.assistant_message_count += 1

        # If running from a blueprint, handle block progression
        if self.experiment_plan:
            self.messages_in_current_block += 1
            current_block = self.experiment_plan[self.current_block_index]
            duration = current_block.get("duration_messages", 10)
            
            if self.messages_in_current_block >= duration:
                # Time to move to the next block
                self._start_next_block()
            
            # --- FIX: MOVED UP FROM THE BOTTOM ---
            # Re-enable input controls before exiting
            self.input_field.setEnabled(True)
            self.input_field.setFocus()
            self.send_button.setEnabled(True)
            if hasattr(self, "search_button") and self.search_button is not None:
                self.search_button.setEnabled(True)
            # --- END FIX ---
            
            # When in blueprint mode, we are done with this turn.
            return

        # --- Standard Mode: Check for other dynamic features ---
        if is_enabled(FeatureFlag.INTER_TRIAL_SURVEY):
            from feature_flags import feature_settings
            trigger_count = feature_settings.get('survey_trigger_count', 5)
            if self.assistant_message_count > 0 and self.assistant_message_count % trigger_count == 0:
                QTimer.singleShot(1000, self._show_survey)

        self._must_slow_turn = False
        self._earliest_display_ts = None

        if self._check_auto_end_conditions():
            return

        if is_enabled(FeatureFlag.BLOCK_MSGS):
            message_threshold = get_setting_value('block_message_count', False)
            repeat_blocking = get_setting_value('block_repeat', False)
            if message_threshold is None: message_threshold = 5
            if repeat_blocking is None: repeat_blocking = True
            if repeat_blocking:
                if self.count > 0 and self.count % message_threshold == 0:
                    self._start_block(); return
            else:
                if self.count == message_threshold:
                    self._start_block(); return

        # This block is now only reached in Standard Mode
        self.input_field.setEnabled(True)
        self.input_field.setFocus()
        self.send_button.setEnabled(True)
        if hasattr(self, "search_button") and self.search_button is not None:
            self.search_button.setEnabled(True)

    def _apply_block_config(self, block_data: dict):
        """Resets and applies the features and settings for a given experiment block."""
        from feature_flags import feature_settings

        log.info(f"Applying config for block: {block_data.get('name')}")

        # 1. Reset all feature flags to False
        for flag in FeatureFlag:
            enabled_features[flag] = False

        # 2. Enable the features specified in the blueprint for this block
        active_features = block_data.get("features", {})
        for feature_name, is_active in active_features.items():
            try:
                flag = FeatureFlag[feature_name]
                enabled_features[flag] = is_active
            except KeyError:
                log.warning(f"Blueprint contains unknown feature: {feature_name}")

        # 3. Update the global settings with the values from this block
        block_settings = block_data.get("settings", {})
        feature_settings.update(block_settings)

        # 4. Re-initialize any chat window components that depend on these settings
        self._apply_text_size()
        self._setup_erase_history_timer() # This will start/stop the timer as needed

        # 5. Finally, update the chat title from the block's name
        block_name = block_data.get("name", "Chat")
        self.setWindowTitle(block_name) # Use setWindowTitle directly to avoid the system message
        log.info(f"Chat title changed to: {block_name}")

    # Temporarily disable message sending and start countdown timer
    def _start_block(self) -> None:
        # Step 1: Get block duration from A-side settings (session control)
        block_duration = get_setting_value('block_duration_s', False)  # A-side for session control
        if block_duration is None:
            block_duration = 15  # Fallback
        
        # Step 2: Initialize blocking state and show notification
        self.blocking = True
        self.add_system_message(f"Blocking for {block_duration}s...")
        self.remaining = block_duration
        
        # Step 3: Set up countdown timer
        self.block_timer = QTimer(self)
        self.block_timer.timeout.connect(self._update_countdown)
        self.block_timer.start(1000)  # Update every second
        
        # Step 4: Disable input controls
        self.input_field.setEnabled(False)
        self.send_button.setEnabled(False)

    # Update the blocking countdown and re-enable controls when complete
    def _update_countdown(self) -> None:
        # Step 1: Continue countdown if time remaining
        if self.remaining > 0:
            self.add_system_message(f"{self.remaining}s...")
            self.remaining -= 1
        else:
            # Step 2: Complete blocking period
            self.block_timer.stop()
            self.add_system_message("You may type now.")
            self.blocking = False
            
            # Step 3: Re-enable all input controls
            self.input_field.setEnabled(True)
            self.send_button.setEnabled(True)
            if hasattr(self, "search_button") and self.search_button is not None:
                self.search_button.setEnabled(True)

    # Handle API errors by cleaning up and re-enabling controls
    def _on_error(self, msg: str) -> None:
        # Step 1: Clean up thinking bubble if active
        if self._current_thinking_bubble:
            self._current_thinking_bubble.stop_animation()
            self.messages_layout.removeWidget(self._current_thinking_bubble)
            self._current_thinking_bubble.deleteLater()
            self._current_thinking_bubble = None
        
        # Step 2: Show error message to user
        self.add_system_message(f"ERROR: {msg}")
        
        # Step 3: Re-enable input controls for retry
        self.input_field.setEnabled(True)
        self.send_button.setEnabled(True)
        if hasattr(self, "search_button") and self.search_button is not None:
            self.search_button.setEnabled(True)

    # Handle UI A/B test responses where both options have identical content
    def _on_ui_ab_response(self, reply: str) -> None:
        # Step 1: Define UI test processing function
        def proceed():
            # Clean up thinking bubble
            if self._current_thinking_bubble:
                self._current_thinking_bubble.stop_animation()
                self.messages_layout.removeWidget(self._current_thinking_bubble)
                self._current_thinking_bubble.deleteLater()
                self._current_thinking_bubble = None
            
            # Step 2: Show UI comparison dialog with identical content
            dialog = ABTestingDialog(response_a=reply, response_b=reply, parent=self)
            if dialog.exec() == QDialog.Accepted:
                sel = dialog.selected_version or 'A'
                test_type = "ui_test"

                # Step 3: Find original user message for logging
                original_message = ""
                for msg in reversed(self.history):
                    if msg.get("role") == "user":
                        original_message = msg.get("content", "")
                        break

                # Step 4: Log UI test results
                log_ab_trial(
                    message_content=original_message,
                    option_a=reply,
                    option_b=reply,
                    selected=sel,
                    latency_ms=dialog.selection_latency,
                    test_type=test_type
                )

                # Step 5: Record selection and display response
                self._last_ab_choice = sel
                self.add_system_message(f"You selected Option {sel}")
                self.add_message(reply, is_user=False)
                self._finish_response(reply)
            else:
                # Step 6: Default to showing response if dialog cancelled
                self.add_message(reply, is_user=False)
                self._finish_response(reply)
        
        # Step 7: Apply slowdown delay if required
        self._maybe_delay_then(proceed)

    # === START NEW AB_UI_ALT WORKFLOW METHODS ===

    def _start_ab_ui_alt_workflow(self, prompt: str) -> None:
        """
        Starts the sequential A/B UI Alt workflow.
        Step 1: Get the base response (Option A).
        """
        # Create Thread A to get the base response
        self.thread_a = ChatThread(self.history, prompt, use_features=True)
        
        # Connect its result to the rephrasing function
        self.thread_a.result_ready.connect(self._on_base_response_for_alt_ui)
        self.thread_a.error.connect(self._on_error)
        self._start_and_track(self.thread_a)

    def _on_base_response_for_alt_ui(self, base_reply: str) -> None:
        """
        Received Option A.
        Step 2: Send Option A back to the API to be rephrased into Option B.
        """

        # This is the special rephrasing instruction
        rephrase_prompt = (
            "Please paraphrase the following text. Maintain the core information, "
            "tone, and approximate length, but use different wording and sentence structure. "
            "Do not add any commentary before or after the rephrased text. Just provide the rephrased text directly."
            f"\n\nORIGINAL TEXT:\n---\n{base_reply}"
        )

        # Create Thread B. We pass an empty history and disable features 
        # to ensure it's a "clean" rephrasing task.
        self.thread_b = ChatThread(history=[], prompt=rephrase_prompt, use_features=False)
        
        # We must use a lambda function here to pass BOTH responses to the final handler
        self.thread_b.result_ready.connect(
            lambda rephrased_reply: self._on_rephrased_response_for_alt_ui(base_reply, rephrased_reply)
        )
        self.thread_b.error.connect(self._on_error)
        self._start_and_track(self.thread_b)

    def _on_rephrased_response_for_alt_ui(self, base_reply: str, rephrased_reply: str) -> None:
        """
        Received Option B (the rephrased text).
        Step 3: Show both Option A and Option B in the dialog.
        """
        # Define the function to proceed (this allows our slowdown logic to work)
        def proceed():
            # Clean up the "thinking" bubble
            if self._current_thinking_bubble:
                self._current_thinking_bubble.stop_animation()
                self.messages_layout.removeWidget(self._current_thinking_bubble)
                self._current_thinking_bubble.deleteLater()
                self._current_thinking_bubble = None
            
            # Show the comparison dialog with the original and the paraphrase
            self._show_ab_dialog(base_reply, rephrased_reply)

        # Apply slowdown delay if required, otherwise proceed immediately
        self._maybe_delay_then(proceed)

    # === END NEW AB_UI_ALT WORKFLOW METHODS ===

    def _handle_scripted_ab_turn(self, reply_a: str, reply_b: str):
        """
        Handles a scripted A/B test. This respects slowdown logic
        and then shows the A/B dialog with the pre-scripted content.
        """
        def proceed():
            # Clean up the "thinking" bubble
            if self._current_thinking_bubble:
                self._current_thinking_bubble.stop_animation()
                self.messages_layout.removeWidget(self._current_thinking_bubble)
                self._current_thinking_bubble.deleteLater()
                self._current_thinking_bubble = None
            
            # Show the comparison dialog with our two scripted responses
            self._show_ab_dialog(reply_a, reply_b)

        # Apply slowdown delay if required, otherwise proceed immediately
        self._maybe_delay_then(proceed)

    # Send message with web search functionality enabled
    def send_with_web_search(self) -> None:
        # Step 1: Get and validate user input
        txt = self.input_field.text().strip()
        if not txt:
            return

        # Step 2: Log user message
        log_message("user", txt)

        # Step 3: Display message and update conversation
        self.add_message(txt, is_user=True)
        self.history.append({"role": "user", "content": txt})
        
        # Step 4: Clear input and disable controls
        self.input_field.clear()
        self.input_field.setEnabled(False)
        self.send_button.setEnabled(False)
        self.search_button.setEnabled(False)

        # Step 5: Capture send timestamp
        sent_ts = time.time()

        # Step 6: Apply delay before web search if enabled (A-side for user actions)
        if is_enabled(FeatureFlag.DELAY_BEFORE_SEND):
            delay_seconds = get_setting_value('delay_seconds', False)
            if delay_seconds is None:
                delay_seconds = 2  # Fallback
            self.add_system_message(f"Processing web search... ({delay_seconds}s delay)")
            QTimer.singleShot(delay_seconds * 1000, lambda ts=sent_ts: self._web_search_after_delay(txt, ts))
        else:
            self._web_search_after_delay(txt, sent_ts)

    # Execute web search after any configured delay
    def _web_search_after_delay(self, txt: str, sent_ts: float) -> None:
        # Step 1: Prepare slowdown settings
        self._prepare_turn_slowdown(sent_ts)
        
        # Step 2: Show thinking animation if enabled
        if is_enabled(FeatureFlag.THINKING):
            self._start_thinking()

        # Step 3: Create and start web search thread
        web_thread = ChatThread(self.history, txt, use_features=True, force_web_search=True)
        web_thread.result_ready.connect(self._on_response)
        web_thread.error.connect(self._on_error)
        self._start_and_track(web_thread)

    # Export data, show debrief, and cleanly close the chat session
    def _end_chat(self) -> None:
        # Step 1: Mark session end for accurate duration tracking
        try:
            data_logger.mark_session_end()
        except Exception:
            pass

        # Step 2: Export conversation data
        try:
            export_data()
            self.add_system_message("Data exported. Thank you for participating.")
        except Exception as e:
            self.add_system_message(f"Export error: {e}")

        # Step 3: Show debrief dialog to user
        dlg = DebriefDialog(self)
        dlg.exec()

        # Step 4: Clean up all background worker threads
        for thr in list(self._threads):
            try:
                if thr.isRunning():
                    thr.quit()
                    thr.wait(2000)
            except Exception:
                pass

        # Step 5: Close the chat window
        self.close()

    # Clean up timers when window is being closed
    def closeEvent(self, event) -> None:
        # Step 1: Clean up all timers to prevent memory leaks
        self._cleanup_timers()
        
        # Step 2: Call parent close event
        super().closeEvent(event)

    # Stop all running timers to prevent memory leaks and crashes
    def _cleanup_timers(self) -> None:
        # Step 1: Stop typewriter timer
        if hasattr(self, '_typetimer') and self._typetimer:
            self._typetimer.stop()
            self._typetimer = None
        
        # Step 2: Stop auto-end timer
        if hasattr(self, 'auto_end_timer') and self.auto_end_timer:
            self.auto_end_timer.stop()
            self.auto_end_timer = None
        
        # Step 3: Stop blocking timer
        if hasattr(self, 'block_timer') and self.block_timer:
            self.block_timer.stop()
            self.block_timer = None
        
        # Step 4: Clean up thinking bubble
        if hasattr(self, '_current_thinking_bubble') and self._current_thinking_bubble:
            self._current_thinking_bubble.stop_animation()
            self._current_thinking_bubble = None
        
        # Step 5: Stop erase history timer
        if hasattr(self, 'erase_timer') and self.erase_timer:
            self.erase_timer.stop()
            self.erase_timer = None

# ==============================================================================
# — Feature Selection Control Panel —
# ==============================================================================

class ControlPanel(QWidget):
    
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ControlPanel")
        self.current_theme_name = load_theme_preference()
        app = QApplication.instance()
        if app:
            app.setEffectEnabled(Qt.UIEffect.UI_AnimateTooltip, False)
            app.setEffectEnabled(Qt.UIEffect.UI_FadeTooltip, False)
        
        self._build_ui()
        self._update_feature_progress(None, False)

    def _build_ui(self) -> None:
        self.setWindowTitle("Control Panel")
        self.resize(900, 700)
        
        # Load saved theme or default
        theme = get_theme(self.current_theme_name)
        self.setStyleSheet(f"""
            #ControlPanel {{
                background: {theme['background']};
                font-family: 'Segoe UI', Arial, sans-serif;
            }}
        """)

        container = QFrame(self)
        container.setObjectName("controlCard")
        container.setStyleSheet("""
            #controlCard {
                background: rgba(255, 255, 255, 0.15);
                border: 1px solid rgba(255, 255, 255, 0.5);
                border-radius: 20px;
                backdrop-filter: blur(10px);
            }
        """)
        
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(30)
        shadow.setXOffset(0)
        shadow.setYOffset(10)
        shadow.setColor(QColor(0,0,0, 150))
        container.setGraphicsEffect(shadow)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # Create a header layout to hold both title and theme button
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        # Add stretch to center the title
        header_layout.addStretch()
        
        header = QLabel("Feature Control Panel", alignment=Qt.AlignCenter)
        header.setStyleSheet("""
            QLabel {
                font-size: 28pt;
                font-weight: 700;
                color: white;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
                margin-bottom: 8px;
                background: transparent;
            }
        """)
        header_layout.addWidget(header)
        
        # Add stretch and theme button on the right
        header_layout.addStretch()
        
        # Create simple "Theme" text button
        self.theme_btn = QPushButton("Theme")
        self.theme_btn.setFixedSize(80, 35)
        self.theme_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.15);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.4);
                border-radius: 8px;
                font-size: 11pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.25);
                border: 1px solid rgba(255, 255, 255, 0.6);
            }
        """)
        self.theme_btn.clicked.connect(self._show_theme_menu)
        header_layout.addWidget(self.theme_btn)
        
        layout.addLayout(header_layout)

        # Create theme menu (initially hidden)
        self.theme_menu = QWidget(self)
        self.theme_menu.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.theme_menu.setAttribute(Qt.WA_TranslucentBackground)
        self.theme_menu.setStyleSheet("""
            QWidget {
                background: rgba(40, 40, 40, 0.95);
                border: 2px solid rgba(255, 255, 255, 0.8);
                border-radius: 12px;
            }
        """)

        theme_menu_layout = QVBoxLayout(self.theme_menu)
        theme_menu_layout.setContentsMargins(10, 10, 10, 10)
        theme_menu_layout.setSpacing(5)

        # Add theme buttons directly to menu (no title or separator)
        for theme_name, theme_colors in THEMES.items():
            theme_btn = QPushButton(theme_name)
            theme_btn.setFixedHeight(45)
            
            is_active = (theme_name == self.current_theme_name)
            border_style = "3px solid white" if is_active else "1px solid rgba(255, 255, 255, 0.3)"
            
            theme_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {theme_colors['background']};
                    color: white;
                    border: {border_style};
                    border-radius: 8px;
                    padding: 8px;
                    font-size: 11pt;
                    font-weight: bold;
                    text-align: left;
                    padding-left: 15px;
                    text-shadow: 1px 1px 2px rgba(0,0,0,0.7);
                }}
                QPushButton:hover {{
                    border: 2px solid white;
                }}
            """)
            theme_btn.clicked.connect(lambda checked, name=theme_name: self._select_theme(name))
            theme_menu_layout.addWidget(theme_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                border-radius: 10px;
                background: rgba(255, 255, 255, 0.2);
                text-align: center;
                font-weight: bold;
                color: white;
                height: 20px;
            }}
            QProgressBar::chunk {{
                border-radius: 10px;
                background: {theme['progress_bar']};
            }}
        """)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        layout.addSpacing(16)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: rgba(0, 0, 0, 0.1);
                width: 12px;
                border-radius: 6px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.4);
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 0.7);
            }
            QScrollBar:vertical:!enabled {
                background: transparent;
            }
        """)

        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background: transparent;")
        self.sections_layout = QVBoxLayout(scroll_widget)
        self.sections_layout.setSpacing(0)

        flag_to_group_map = {}
        for group_title, flag_list in FEATURE_GROUPS.items():
            for flag_name in flag_list:
                flag_to_group_map[flag_name] = group_title
        
        self.sections = {title: CollapsibleSection(title) for title in FEATURE_GROUPS}
        self.sections["Other"] = CollapsibleSection("Other Features")

        self.feature_buttons = {}
        
        for flag in FeatureFlag:
            btn = self._create_modern_feature_button(flag)
            self.feature_buttons[flag] = btn
            group_title = flag_to_group_map.get(flag.name, "Other")
            self.sections[group_title].addButton(btn)

        for group_title in FEATURE_GROUPS:
            section = self.sections[group_title]
            if section.button_count > 0:
                section.finalize_grid()
                self.sections_layout.addWidget(section)
        
        other_section = self.sections["Other"]
        if other_section.button_count > 0:
            other_section.finalize_grid()
            self.sections_layout.addWidget(other_section)

        self.sections_layout.addStretch(1)
        
        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area, 1)

        cont = QPushButton("Continue to Chat")
        cont.setObjectName("cont_btn")  # Add object name for theme updates
        cont.setFixedHeight(50)
        cont.setStyleSheet(f"""
            QPushButton {{
                background: {theme['button_gradient']};
                color: white;
                border: none;
                border-radius: 25px;
                font-size: 16pt;
                font-weight: bold;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                background: {theme['button_hover']};
                transform: translateY(-2px);
            }}
            QPushButton:pressed {{
                background: {theme['button_gradient']};
            }}
        """)
        cont.clicked.connect(self._start_chat)
        layout.addWidget(cont)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(container, stretch=1)
        main_layout.setContentsMargins(40, 40, 40, 40)

    def _show_theme_menu(self):
        """Show the theme selection popup menu."""
        # Position the menu below the Theme button
        btn_pos = self.theme_btn.mapToGlobal(self.theme_btn.rect().bottomRight())
        self.theme_menu.move(btn_pos.x() - self.theme_menu.width() + 20, btn_pos.y() + 5)
        self.theme_menu.show()

    def _select_theme(self, theme_name):
        """Select a theme and close the menu."""
        self._apply_theme(theme_name)
        self.theme_menu.close()
        
        # Update the menu buttons to show new active theme
        for btn in self.theme_menu.findChildren(QPushButton):
            if btn.text() in THEMES:
                btn_theme = THEMES[btn.text()]
                is_active = (btn.text() == theme_name)
                border_style = "3px solid white" if is_active else "1px solid rgba(255, 255, 255, 0.3)"
                
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {btn_theme['background']};
                        color: white;
                        border: {border_style};
                        border-radius: 8px;
                        padding: 8px;
                        font-size: 11pt;
                        font-weight: bold;
                        text-align: left;
                        padding-left: 15px;
                        text-shadow: 1px 1px 2px rgba(0,0,0,0.7);
                    }}
                    QPushButton:hover {{
                        border: 2px solid white;
                    }}
                """)

    def _apply_theme(self, theme_name):
        """Apply a theme and save the preference."""
        self.current_theme_name = theme_name
        save_theme_preference(theme_name)
        theme = get_theme(theme_name)
        
        # Update main background
        self.setStyleSheet(f"""
            QWidget {{
                background: {theme['background']};
                font-family: 'Segoe UI', Arial, sans-serif;
            }}
        """)
        
        # Update progress bar
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                border-radius: 10px;
                background: rgba(255, 255, 255, 0.2);
                text-align: center;
                font-weight: bold;
                color: white;
                height: 20px;
            }}
            QProgressBar::chunk {{
                border-radius: 10px;
                background: {theme['progress_bar']};
            }}
        """)
        
        # Update continue button
        cont_btn = self.findChild(QPushButton, "cont_btn")
        if cont_btn:
            cont_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {theme['button_gradient']};
                    color: white;
                    border: none;
                    border-radius: 25px;
                    font-size: 16pt;
                    font-weight: bold;
                    text-transform: uppercase;
                    letter-spacing: 1px;
                }}
                QPushButton:hover {{
                    background: {theme['button_hover']};
                }}
            """)
    
    def eventFilter(self, obj, event):
        global current_tooltip
        
        if event.type() == event.Type.Enter:
            if hasattr(obj, 'tooltip_text') and obj.tooltip_text:
                if current_tooltip:
                    current_tooltip.hide()
                
                current_tooltip = CustomTooltip(obj.tooltip_text)
                pos = obj.mapToGlobal(obj.rect().bottomRight())
                current_tooltip.move(pos.x() - current_tooltip.width(), pos.y() + 5)
                current_tooltip.show()
            return True
        
        elif event.type() == event.Type.Leave:
            if current_tooltip:
                current_tooltip.hide()
                current_tooltip = None
            return True
        
        return super().eventFilter(obj, event)

    def _create_modern_feature_button(self, flag):
        btn = QPushButton()
        btn.setCheckable(True)
        btn.setChecked(bool(enabled_features.get(flag, False)))
        btn.setMinimumHeight(70)
        
        btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        
        button_layout = QHBoxLayout(btn)
        button_layout.setContentsMargins(12, 8, 8, 8)
        
        # Create the feature label
        feature_label = QLabel(flag.name.replace('_', ' ').title())
        feature_label.setStyleSheet("color: white; font-size: 11pt; font-weight: bold; background: transparent;")
        feature_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        # --- SIMPLIFIED ICON APPROACH ---
        # Create a single label that acts as both the icon and its background
        icon_widget = QLabel("🔍")
        icon_widget.setFixedSize(20, 20)  # Slightly larger for better visibility
        icon_widget.setAlignment(Qt.AlignCenter)
        icon_widget.setStyleSheet("""
            QLabel {
                background: rgba(255, 255, 255, 0.5);
                border-radius: 10px;
                font-size: 11pt;
                padding: 0px;
                color: rgba(0, 0, 0, 0.8);
            }
            QLabel:hover {
                background: rgba(255, 255, 255, 0.8);
            }
        """)
        
        # Set up tooltip
        icon_widget.tooltip_text = get_feature_tooltip(flag)
        icon_widget.setAttribute(Qt.WA_Hover, True)
        icon_widget.installEventFilter(self)
        
        # If emoji still doesn't work, try this alternative:
        # icon_widget.setText("ℹ")  # Info symbol as fallback
        # or
        # icon_widget.setText("?")  # Question mark as fallback
        
        # Add widgets to button layout
        button_layout.addWidget(feature_label, 0)
        button_layout.addStretch(1)
        button_layout.addWidget(icon_widget, 0)
        
        # Set button styling
        btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                border: 2px solid rgba(255, 255, 255, 0.6);
                border-radius: 12px;
                text-align: left;
                min-width: 160px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.2);
                border: 2px solid rgba(255, 255, 255, 0.9);
            }
            QPushButton:checked {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #11998e, stop:1 #38ef7d);
                border: 2px solid #11998e;
            }
            QPushButton:checked:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0f8a7e, stop:1 #32d96f);
            }
        """)
        
        # Connect toggle signal
        btn.toggled.connect(lambda checked, f=flag: self._update_feature_progress(f, checked))
        
        return btn

    def _update_feature_progress(self, flag, checked):
        if flag is not None:
            enabled_features[flag] = checked
        
        enabled_count = sum(1 for enabled in enabled_features.values() if enabled)
        total_count = len(FeatureFlag)
        
        if total_count > 0:
            progress = int((enabled_count / total_count) * 100)
        else:
            progress = 0
            
        self.progress_bar.setValue(progress)
        self.progress_bar.setFormat(f"{enabled_count}/{total_count} Features Enabled")

    def _features_need_settings(self) -> bool:
        features_with_settings = [
            FeatureFlag.TEXT_SIZE_CHANGER,
            FeatureFlag.DELAY_BEFORE_SEND,
            FeatureFlag.AUTO_END_AFTER_N_MSGS,
            FeatureFlag.AUTO_END_AFTER_T_MIN,
            FeatureFlag.SLOWDOWN,
            FeatureFlag.ERASE_HISTORY,
            FeatureFlag.BLOCK_MSGS,
            FeatureFlag.AB_TESTING,
            FeatureFlag.TYPEWRITER,
            FeatureFlag.SCRIPTED_RESPONSES,
            FeatureFlag.CUSTOM_CHAT_TITLE,
            FeatureFlag.INTER_TRIAL_SURVEY,
            FeatureFlag.DYNAMIC_FEATURE_CHANGING,
        ]
        return any(is_enabled(feature) for feature in features_with_settings if feature in enabled_features)

    def _start_chat(self) -> None:
        if self._features_need_settings():
            settings_dialog = SettingsDialog(self)
            if settings_dialog.exec() != QDialog.Accepted:
                return

        set_features(enabled_features)
        
        try:
            from feature_flags import feature_settings
            from data_logger import set_feature_settings
            set_feature_settings(feature_settings)
        except Exception as e:
            print(f"Error storing feature settings: {e}")
        
        self.hide() 

        sona = SonaIdDialog() 
        if sona.exec() != QDialog.Accepted:
            self.showMaximized()
            return 
        set_participant_info(sona_id=SONA_ID)

        consent = ConsentDialog() 
        if consent.exec() != QDialog.Accepted:
            self.showMaximized()
            return
        set_participant_info(consent=True)
        
        self.chat_window = ChatWindow()
        self.chat_window.showMaximized()

        try:
            self.chat_window.search_button.setVisible(is_enabled(FeatureFlag.WEB_SEARCH))
        except Exception:
            pass

# ==============================================================================
# — TOOL TIPS —
# ==============================================================================

class CustomTooltip(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        
        # Enable transparency so we can draw custom background
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        
        # Style only the text, background will be custom drawn
        self.setStyleSheet("""
            QLabel {
                color: white;
                padding: 12px 16px;
                font-size: 11pt;
                font-family: 'Segoe UI', Arial, sans-serif;
                background: transparent;
            }
        """)
        self.setWordWrap(True)
        self.setMaximumWidth(400)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        
        # Create rounded rectangle path
        path = QPainterPath()
        rect = self.rect()
        path.addRoundedRect(rect, 8, 8)
        
        # Fill background with rounded corners
        background_color = QColor(45, 55, 72, 240)
        painter.fillPath(path, background_color)
        
        # Draw border
        pen = QPen(QColor(255, 255, 255, 77), 1)
        painter.setPen(pen)
        painter.drawPath(path)
        
        # Let parent draw the text on top
        painter.end()  # End custom painting
        
        # Draw text normally
        super().paintEvent(event)

# Global tooltip instance
current_tooltip = None

# ==============================================================================
# — SONA ID Entry Dialog —
# ==============================================================================

# Dialog for entering 6-digit SONA participant ID
class SonaIdDialog(QDialog):
    
    # Initialize SONA ID entry dialog with validation
    def __init__(self, parent=None):
        # Step 1: Initialize parent dialog
        super().__init__(parent)
        self.setWindowTitle("Enter SONA ID")
        self.setMinimumWidth(420)

        # Step 2: Create main layout
        layout = QVBoxLayout(self)

        # Step 3: Add title
        title = QLabel("Enter Your SONA ID")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:16pt;font-weight:bold;margin-bottom:8px;")
        layout.addWidget(title)

        # Step 4: Add instruction
        prompt = QLabel("Please enter your 6-digit SONA ID:")
        layout.addWidget(prompt)

        # Step 5: Create validated input field
        self.input = QLineEdit()
        self.input.setMaxLength(6)  # Hard cap at 6 characters
        # Only allow digits while typing
        rx = QRegularExpression(r"^\d{0,6}$")
        self.input.setValidator(QRegularExpressionValidator(rx, self.input))
        self.input.setPlaceholderText("e.g., 123456")
        layout.addWidget(self.input)

        # Step 6: Add error display label
        self.error = QLabel("")
        self.error.setStyleSheet("color:#b10d2c;font-weight:bold;")
        layout.addWidget(self.error)

        # Step 7: Add buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Begin")
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Step 8: Focus input field
        self.input.setFocus()

    # Validate SONA ID format and save if valid
    def _accept_if_valid(self) -> None:
        # Step 1: Get and validate input
        text = self.input.text().strip()
        if len(text) != 6 or not text.isdigit():
            self.error.setText("SONA ID must be exactly 6 digits.")
            return
        
        # Step 2: Save SONA ID globally and to logger
        global SONA_ID
        SONA_ID = text
        try:
            setattr(data_logger.session, "sona_id", SONA_ID)
            setattr(data_logger.session, "sona_timestamp", time.time())
        except Exception:
            pass
        
        # Step 3: Accept dialog
        self.accept()

# ==============================================================================
# — Consent Form Dialog —
# ==============================================================================

# Dialog for displaying consent form and collecting agreement
class ConsentDialog(QDialog):
    
    # Initialize consent dialog with HTML content viewer
    def __init__(self, parent=None):
        # Step 1: Initialize parent dialog
        super().__init__(parent)
        self.setWindowTitle("Consent Form")
        self.resize(720, 600)

        # Step 2: Create main layout
        layout = QVBoxLayout(self)

        # Step 3: Create HTML viewer for consent form
        self.view = QTextBrowser()
        try:
            consent_path = Path(__file__).parent / "consent.html"
            self.view.setHtml(consent_path.read_text(encoding="utf-8"))
        except Exception:
            self.view.setHtml("<h2>Consent Form</h2><p>(consent.html not found)</p>")
        layout.addWidget(self.view)

        # Step 4: Create agreement buttons
        buttons = QDialogButtonBox()
        agree = buttons.addButton("I Agree", QDialogButtonBox.AcceptRole)
        disagree = buttons.addButton("I Do Not Agree", QDialogButtonBox.RejectRole)
        agree.clicked.connect(self._accept_and_log)
        disagree.clicked.connect(self.reject)
        layout.addWidget(buttons)

    # Log consent agreement and close dialog
    def _accept_and_log(self) -> None:
        # Step 1: Log consent information
        try:
            setattr(data_logger.session, "consented", True)
            setattr(data_logger.session, "consent_timestamp", time.time())
            setattr(data_logger.session, "consent_version", "v1")
        except Exception:
            pass
        
        # Step 2: Accept dialog
        self.accept()

# ==============================================================================
# — Debrief Dialog —
# ==============================================================================

# Dialog for showing post-experiment debrief information
class DebriefDialog(QDialog):
    
    # Initialize debrief dialog with HTML content viewer
    def __init__(self, parent=None):
        # Step 1: Initialize parent dialog
        super().__init__(parent)
        self.setWindowTitle("Debrief")
        self.resize(760, 620)

        # Step 2: Create main layout
        layout = QVBoxLayout(self)

        # Step 3: Create HTML viewer for debrief content
        self.view = QTextBrowser()
        try:
            debrief_path = Path(__file__).parent / "debrief.html"
            self.view.setHtml(debrief_path.read_text(encoding="utf-8"))
        except Exception:
            self.view.setHtml("<h2>Debrief</h2><p>(debrief.html not found)</p>")
        layout.addWidget(self.view)

        # Step 4: Create close button
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("Close")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        buttons.button(QDialogButtonBox.Close).clicked.connect(self.accept)
        layout.addWidget(buttons)

    # Log debrief viewing when dialog is shown
    def showEvent(self, event):
        # Step 1: Log debrief display
        try:
            setattr(data_logger.session, "debrief_shown", True)
            setattr(data_logger.session, "debrief_timestamp", time.time())
        except Exception:
            pass
        
        # Step 2: Call parent show event
        super().showEvent(event)


# ==============================================================================
# — Transition Screen Dialog —
# ==============================================================================

class TransitionDialog(QDialog):
    """A simple, frameless dialog to show a transition message that auto-closes."""
    def __init__(self, message, duration_ms=3000, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setStyleSheet("background-color: #2d3748; border-radius: 15px;")

        layout = QVBoxLayout(self)
        self.label = QLabel(message, self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setWordWrap(True)
        self.label.setStyleSheet("color: white; font-size: 22pt; font-weight: bold; padding: 40px;")
        layout.addWidget(self.label)

        # Automatically close the dialog after the specified duration
        QTimer.singleShot(duration_ms, self.accept)


# ==============================================================================
# — Application Entry Point —
# ==============================================================================

# Main application entry point that orchestrates the complete user flow
if __name__ == "__main__":
    # Step 1: Create Qt application
    app = QApplication(sys.argv)

    # Step 2: Load stylesheet if available
    style_file = Path(__file__).parent / "style.qss"
    if style_file.exists():
        app.setStyleSheet(style_file.read_text())

    # Step 3: Launch feature selection (was Step 5)
    # The panel will now handle SONA and Consent
    panel = ControlPanel()
    panel.showMaximized()

    # Step 4: Start application event loop (was Step 6)
    sys.exit(app.exec())