# survey_builder.py

import sys
import json
import uuid
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QDialogButtonBox,
    QListWidget, QPushButton, QLabel, QStackedWidget, QComboBox, QWidget,
    QLineEdit, QFormLayout, QListWidgetItem, QTextEdit, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView
)

class SurveyBuilderDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Survey Builder")
        self.setMinimumSize(900, 600)
        
        # --- START MODIFICATION ---

        # 1. Add a unique object name for specific styling
        self.setObjectName("SurveyBuilder")

        # 2. Replace the old stylesheet with this final, more specific one
        self.setStyleSheet("""
            QDialog#SurveyBuilder {
                background-color: #f0f0f0; /* A standard, neutral UI gray */
            }
            /* Target generic QWidgets inside our dialog to make them transparent */
            QDialog#SurveyBuilder QWidget {
                background-color: transparent;
                color: #212529;
            }
            /* Now, explicitly give backgrounds back to the widgets that need them */
            QListWidget, QLineEdit, QComboBox, QTableWidget, QSpinBox, QStackedWidget {
                background-color: white;
                color: black;
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 4px;
            }
            QListWidget QLineEdit { font-size: 14pt; }
            QPushButton {
                color: black;
                background-color: #e1e1e1;
                padding: 8px;
                border-radius: 4px;
                border: 1px solid #adadad;
            }
            QPushButton:hover {
                background-color: #e9e9e9;
            }
        """)
        self.current_editing_item = None

        main_layout = QHBoxLayout(self)

        # --- LEFT PANEL (List of Questions) ---
        left_panel_layout = QVBoxLayout()
        add_widget = QWidget()
        add_layout = QHBoxLayout(add_widget)
        add_layout.setContentsMargins(0,0,0,0)
        self.question_type_combo = QComboBox()
        self.question_type_combo.addItems([
            "Percentage Scale", "Likert Scale", "Multiple Choice", "Checkbox"
        ])
        self.add_question_btn = QPushButton("Add Question")
        add_layout.addWidget(self.question_type_combo, 1)
        add_layout.addWidget(self.add_question_btn, 0)
        left_panel_layout.addWidget(add_widget)
        self.question_list_widget = QListWidget()
        self.question_list_widget.setDragDropMode(QListWidget.InternalMove)
        self.question_list_widget.setAlternatingRowColors(True)
        self.question_list_widget.setMinimumWidth(350)
        left_panel_layout.addWidget(self.question_list_widget)
        self.delete_btn = QPushButton("Delete Selected Question")
        self.delete_btn.clicked.connect(self._delete_question)
        self.delete_btn.setStyleSheet("background-color: #e74c3c; color: white;")
        left_panel_layout.addWidget(self.delete_btn)
        main_layout.addLayout(left_panel_layout, 1)

        # --- RIGHT PANEL (The Editor Stack) ---
        right_panel_layout = QVBoxLayout()
        self.editor_stack = QStackedWidget()
        
        self.blank_editor = QLabel("Select a question to edit, or add a new one.")
        self.blank_editor.setAlignment(Qt.AlignCenter)
        self.blank_editor.setStyleSheet("font-size: 14pt; color: #888;")
        self.editor_stack.addWidget(self.blank_editor)
        
        self.vas_editor = self._create_vas_editor()
        self.editor_stack.addWidget(self.vas_editor)
        
        self.likert_editor = self._create_likert_editor()
        self.editor_stack.addWidget(self.likert_editor)
        
        self.mc_editor = self._create_options_editor("Multiple Choice Options")
        self.editor_stack.addWidget(self.mc_editor)
        
        self.cb_editor = self._create_options_editor("Checkbox Options")
        self.editor_stack.addWidget(self.cb_editor)

        right_panel_layout.addWidget(self.editor_stack, 1)
        self.button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        right_panel_layout.addWidget(self.button_box)
        main_layout.addLayout(right_panel_layout, 2)

        self.add_question_btn.clicked.connect(self._add_question)
        self.question_list_widget.currentItemChanged.connect(self._on_question_selected)
        self.button_box.accepted.connect(self._save_and_accept)
        self.button_box.rejected.connect(self.reject)

    def _create_vas_editor(self):
        container = QWidget()
        layout = QFormLayout(container)
        layout.setRowWrapPolicy(QFormLayout.WrapAllRows)
        self.vas_question_edit = QLineEdit()
        self.vas_left_label_edit = QLineEdit()
        self.vas_right_label_edit = QLineEdit()
        layout.addRow(QLabel("<b>Question Text:</b>"), self.vas_question_edit)
        layout.addRow(QLabel("<b>Left Scale Label (0%):</b>"), self.vas_left_label_edit)
        layout.addRow(QLabel("<b>Right Scale Label (100%):</b>"), self.vas_right_label_edit)
        return container

    def _create_likert_editor(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        form_layout = QFormLayout()
        self.likert_question_edit = QLineEdit()
        form_layout.addRow(QLabel("<b>Question Text:</b>"), self.likert_question_edit)
        
        self.likert_points_spinbox = QSpinBox()
        self.likert_points_spinbox.setRange(3, 20) # --- MODIFIED: Increased range to 20 ---
        self.likert_points_spinbox.setSingleStep(1) # Allow any number of points
        form_layout.addRow(QLabel("<b>Number of Points:</b>"), self.likert_points_spinbox)
        layout.addLayout(form_layout)
        
        layout.addWidget(QLabel("<b>Anchors (Optional):</b>"))
        self.likert_anchors_table = QTableWidget()
        self.likert_anchors_table.setColumnCount(2)
        self.likert_anchors_table.setHorizontalHeaderLabels(["Point", "Anchor Text"])
        self.likert_anchors_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.likert_anchors_table.verticalHeader().setVisible(False)
        layout.addWidget(self.likert_anchors_table)

        self.likert_points_spinbox.valueChanged.connect(self._update_likert_table)
        
        return container
        
    def _create_options_editor(self, title):
        container = QWidget()
        layout = QVBoxLayout(container)
        form_layout = QFormLayout()
        question_edit = QLineEdit()
        form_layout.addRow(QLabel("<b>Question Text:</b>"), question_edit)
        layout.addLayout(form_layout)
        layout.addWidget(QLabel(f"<b>{title}:</b>"))
        options_list = QListWidget()
        options_list.setAlternatingRowColors(True)
        options_list.setStyleSheet("QListWidget { font-size: 18pt; }")
        options_list.setSpacing(3)
        options_list.setMinimumHeight(350)
        layout.addWidget(options_list)
        btn_layout = QHBoxLayout()
        add_option_edit = QLineEdit()
        add_option_edit.setPlaceholderText("Enter new option text...")
        add_btn = QPushButton("Add Option")
        remove_btn = QPushButton("Remove Selected")
        btn_layout.addWidget(add_option_edit, 1)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(remove_btn)
        layout.addLayout(btn_layout)
        editor_widgets = {
            "question": question_edit, "options_list": options_list,
            "add_option_edit": add_option_edit, "add_btn": add_btn, "remove_btn": remove_btn
        }
        
        def add_item():
            text = add_option_edit.text().strip()
            if text:
                new_item = QListWidgetItem(text)
                new_item.setFlags(new_item.flags() | Qt.ItemIsEditable) # --- NEW: Make item editable on creation ---
                options_list.addItem(new_item)
                add_option_edit.clear()
        
        def remove_item():
            current_item = options_list.currentItem()
            if current_item:
                options_list.takeItem(options_list.row(current_item))
        
        def edit_item(item):
            # The item flags are already set, so we just need to trigger the editor
            options_list.editItem(item)

        add_btn.clicked.connect(add_item)
        remove_btn.clicked.connect(remove_item)
        add_option_edit.returnPressed.connect(add_item)
        options_list.itemDoubleClicked.connect(edit_item)

        container.setProperty("editor_widgets", editor_widgets)
        return container

    def _update_likert_table(self, num_points):
        self.likert_anchors_table.setRowCount(num_points)
        for i in range(num_points):
            point_item = QTableWidgetItem(str(i + 1))
            point_item.setFlags(point_item.flags() & ~Qt.ItemIsEditable)
            self.likert_anchors_table.setItem(i, 0, point_item)
            if not self.likert_anchors_table.item(i, 1):
                self.likert_anchors_table.setItem(i, 1, QTableWidgetItem(""))

    def _add_question(self):
        selected_type = self.question_type_combo.currentText()
        new_question_data = {"id": f"q_{uuid.uuid4().hex[:6]}"}
        display_text = ""

        if selected_type == "Percentage Scale":
            new_question_data.update({
                "type": "percentage_scale", "question": "New Percentage Question",
                "scale": ["Left Label", "Right Label"]
            })
            display_text = "[Percentage]: New Percentage Question"
        elif selected_type == "Likert Scale":
            new_question_data.update({
                "type": "likert", "question": "New Likert Question",
                "points": 5, "anchors": {"1": "Strongly Disagree", "5": "Strongly Agree"}
            })
            display_text = "[Likert]: New Likert Question"
        elif selected_type == "Multiple Choice":
            new_question_data.update({
                "type": "multiple_choice", "question": "New Multiple Choice Question",
                "options": ["Option 1", "Option 2"]
            })
            display_text = "[MC]: New Multiple Choice Question"
        elif selected_type == "Checkbox":
            new_question_data.update({
                "type": "checkbox", "question": "New Checkbox Question",
                "options": ["Choice A", "Choice B"]
            })
            display_text = "[Checkbox]: New Checkbox Question"
        
        item = QListWidgetItem(display_text)
        item.setData(Qt.UserRole, new_question_data)
        self.question_list_widget.addItem(item)
        self.question_list_widget.setCurrentItem(item)

    def _on_question_selected(self, current_item, previous_item):
        if previous_item:
            self._save_editor_to_item(previous_item)

        if not current_item:
            self.editor_stack.setCurrentWidget(self.blank_editor)
            return

        data = current_item.data(Qt.UserRole)
        q_type = data.get("type")

        editor_map = {
            "percentage_scale": self.vas_editor, "likert": self.likert_editor,
            "multiple_choice": self.mc_editor, "checkbox": self.cb_editor
        }
        editor_to_show = editor_map.get(q_type, self.blank_editor)
        
        if q_type == "percentage_scale":
            self.vas_question_edit.setText(data.get("question", ""))
            self.vas_left_label_edit.setText(data.get("scale", ["", ""])[0])
            self.vas_right_label_edit.setText(data.get("scale", ["", ""])[1])
        elif q_type == "likert":
            points = data.get("points", 5)
            anchors = data.get("anchors", {})
            self.likert_question_edit.setText(data.get("question", ""))
            self.likert_points_spinbox.setValue(points)
            for i in range(points):
                anchor_text = anchors.get(str(i + 1), "")
                self.likert_anchors_table.setItem(i, 1, QTableWidgetItem(anchor_text))
        elif q_type in ["multiple_choice", "checkbox"]:
            widgets = editor_to_show.property("editor_widgets")
            widgets["question"].setText(data.get("question", ""))
            options_list = widgets["options_list"]
            options_list.clear()
            for option_text in data.get("options", []):
                new_item = QListWidgetItem(option_text)
                new_item.setFlags(new_item.flags() | Qt.ItemIsEditable) # --- NEW: Make item editable on load ---
                options_list.addItem(new_item)

        self.editor_stack.setCurrentWidget(editor_to_show)

    def _save_editor_to_item(self, item_to_save):
        if not item_to_save: return
        
        data = item_to_save.data(Qt.UserRole)
        q_type = data.get("type")
        
        if q_type == "percentage_scale":
            data["question"] = self.vas_question_edit.text()
            data["scale"] = [self.vas_left_label_edit.text(), self.vas_right_label_edit.text()]
            item_to_save.setText(f"[Percentage]: {data['question'][:30]}...")
        elif q_type == "likert":
            data["question"] = self.likert_question_edit.text()
            points = self.likert_points_spinbox.value()
            data["points"] = points
            anchors = {}
            for i in range(points):
                item = self.likert_anchors_table.item(i, 1)
                if item:
                    anchor_text = item.text().strip()
                    if anchor_text:
                        anchors[str(i + 1)] = anchor_text
            data["anchors"] = anchors
            item_to_save.setText(f"[Likert]: {data['question'][:30]}...")
        elif q_type in ["multiple_choice", "checkbox"]:
            editor = self.mc_editor if q_type == "multiple_choice" else self.cb_editor
            widgets = editor.property("editor_widgets")
            data["question"] = widgets["question"].text()
            options = [widgets["options_list"].item(i).text() for i in range(widgets["options_list"].count())]
            data["options"] = options
            prefix = "[MC]" if q_type == "multiple_choice" else "[Checkbox]"
            item_to_save.setText(f"{prefix}: {data['question'][:30]}...")
            
        item_to_save.setData(Qt.UserRole, data)

    def _save_and_accept(self):
        # Save current editor state if editing
        current_item = self.question_list_widget.currentItem()
        if current_item:
            self._save_editor_to_item(current_item)
        
        # Gather all questions
        questions = []
        for i in range(self.question_list_widget.count()):
            item = self.question_list_widget.item(i)
            data = item.data(Qt.UserRole)
            questions.append(data)
        
        # Save to file
        from feature_flags import feature_settings
        filename = feature_settings.get('survey_filename', 'survey.json')
        survey_path = Path(__file__).parent / filename
        
        try:
            with open(survey_path, 'w', encoding='utf-8') as f:
                json.dump(questions, f, indent=2)
            self.accept()
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Save Error", f"Failed to save survey: {e}")
        
    def _delete_question(self):
        current_item = self.question_list_widget.currentItem()
        if current_item:
            row = self.question_list_widget.row(current_item)
            self.question_list_widget.takeItem(row)
            self.editor_stack.setCurrentWidget(self.blank_editor)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    builder = SurveyBuilderDialog()
    builder.show()
    sys.exit(app.exec())