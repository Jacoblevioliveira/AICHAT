# ui_components.py

# In ui_components.py
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QFrame, QGridLayout, QSizePolicy,
    QHBoxLayout, QSlider, QLineEdit, QLabel, QCheckBox
)
from PySide6.QtGui import QIntValidator

class CollapsibleSection(QWidget):
    """
    A collapsible section widget containing a grid of buttons.
    Supports a 'dark' (on gradient) and 'light' (on flat color) mode.
    """
    def __init__(self, title: str, mode='dark', parent=None):
        super().__init__(parent)
        self.num_columns = 4
        self.button_count = 0
        self.title = title.upper()
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 5, 0, 5)
        main_layout.setSpacing(0)

        self.header_btn = QPushButton(f"▶  {self.title}  ◀")
        self.header_btn.setCheckable(False) 
        
        # --- NEW: Choose style based on mode ---
        if mode == 'light':
            # Style for light backgrounds (like the Experiment Designer)
            self.header_btn.setStyleSheet("""
                QPushButton {
                    background: #e1e1e1; border: 1px solid #ccc; border-radius: 8px;
                    color: #212529; font-size: 12pt; font-weight: bold;
                    text-align: center; padding: 10px; margin-top: 5px;
                }
                QPushButton:hover { background: #dcdcdc; }
            """)
        else: # Default to dark mode
            # Original style for dark/gradient backgrounds (like the Control Panel)
            self.header_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.2); border: none; border-radius: 10px;
                    color: white; font-size: 14pt; font-weight: bold;
                    text-align: center; padding: 14px 20px;
                }
                QPushButton:hover { background: rgba(255, 255, 255, 0.3); }
            """)

        main_layout.addWidget(self.header_btn)

        self.content_area = QFrame()
        self.content_area.setStyleSheet("QFrame { background: transparent; border: none; }")
        
        self.content_grid = QGridLayout(self.content_area)
        self.content_grid.setSpacing(10)
        main_layout.addWidget(self.content_area)

        self.header_btn.clicked.connect(self._on_toggle_visibility)
        
        self.content_area.setVisible(False)
        self.content_area.setMaximumHeight(0) # Helps with animation-less collapse

    def addButton(self, widget: QWidget):
        row = self.button_count // self.num_columns
        col = self.button_count % self.num_columns
        self.content_grid.addWidget(widget, row, col)
        self.button_count += 1

    def finalize_grid(self):
        if self.button_count == 0: return
        last_row = (self.button_count - 1) // self.num_columns
        last_col = (self.button_count - 1) % self.num_columns
        if last_col < (self.num_columns - 1):
            for col_index in range(last_col + 1, self.num_columns):
                placeholder = QWidget()
                placeholder.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                self.content_grid.addWidget(placeholder, last_row, col_index)

    def _on_toggle_visibility(self):
        is_currently_visible = self.content_area.isVisible()
        
        if is_currently_visible:
            self.content_area.setVisible(False)
            self.content_area.setMaximumHeight(0)
            self.header_btn.setText(f"▶  {self.title}  ◀")
        else:
            self.content_area.setVisible(True)
            self.content_area.setMaximumHeight(16777215)
            self.header_btn.setText(f"▼  {self.title}  ▼")
            
def create_modern_slider(min_val, max_val, current_val, suffix=""):
        container = QWidget()
        container.setFixedHeight(40)  # Fixed height prevents stretching
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        
        slider = QSlider(Qt.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(current_val)
        slider.setFixedHeight(30)  # Fixed slider height
        slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px;
                background: #e0e7ff;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #667eea;
                border: 2px solid #667eea;
                width: 18px;
                height: 18px;
                border-radius: 9px;
                margin: -6px 0;
            }
            QSlider::handle:horizontal:hover {
                background: #5a67d8;
                border: 2px solid #5a67d8;
            }
            QSlider::sub-page:horizontal {
                background: #667eea;
                border-radius: 3px;
            }
        """)
        
        # Make the value display editable
        value_input = QLineEdit(f"{current_val}")
        value_input.setFixedSize(80, 30)  # Fixed size prevents stretching
        value_input.setAlignment(Qt.AlignCenter)
        value_input.setStyleSheet("""
            QLineEdit {
                font-weight: bold;
                color: #4a5568;
                padding: 4px 8px;
                background: #f7fafc;
                border: 2px solid #e2e8f0;
                border-radius: 4px;
            }
            QLineEdit:focus {
                border: 2px solid #667eea;
                background: white;
            }
        """)
        
        # Add input validation
        from PySide6.QtGui import QIntValidator
        validator = QIntValidator(min_val, max_val)
        value_input.setValidator(validator)
        
        # Connect slider to input and vice versa
        def update_input_from_slider(value):
            value_input.setText(str(value))
        
        def update_slider_from_input():
            try:
                value = int(value_input.text())
                if min_val <= value <= max_val:
                    slider.setValue(value)
                else:
                    # Reset to current slider value if invalid
                    value_input.setText(str(slider.value()))
            except ValueError:
                # Reset to current slider value if invalid
                value_input.setText(str(slider.value()))
        
        slider.valueChanged.connect(update_input_from_slider)
        value_input.editingFinished.connect(update_slider_from_input)
        
        # Add suffix label if provided
        if suffix:
            suffix_label = QLabel(suffix)
            suffix_label.setStyleSheet("color: #718096; font-weight: 600; font-size: 10pt;")
            suffix_label.setFixedHeight(30)
            layout.addWidget(slider, 3)
            layout.addWidget(value_input, 1)
            layout.addWidget(suffix_label, 0)
        else:
            layout.addWidget(slider, 3)
            layout.addWidget(value_input, 1)
        
        return container, slider

# Create a modern styled checkbox
def create_modern_checkbox(text, checked=False):
    checkbox = QCheckBox(text)
    checkbox.setChecked(checked)
    checkbox.setStyleSheet("""
        QCheckBox {
            font-size: 11pt;
            color: #2d3748;
            spacing: 8px;
        }
        QCheckBox::indicator {
            width: 18px; height: 18px; border-radius: 3px;
            border: 2px solid #cbd5e0; background: white;
        }
        QCheckBox::indicator:hover { border: 2px solid #667eea; }
        QCheckBox::indicator:checked { background: #667eea; border: 2px solid #667eea; }
    """)
    return checkbox