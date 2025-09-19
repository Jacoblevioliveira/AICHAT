# survey_dialog.py

import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QDialogButtonBox,
    QLabel, QSlider, QWidget, QButtonGroup, QRadioButton, QCheckBox, QFrame,
    QStyle, QStyleOptionSlider
)

# ==============================================================================
# — Custom Visual Analog Scale (VAS) Slider —
# ==============================================================================

class VASlider(QSlider):
    """
    A custom slider that starts without a visible handle. The handle appears
    and follows the mouse only after the user first clicks on the slider track.
    """
    def __init__(self, orientation):
        super().__init__(orientation)
        self.setMinimum(0)
        self.setMaximum(100)
        self.setValue(50)
        self.handle_visible = False
        self._update_style()

    def _update_style(self):
        style = """
            QSlider::groove:horizontal {
                border: 1px solid #bbb;
                background: white;
                height: 10px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: %(handle_color)s;
                border: 1px solid #5a67d8;
                width: 18px;
                margin: -4px 0;
                border-radius: 9px;
            }
        """
        handle_color = "#667eea" if self.handle_visible else "transparent"
        self.setStyleSheet(style % {"handle_color": handle_color})

    def mousePressEvent(self, event):
        if not self.handle_visible:
            self.handle_visible = True
            self._update_style()
        super().mousePressEvent(event)

# ==============================================================================
# — NEW: All-in-One VAS Widget with Floating Label —
# ==============================================================================

class VASWidget(QWidget):
    """A composite widget for a complete VAS question."""
    def __init__(self, config, parent=None):
        super().__init__(parent)
        
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(4)

        # 1. Question Label
        question_label = QLabel(config.get("question", "No question text"))
        question_label.setWordWrap(True)
        question_label.setStyleSheet("font-weight: bold; margin-bottom: 5px;")
        main_layout.addWidget(question_label)

        # 2. Floating value label (initially hidden)
        self.value_label = QLabel(self)
        self.value_label.setAlignment(Qt.AlignCenter)
        self.value_label.setStyleSheet("background: #2d3748; color: white; font-weight: bold; border-radius: 4px; padding: 2px 5px;")
        self.value_label.setFixedSize(45, 20)
        self.value_label.hide()

        # 3. The VAS Slider
        self.slider = VASlider(Qt.Horizontal)
        main_layout.addWidget(self.slider)

        # 4. Scale Labels with 0% and 100% anchors
        scale_layout = QHBoxLayout()
        left_desc = QLabel(config.get("scale", ["", ""])[0])
        right_desc = QLabel(config.get("scale", ["", ""])[1])
        
        # Add smaller, gray labels for 0% and 100%
        zero_label = QLabel("0%")
        hundred_label = QLabel("100%")
        zero_label.setStyleSheet("color: #718096;")
        hundred_label.setStyleSheet("color: #718096;")

        scale_layout.addWidget(left_desc)
        scale_layout.addWidget(zero_label)
        scale_layout.addStretch()
        scale_layout.addWidget(hundred_label)
        scale_layout.addWidget(right_desc)
        main_layout.addLayout(scale_layout)

        # Connect slider signal to update the label
        self.slider.valueChanged.connect(self.update_value_label)

    def update_value_label(self, value):
        """Updates the text and position of the floating value label."""
        if not self.slider.handle_visible:
            return

        self.value_label.setText(f"{value}%")
        if not self.value_label.isVisible():
            self.value_label.show()
            
        # This logic calculates the pixel position of the slider handle
        opt = QStyleOptionSlider()
        self.slider.initStyleOption(opt)
        handle_rect = self.slider.style().subControlRect(QStyle.CC_Slider, opt, QStyle.SC_SliderHandle, self)

        # Center the label above the handle
        label_x = handle_rect.center().x() - (self.value_label.width() / 2)
        label_y = self.slider.y() - self.value_label.height() - 2 # 2px spacing
        self.value_label.move(int(label_x), label_y)

# ==============================================================================
# — Main Survey Dialog —
# ==============================================================================

class SurveyDialog(QDialog):
    # ... (init method is the same) ...
    def __init__(self, questions, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Quick Survey")
        self.setMinimumWidth(500)
        self.questions_config = questions
        self.input_widgets = {} 
        self.results = {}

        self.layout = QVBoxLayout(self)
        self._build_ui()
        
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        self.button_box.accepted.connect(self._submit_survey)
        self.layout.addWidget(self.button_box)

    def _build_ui(self):
        # ... (this method is slightly simplified now) ...
        for q_config in self.questions_config:
            widget = None
            if q_config.get("type") == "percentage_scale":
                widget = VASWidget(q_config, self) # Use our new composite widget
                self.input_widgets[q_config["id"]] = widget # Store the whole widget
            # ... (the rest of the elif blocks are the same) ...
            elif q_config.get("type") == "likert":
                widget = self._create_likert_widget(q_config)
            elif q_config.get("type") == "multiple_choice":
                widget = self._create_mc_widget(q_config)
            elif q_config.get("type") == "checkbox":
                widget = self._create_checkbox_widget(q_config)

            if widget:
                self.layout.addWidget(widget)
                separator = QFrame()
                separator.setFrameShape(QFrame.HLine); separator.setFrameShadow(QFrame.Sunken)
                self.layout.addWidget(separator)
    
    # This method is now DELETED as its logic is inside VASWidget
    # def _create_vas_widget(self, config):

    # ... (_create_likert_widget, _create_mc_widget, _create_checkbox_widget are the same) ...
    def _create_likert_widget(self, config):
        container = QWidget(); layout = QVBoxLayout(container)
        label = QLabel(config.get("question", "No question text")); label.setWordWrap(True)
        layout.addWidget(label)
        button_group = QButtonGroup(self); self.input_widgets[config["id"]] = button_group
        radio_layout = QHBoxLayout(); radio_layout.addStretch()
        for i in range(1, 6):
            radio_button = QRadioButton(str(i)); button_group.addButton(radio_button, i); radio_layout.addWidget(radio_button)
        radio_layout.addStretch(); layout.addLayout(radio_layout)
        scale_layout = QHBoxLayout()
        left_label = QLabel(config.get("scale", ["", ""])[0]); right_label = QLabel(config.get("scale", ["", ""])[1])
        scale_layout.addWidget(left_label); scale_layout.addStretch(); scale_layout.addWidget(right_label)
        layout.addLayout(scale_layout)
        return container

    def _create_mc_widget(self, config):
        container = QWidget(); layout = QVBoxLayout(container)
        label = QLabel(config.get("question", "No question text")); label.setWordWrap(True)
        layout.addWidget(label)
        button_group = QButtonGroup(self); self.input_widgets[config["id"]] = button_group
        for i, option_text in enumerate(config.get("options", [])):
            radio_button = QRadioButton(option_text); button_group.addButton(radio_button, i); layout.addWidget(radio_button)
        return container

    def _create_checkbox_widget(self, config):
        container = QWidget(); layout = QVBoxLayout(container)
        label = QLabel(config.get("question", "No question text")); label.setWordWrap(True)
        layout.addWidget(label)
        checkboxes = []
        for option_text in config.get("options", []):
            checkbox = QCheckBox(option_text); layout.addWidget(checkbox); checkboxes.append(checkbox)
        self.input_widgets[config["id"]] = checkboxes
        return container

    def _submit_survey(self):
        # ... (this method has a small change for the vas widget) ...
        for q_config in self.questions_config:
            q_id = q_config["id"]
            q_type = q_config["type"]
            widget = self.input_widgets.get(q_id)
            
            if widget is None: continue

            if q_type == "percentage_scale":
                # Get the slider from our composite VASWidget
                slider = widget.slider
                self.results[q_id] = slider.value() if slider.handle_visible else None
            elif q_type in ["likert", "multiple_choice"]:
                checked_button = widget.checkedButton()
                self.results[q_id] = checked_button.text() if checked_button else None
            elif q_type == "checkbox":
                self.results[q_id] = [cb.text() for cb in widget if cb.isChecked()]
        
        print(f"Survey Results Collected: {self.results}")
        self.accept()

# --- Example usage for testing (unchanged) ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    example_questions = [
        {"id": "truthfulness_vas", "type": "percentage_scale", "question": "How truthful was that last response?", "scale": ["Completely False", "Completely True"]},
        {"id": "trust_likert", "type": "likert", "question": "How much do you trust this AI assistant?", "scale": ["Do not trust at all", "Trust completely"]},
        {"id": "reason_mc", "type": "multiple_choice", "question": "What is the primary reason for your trust rating?", "options": ["The tone of the response", "The information provided", "The speed of the response", "Other"]},
        {"id": "emotion_checkbox", "type": "checkbox", "question": "Which emotions did the last response make you feel? (Select all that apply)", "options": ["Confidence", "Confusion", "Annoyance", "Satisfaction", "Curiosity"]}
    ]
    dialog = SurveyDialog(example_questions)
    if dialog.exec() == QDialog.Accepted:
        print("\nFinal Survey Results:", dialog.results)
    sys.exit(0)