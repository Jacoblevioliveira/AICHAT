"""
Data logging system for ChatGPT UI A/B testing experiment.
Exports to two CSV files: ab_trials.csv and conversation_transcripts.csv
"""

import csv
import uuid
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import time

# — Structures: A/B trials, messages, and whole session. —
@dataclass
class ABTrialData:
    """Data structure for A/B trial information"""
    trial_number: int
    timestamp: str
    message_content: str
    option_a_content: str
    option_b_content: str
    selected_option: str  # 'A' or 'B'
    selection_latency_ms: int
    test_type: str  # 'ui_test' or 'content_test'

@dataclass
class MessageData:
    """Data structure for individual messages"""
    message_number: int
    timestamp: str
    speaker: str  # 'user', 'assistant', or 'system'
    message_content: str
    had_ab_test: bool = False
    ab_selection: Optional[str] = None

# --- NEW ---
@dataclass
class SurveyResponseData:
    """Data for a single answered question from a survey pop-up."""
    timestamp: str
    after_message_number: int
    question_id: str
    response: str # Could be a number, text, or a list of texts
# --- END NEW ---

@dataclass
class SessionData:
    """Complete session data"""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sona_id: Optional[str] = None
    consent: Optional[bool] = None
    participant_features: Dict = field(default_factory=dict)
    feature_settings: Dict = field(default_factory=dict)
    messages: List[MessageData] = field(default_factory=list)
    ab_trials: List[ABTrialData] = field(default_factory=list)
    survey_responses: List[SurveyResponseData] = field(default_factory=list) # --- NEW ---
    session_start: str = field(default_factory=lambda: datetime.now().isoformat())
    session_end: Optional[str] = None

class DataLogger:
    """Handles all data collection and CSV export for the experiment"""
    
    def __init__(self):
        self.session = SessionData()
        self.message_counter = 0
        self.ab_trial_counter = 0
        print(f"New session started: {self.session.session_id}")
    
    # — Participant metadata setters —
    def set_sona_id(self, sona_id: str):
        self.session.sona_id = sona_id
        print(f"SONA ID set: {sona_id}")
    
    def set_consent(self, consent: bool):
        self.session.consent = consent
        print(f"Consent status: {consent}")
    
    def set_participant_features(self, features: Dict):
        self.session.participant_features = features.copy()
        print(f"Features set: {self.get_features_as_string()}")

    def set_feature_settings(self, settings: Dict):
        self.session.feature_settings = settings.copy()
        print(f"Feature settings set: {self.get_feature_settings_as_string()}")

    # — Core logging —
    def add_message(self, speaker: str, content: str, had_ab_test: bool = False, ab_selection: Optional[str] = None):
        self.message_counter += 1
        message = MessageData(
            message_number=self.message_counter,
            timestamp=datetime.now().isoformat(),
            speaker=speaker,
            message_content=content,
            had_ab_test=had_ab_test,
            ab_selection=ab_selection
        )
        self.session.messages.append(message)
        print(f"Message logged: {speaker} - {content[:50]}{'...' if len(content) > 50 else ''}")
    
    def add_ab_trial(self, message_content: str, option_a: str, option_b: str, 
                     selected: str, latency_ms: int, test_type: str):
        self.ab_trial_counter += 1
        trial = ABTrialData(
            trial_number=self.ab_trial_counter,
            timestamp=datetime.now().isoformat(),
            message_content=message_content,
            option_a_content=option_a,
            option_b_content=option_b,
            selected_option=selected,
            selection_latency_ms=latency_ms,
            test_type=test_type
        )
        self.session.ab_trials.append(trial)
        print(f"A/B trial logged: {test_type} - Selected {selected} - {latency_ms}ms")

    # --- NEW ---
    def add_survey_responses(self, message_num: int, results: Dict):
        """Adds a set of survey responses to the session data."""
        timestamp = datetime.now().isoformat()
        for q_id, response in results.items():
            # Convert list responses (from checkboxes) to a semi-colon separated string
            response_str = ";".join(response) if isinstance(response, list) else str(response)
            
            survey_data = SurveyResponseData(
                timestamp=timestamp,
                after_message_number=message_num,
                question_id=q_id,
                response=response_str
            )
            self.session.survey_responses.append(survey_data)
        print(f"Survey responses logged for message #{message_num}")
    # --- END NEW ---

    # — Session timing helpers —
    def mark_session_end(self):
        self.session.session_end = datetime.now().isoformat()
        print(f"Session ended: {self.session.session_end}")

    def get_chat_duration_seconds(self) -> Optional[int]:
        try:
            start_dt = datetime.fromisoformat(self.session.session_start)
            end_dt = datetime.fromisoformat(self.session.session_end) if self.session.session_end else datetime.now()
            return int((end_dt - start_dt).total_seconds())
        except Exception:
            return None
    
    # — Formatting helpers —
    def get_features_as_string(self) -> str:
        if not self.session.participant_features: return ""
        feature_parts = []
        for feature_name, is_enabled in self.session.participant_features.items():
            name = feature_name.name if hasattr(feature_name, 'name') else str(feature_name)
            value = 1 if is_enabled else 0
            feature_parts.append(f"{name}:{value}")
        return ",".join(feature_parts)
    
    def get_feature_settings_as_string(self) -> str:
        if not self.session.feature_settings: return ""
        settings_parts = []
        for setting_name, setting_value in self.session.feature_settings.items():
            settings_parts.append(f"{setting_name}:{setting_value}")
        return ",".join(settings_parts)
    
    # — Export —
    def export_to_csv(self, output_dir: Path = None):
        if output_dir is None:
            output_dir = Path(__file__).parent / "experiment_data"
        output_dir.mkdir(exist_ok=True)
        
        participant_num = self._get_next_participant_number(output_dir)
        print(f"Exporting data for session {self.session.session_id} as Participant {participant_num}...")
        
        ab_trials_path = output_dir / f"Participant {participant_num} AB Trials.csv"
        transcripts_path = output_dir / f"Participant {participant_num} Transcript.csv"
        
        self._export_ab_trials(ab_trials_path)
        print(f"A/B trials exported to: {ab_trials_path}")
        
        self._export_transcripts(transcripts_path)
        print(f"Transcripts exported to: {transcripts_path}")
        
        # --- NEW ---
        if self.session.survey_responses:
            survey_path = output_dir / f"Participant {participant_num} Survey Responses.csv"
            self._export_survey_responses(survey_path)
            print(f"Survey responses exported to: {survey_path}")
        # --- END NEW ---
        
        print(f"Export complete. Messages: {len(self.session.messages)}, A/B Trials: {len(self.session.ab_trials)}")
        return participant_num
    
    def _get_next_participant_number(self, output_dir: Path) -> int:
        participant_num = 1
        while True:
            ab_trials_path = output_dir / f"Participant {participant_num} AB Trials.csv"
            transcripts_path = output_dir / f"Participant {participant_num} Transcript.csv"
            if not ab_trials_path.exists() and not transcripts_path.exists():
                return participant_num
            participant_num += 1
            if participant_num > 10000:
                raise RuntimeError("Too many participants! Check your data directory.")

    def _export_ab_trials(self, filepath: Path):
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            # ... (this method is unchanged) ...
            fieldnames = [
                'session_id', 'sona_id', 'consent', 'participant_features', 'feature_settings',
                'session_start', 'session_end', 'chat_duration_seconds',
                'timestamp', 'trial_number', 'message_content', 'option_a_content',
                'option_b_content', 'selected_option', 'selection_latency_ms', 'test_type'
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for trial in self.session.ab_trials:
                writer.writerow({
                    'session_id': self.session.session_id, 'sona_id': self.session.sona_id or '',
                    'consent': self.session.consent if self.session.consent is not None else '',
                    'participant_features': self.get_features_as_string(),
                    'feature_settings': self.get_feature_settings_as_string(),
                    'session_start': self.session.session_start, 'session_end': self.session.session_end or '',
                    'chat_duration_seconds': self.get_chat_duration_seconds() or '',
                    'timestamp': trial.timestamp, 'trial_number': trial.trial_number,
                    'message_content': trial.message_content, 'option_a_content': trial.option_a_content,
                    'option_b_content': trial.option_b_content, 'selected_option': trial.selected_option,
                    'selection_latency_ms': trial.selection_latency_ms, 'test_type': trial.test_type
                })
    
    def _export_transcripts(self, filepath: Path):
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            # ... (this method is unchanged) ...
            fieldnames = [
                'session_id', 'sona_id', 'consent', 'participant_features', 'feature_settings',
                'session_start', 'session_end', 'chat_duration_seconds',
                'message_number', 'timestamp', 'speaker', 'message_content',
                'had_ab_test', 'ab_selection'
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for message in self.session.messages:
                writer.writerow({
                    'session_id': self.session.session_id, 'sona_id': self.session.sona_id or '',
                    'consent': self.session.consent if self.session.consent is not None else '',
                    'participant_features': self.get_features_as_string(),
                    'feature_settings': self.get_feature_settings_as_string(),
                    'session_start': self.session.session_start, 'session_end': self.session.session_end or '',
                    'chat_duration_seconds': self.get_chat_duration_seconds() or '',
                    'message_number': message.message_number, 'timestamp': message.timestamp,
                    'speaker': message.speaker, 'message_content': message.message_content,
                    'had_ab_test': message.had_ab_test, 'ab_selection': message.ab_selection or ''
                })

    # --- NEW ---
    def _export_survey_responses(self, filepath: Path):
        """Export survey response data to an individual participant CSV file."""
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'session_id', 'sona_id', 'timestamp', 'after_message_number',
                'question_id', 'response'
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for resp in self.session.survey_responses:
                writer.writerow({
                    'session_id': self.session.session_id,
                    'sona_id': self.session.sona_id or '',
                    'timestamp': resp.timestamp,
                    'after_message_number': resp.after_message_number,
                    'question_id': resp.question_id,
                    'response': resp.response
                })
    # --- END NEW ---
    
    def get_session_summary(self) -> Dict:
        """Get a summary of the current session for debugging"""
        return {
            'session_id': self.session.session_id,
            'sona_id': self.session.sona_id,
            'consent': self.session.consent,
            'total_messages': len(self.session.messages),
            'total_ab_trials': len(self.session.ab_trials),
            'session_start': self.session.session_start,
            'session_end': self.session.session_end,
            'chat_duration_seconds': self.get_chat_duration_seconds(),
            'features': self.get_features_as_string(),
            'feature_settings': self.get_feature_settings_as_string()
        }

# — Global data logger instance —
data_logger = DataLogger()

# — Convenience functions for easier integration —
def log_message(speaker: str, content: str, had_ab_test: bool = False, ab_selection: str = None):
    data_logger.add_message(speaker, content, had_ab_test, ab_selection)

def log_ab_trial(message_content: str, option_a: str, option_b: str, 
                 selected: str, latency_ms: int, test_type: str):
    data_logger.add_ab_trial(message_content, option_a, option_b, selected, latency_ms, test_type)

# --- NEW ---
def log_survey_responses(message_num: int, results: Dict):
    """Convenience function to log a set of survey responses."""
    data_logger.add_survey_responses(message_num, results)
# --- END NEW ---

def set_features(features: Dict):
    data_logger.set_participant_features(features)

def set_feature_settings(settings: Dict):
    data_logger.set_feature_settings(settings)

def export_data(output_dir: Path = None):
    data_logger.export_to_csv(output_dir)

def set_participant_info(sona_id: str = None, consent: bool = None):
    if sona_id is not None:
        data_logger.set_sona_id(sona_id)
    if consent is not None:
        data_logger.set_consent(consent)

# Optional manual test
if __name__ == "__main__":
    print("Testing data logger with duration and feature settings...")
    set_participant_info(sona_id="123456", consent=True)
    set_feature_settings({"text_size": 16, "delay_seconds": 3, "auto_end_messages": 10})
    log_message("user", "Hello")
    log_message("assistant", "Hi there")
    log_ab_trial("Hello", "A1", "B1", "A", 1234, "content_test")
    time.sleep(2)  # simulate chat time
    data_logger.mark_session_end()
    export_data()
    print("Summary:", data_logger.get_session_summary())