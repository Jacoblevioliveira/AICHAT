# script_editor.py

import sys
import json
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QDialog, QListWidget,
    QLineEdit, QPushButton, QDialogButtonBox, QAbstractItemView, QLabel,
    QMessageBox, QListWidgetItem, QTextEdit, QStackedWidget, QFrame
)

# Import our settings to get the filename
from feature_flags import feature_settings

class ScriptEditorDialog(QDialog):
    """
    A dialog to create and edit a structured JSON conversation script,
    supporting both "normal" and "ab_test" step types.
    """
    def __init__(self, parent=None):
        super().__init__(parent)

        # 1. Configuration
        self.setWindowTitle("JSON Script Editor")
        self.setMinimumSize(800, 600)

        # Get the target filename (now script.json)
        self.filename = feature_settings.get('scripted_convo_file', 'script.json')
        self.script_path = Path(__file__).parent / self.filename
        
        # This will hold the QListWidgetItem that is currently being edited.
        # We need this to save changes before switching items.
        self.current_editing_item = None

        # 2. Build the UI
        self._setup_ui()

        # 3. Connect signals
        self._connect_signals()

        # 4. Load existing data
        self._load_script_from_file()

    def _setup_ui(self):
        """Create all widgets and layouts."""
        
        # Main layout is a horizontal split: List on left, Editor on right
        main_layout = QHBoxLayout(self)

        # --- LEFT PANEL (List of steps) ---
        left_panel_layout = QVBoxLayout()
        
        # Add Step Buttons
        add_btn_layout = QHBoxLayout()
        self.add_normal_btn = QPushButton("Add Normal Step")
        self.add_ab_btn = QPushButton("Add A/B Test Step")
        add_btn_layout.addWidget(self.add_normal_btn)
        add_btn_layout.addWidget(self.add_ab_btn)
        left_panel_layout.addLayout(add_btn_layout)

        # The list of steps
        self.step_list_widget = QListWidget()
        self.step_list_widget.setDragDropMode(QAbstractItemView.InternalMove) # Reordering is on
        self.step_list_widget.setAlternatingRowColors(True)
        self.step_list_widget.setMinimumWidth(300)
        left_panel_layout.addWidget(self.step_list_widget) # Add list with stretch
        
        # Delete Button
        self.delete_btn = QPushButton("Delete Selected Step")
        self.delete_btn.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold;")
        left_panel_layout.addWidget(self.delete_btn)
        
        # Add left panel to main layout
        main_layout.addLayout(left_panel_layout, 1) # 1 stretch factor

        # --- RIGHT PANEL (The Editor Stack) ---
        right_panel_layout = QVBoxLayout()
        
        # This stack holds our 3 editor "cards"
        self.editor_stack = QStackedWidget()
        
        # Card 0: The "Blank" editor (when nothing is selected)
        self.blank_editor_widget = QWidget()
        blank_layout = QVBoxLayout(self.blank_editor_widget)
        blank_layout.addStretch()
        blank_label = QLabel("Select a step from the list to edit it,\nor add a new step.")
        blank_label.setAlignment(Qt.AlignCenter)
        blank_label.setStyleSheet("font-size: 14pt; color: #888;")
        blank_layout.addWidget(blank_label)
        blank_layout.addStretch()

        # Card 1: The "Normal Step" editor
        self.normal_editor_widget = self._create_normal_editor_widget()
        
        # Card 2: The "A/B Step" editor (your "split-screen" idea)
        self.ab_editor_widget = self._create_ab_editor_widget()

        # Add all three cards to the stack
        self.editor_stack.addWidget(self.blank_editor_widget)
        self.editor_stack.addWidget(self.normal_editor_widget)
        self.editor_stack.addWidget(self.ab_editor_widget)
        
        right_panel_layout.addWidget(self.editor_stack, 1)

        # Apply button to save changes from editor panel back to the list item
        self.apply_changes_btn = QPushButton("Apply Changes to Step")
        self.apply_changes_btn.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; padding: 8px;")
        right_panel_layout.addWidget(self.apply_changes_btn)
        
        # Main Dialog Buttons (Save/Cancel)
        self.button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        right_panel_layout.addWidget(self.button_box)
        
        # Add right panel to main layout
        main_layout.addLayout(right_panel_layout, 2) # 2 stretch factor (wider)

    def _create_normal_editor_widget(self):
        """Helper to create the UI for editing a single-response step."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel("Normal Response:")
        label.setStyleSheet("font-weight: bold; font-size: 12pt; margin-bottom: 5px;")
        self.normal_edit_box = QTextEdit() # Use QTextEdit for multi-line text
        layout.addWidget(label)
        layout.addWidget(self.normal_edit_box)
        return widget

    def _create_ab_editor_widget(self):
        """Helper to create the UI for editing an A/B 'split-screen' step."""
        widget = QWidget()
        main_layout = QVBoxLayout(widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        title_label = QLabel("A/B Test Response:")
        title_label.setStyleSheet("font-weight: bold; font-size: 12pt; margin-bottom: 5px; color: #c0392b;")
        main_layout.addWidget(title_label)
        
        # The "split-screen" layout
        split_layout = QHBoxLayout()
        
        # A-Side
        layout_a = QVBoxLayout()
        label_a = QLabel("Response A (White)")
        label_a.setStyleSheet("font-weight: bold;")
        self.ab_edit_a = QTextEdit()
        layout_a.addWidget(label_a)
        layout_a.addWidget(self.ab_edit_a)
        
        # B-Side (with red-ish styling)
        layout_b = QVBoxLayout()
        label_b = QLabel("Response B (Lite Red)")
        label_b.setStyleSheet("font-weight: bold;")
        self.ab_edit_b = QTextEdit()
        self.ab_edit_b.setStyleSheet("background-color: #fff8f8; border: 1px solid #e74c3c;") # Your "lite red" idea
        layout_b.addWidget(label_b)
        layout_b.addWidget(self.ab_edit_b)
        
        split_layout.addLayout(layout_a)
        split_layout.addLayout(layout_b)
        main_layout.addLayout(split_layout)
        
        return widget

    def _connect_signals(self):
        """Connect all button clicks and UI events to their functions."""
        # Main dialog buttons
        self.button_box.accepted.connect(self._save_and_accept)
        self.button_box.rejected.connect(self.reject)
        
        # Add buttons
        self.add_normal_btn.clicked.connect(self._add_normal_step)
        self.add_ab_btn.clicked.connect(self._add_ab_step)
        
        # Edit buttons
        self.delete_btn.clicked.connect(self._delete_selected_step)
        self.apply_changes_btn.clicked.connect(self._save_editor_to_item)
        
        # The "magic" connection: When the user clicks a different item in the list...
        self.step_list_widget.currentItemChanged.connect(self._on_step_selected)

    def _load_script_from_file(self):
        """Loads and parses the script.json file on startup."""
        if not self.script_path.exists():
            print(f"No script file found at {self.script_path}, starting fresh.")
            return # Start with an empty editor
        
        try:
            with open(self.script_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if not isinstance(data, list):
                raise ValueError("Script file is not a valid JSON list.")
            
            self.step_list_widget.clear()
            for step_data in data:
                # Add each step (object) to the list
                self._add_step_to_list_widget(step_data)
                
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Failed to load or parse script.json:\n{e}")

    def _add_step_to_list_widget(self, step_data, insert_row=None):
        """Helper to add a new step item to our QListWidget."""
        item_type = step_data.get("type", "normal")
        
        # Create a summary text to display in the list
        display_text = ""
        if item_type == "normal":
            summary = step_data.get('response', '')[:40] + "..."
            display_text = f"[Normal]: \"{summary}\""
        elif item_type == "ab_test":
            summary_a = step_data.get('response_a', '')[:20] + "..."
            summary_b = step_data.get('response_b', '')[:20] + "..."
            display_text = f"[A/B]: A:\"{summary_a}\" | B:\"{summary_b}\""

        item = QListWidgetItem(display_text)
        
        # This is the most important part:
        # We store the *entire* python dictionary object inside the list item itself.
        item.setData(Qt.UserRole, step_data)
        
        # Add it to the list
        if insert_row is not None:
            self.step_list_widget.insertItem(insert_row, item)
        else:
            self.step_list_widget.addItem(item)
            
        return item

    # --- Button and Event Logic ---

    def _add_normal_step(self):
        """Adds a new, blank "normal" step object to the list."""
        new_step_data = {
            "type": "normal",
            "response": "New normal response. Edit me."
        }
        item = self._add_step_to_list_widget(new_step_data)
        self.step_list_widget.setCurrentItem(item) # Auto-select it

    def _add_ab_step(self):
        """Adds a new, blank "ab_test" step object to the list."""
        new_step_data = {
            "type": "ab_test",
            "response_a": "New A-Side Response. Edit me.",
            "response_b": "New B-Side Response. Edit me."
        }
        item = self._add_step_to_list_widget(new_step_data)
        self.step_list_widget.setCurrentItem(item) # Auto-select it
        
    def _delete_selected_step(self):
        """Deletes the currently selected item."""
        current_row = self.step_list_widget.currentRow()
        if current_row >= 0:
            item = self.step_list_widget.takeItem(current_row)
            del item

    def _on_step_selected(self, current_item, previous_item):
        """
        This is the main "magic" function. It fires when the user clicks
        a different item in the list. It auto-saves the old item
        and then loads the new item into the correct editor.
        """
        # Auto-save any changes from the item we are leaving
        if previous_item:
            self._save_editor_to_item(previous_item)

        if not current_item:
            # Nothing is selected (e.g., list is empty), show blank editor
            self.editor_stack.setCurrentWidget(self.blank_editor_widget)
            self.current_editing_item = None
            return

        # Get the full data object stored inside the new item
        data = current_item.data(Qt.UserRole)
        self.current_editing_item = current_item

        # Show the correct editor card based on its "type"
        if data.get("type") == "normal":
            self.normal_edit_box.setPlainText(data.get("response", ""))
            self.editor_stack.setCurrentWidget(self.normal_editor_widget)
            
        elif data.get("type") == "ab_test":
            self.ab_edit_a.setPlainText(data.get("response_a", ""))
            self.ab_edit_b.setPlainText(data.get("response_b", ""))
            self.editor_stack.setCurrentWidget(self.ab_editor_widget)
            
        else:
            self.editor_stack.setCurrentWidget(self.blank_editor_widget)

    def _save_editor_to_item(self, item_to_save=None):
        """Saves data from the editor panels back into the item's stored data."""
        if not item_to_save:
            item_to_save = self.current_editing_item
        
        if not item_to_save:
            return # Nothing to save

        # Get the data, modify it, then write it back
        data = item_to_save.data(Qt.UserRole)
        item_type = data.get("type")

        if item_type == "normal":
            data["response"] = self.normal_edit_box.toPlainText()
            # Update the display text in the list
            summary = data['response'][:40] + "..."
            item_to_save.setText(f"[Normal]: \"{summary}\"")
            
        elif item_type == "ab_test":
            data["response_a"] = self.ab_edit_a.toPlainText()
            data["response_b"] = self.ab_edit_b.toPlainText()
            # Update the display text
            summary_a = data['response_a'][:20] + "..."
            summary_b = data['response_b'][:20] + "..."
            item_to_save.setText(f"[A/B]: A:\"{summary_a}\" | B:\"{summary_b}\"")

        # Write the modified dictionary back into the item
        item_to_save.setData(Qt.UserRole, data)

    def _save_and_accept(self):
        """Gathers all data from the list and writes it to the JSON file."""
        
        # First, run one final save on the currently active editor panel
        self._save_editor_to_item()

        # Now, loop through the list and build our final python list-of-dicts
        script_to_save = []
        for i in range(self.step_list_widget.count()):
            item = self.step_list_widget.item(i)
            data = item.data(Qt.UserRole)
            script_to_save.append(data)

        try:
            # Open the file and dump our list into it as indented (human-readable) JSON
            with open(self.script_path, 'w', encoding='utf-8') as f:
                json.dump(script_to_save, f, indent=4)
            
            # Success! Accept the dialog.
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Could not save script file: {e}\n\nPlease check permissions and try again.")