# experiment_designer.py

import sys
import json
import uuid
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QDialogButtonBox,
    QListWidget, QPushButton, QLabel, QStackedWidget, QWidget, QFrame,
    QListWidgetItem, QLineEdit, QFormLayout, QSpinBox, QCheckBox, QScrollArea,
    QFileDialog, QMessageBox, QHeaderView, QSlider
)
from feature_flags import FeatureFlag, FEATURE_GROUPS
from ui_components import CollapsibleSection, create_modern_slider, create_modern_checkbox

class ExperimentDesignerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Experiment Designer")
        self.setMinimumSize(1000, 700)
        self.setObjectName("ExperimentDesigner")
        self.setStyleSheet("""
            QDialog#ExperimentDesigner { background-color: #f0f0f0; }
            QDialog#ExperimentDesigner QWidget { background-color: transparent; color: #212529; }
            #ExperimentDesigner QListWidget, #ExperimentDesigner QLineEdit, #ExperimentDesigner QComboBox, 
            #ExperimentDesigner QTableWidget, #ExperimentDesigner QSpinBox, #ExperimentDesigner QStackedWidget {
                background-color: white; color: black; border: 1px solid #ccc; border-radius: 4px; padding: 4px;
            }
            #ExperimentDesigner QPushButton { color: black; background-color: #e1e1e1; border: 1px solid #adadad; padding: 8px; border-radius: 4px; }
            #ExperimentDesigner QPushButton:hover { background-color: #e9e9e9; }
        """)

        self.settings_frames = {}
        self.settings_widgets = {}

        # --- Main Layout Structure ---
        dialog_layout = QVBoxLayout(self)
        panel_layout = QHBoxLayout()
        panel_layout.setContentsMargins(10, 10, 10, 10)

        # --- Left Panel (Timeline) ---
        left_panel_widget = QFrame()
        left_panel_widget.setFrameShape(QFrame.StyledPanel)
        left_panel_layout = QVBoxLayout(left_panel_widget)
        left_panel_layout.addWidget(QLabel("<b>Experiment Timeline</b>"))
        self.block_list_widget = QListWidget()
        self.block_list_widget.setDragDropMode(QListWidget.InternalMove)
        left_panel_layout.addWidget(self.block_list_widget)
        list_btn_layout = QHBoxLayout()
        self.add_block_btn = QPushButton("Add Block")
        self.remove_block_btn = QPushButton("Remove Block")
        list_btn_layout.addWidget(self.add_block_btn)
        list_btn_layout.addWidget(self.remove_block_btn)
        left_panel_layout.addLayout(list_btn_layout)
        panel_layout.addWidget(left_panel_widget, 1)

        # --- Right Panel (Block Inspector) ---
        right_panel_widget = QFrame()
        right_panel_widget.setFrameShape(QFrame.StyledPanel)
        right_panel_layout = QVBoxLayout(right_panel_widget)
        right_panel_layout.addWidget(QLabel("<b>Block Inspector</b>"))
        self.editor_stack = QStackedWidget()
        self.blank_editor = QLabel("Select a block to edit, or add a new one.")
        self.blank_editor.setAlignment(Qt.AlignCenter)
        self.blank_editor.setStyleSheet("font-size: 14pt; color: #888;")
        self.editor_stack.addWidget(self.blank_editor)
        self.block_editor = self._create_block_editor()
        self.editor_stack.addWidget(self.block_editor)
        right_panel_layout.addWidget(self.editor_stack, 1)
        panel_layout.addWidget(right_panel_widget, 2)

        dialog_layout.addLayout(panel_layout)

        # --- Main Dialog Buttons ---
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Open | QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        dialog_layout.addWidget(self.button_box)

        # --- Connect Signals ---
        self.add_block_btn.clicked.connect(self._add_block)
        self.remove_block_btn.clicked.connect(self._remove_selected_block)
        self.block_list_widget.currentItemChanged.connect(self._on_block_selected)
        self.button_box.button(QDialogButtonBox.Open).clicked.connect(self._load_from_file)
        self.button_box.button(QDialogButtonBox.Save).clicked.connect(self._save_and_accept)
        self.button_box.rejected.connect(self.reject)

        for _, button in self.feature_buttons.items():
            button.toggled.connect(self._update_settings_visibility)

    def _create_block_editor(self):
        container = QWidget(); layout = QVBoxLayout(container)
        basic_settings_widget = QWidget(); form_layout = QFormLayout(basic_settings_widget)
        self.block_name_edit = QLineEdit(); self.block_duration_spin = QSpinBox()
        self.block_duration_spin.setRange(1, 999); self.block_duration_spin.setSuffix(" messages")
        form_layout.addRow(QLabel("<b>Block Name:</b>"), self.block_name_edit)
        form_layout.addRow(QLabel("<b>Duration:</b>"), self.block_duration_spin)
        layout.addWidget(basic_settings_widget)
        layout.addWidget(QLabel("<b>Active Features:</b>"))
        self.feature_editor_widget, self.feature_buttons = self._create_feature_editor()
        layout.addWidget(self.feature_editor_widget)
        layout.addWidget(QLabel("<b>Feature Settings:</b>"))
        self.settings_area = QScrollArea(); self.settings_area.setWidgetResizable(True)
        self.settings_area.setStyleSheet("QScrollArea { border: 1px solid #ccc; border-radius: 4px; background-color: white; }")
        settings_container = QWidget(); self.settings_layout = QVBoxLayout(settings_container)
        self.settings_layout.setContentsMargins(10, 10, 10, 10); self.settings_layout.addStretch()
        self.settings_area.setWidget(settings_container); layout.addWidget(self.settings_area, 1)
        self._create_all_settings_widgets()
        return container

    def _create_feature_editor(self):
        container = QScrollArea(); container.setWidgetResizable(True); container.setStyleSheet("QScrollArea { border: none; }")
        widget = QWidget(); layout = QVBoxLayout(widget); layout.setContentsMargins(0,0,0,0)
        feature_buttons = {}
        flag_to_group_map = {}
        for group_title, flag_list in FEATURE_GROUPS.items():
            for flag_name in flag_list: flag_to_group_map[flag_name] = group_title
        sections = {title: CollapsibleSection(title, mode='light') for title in FEATURE_GROUPS.keys()}
        for flag in FeatureFlag:
            if flag == FeatureFlag.DYNAMIC_FEATURE_CHANGING:
                continue
            btn = QPushButton(flag.name.replace('_', ' ').title()); btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton { text-align: left; padding: 8px; background-color: #f0f0f0; border: 1px solid #ccc; }
                QPushButton:checked { background-color: #c8e6c9; border-color: #81c784; font-weight: bold; }
                QPushButton:hover { background-color: #e0e0e0; }
            """)
            feature_buttons[flag] = btn
            group_title = flag_to_group_map.get(flag.name, "Other")
            if group_title not in sections: sections[group_title] = CollapsibleSection(group_title, mode='light')
            sections[group_title].addButton(btn)
        for section in sections.values():
            if section.button_count > 0: layout.addWidget(section)
        layout.addStretch(); container.setWidget(widget)
        return container, feature_buttons

    def _create_all_settings_widgets(self):
        """Create all possible settings widgets and add them to the layout, initially hidden."""
        # --- TEXT SIZE CHANGER SETTINGS ---
        ts_frame = QFrame(); ts_layout = QFormLayout(ts_frame)
        ts_container, ts_slider = create_modern_slider(8, 48, 20, "pt")
        ts_layout.addRow("Text Size:", ts_container)
        self.settings_frames[FeatureFlag.TEXT_SIZE_CHANGER] = ts_frame
        self.settings_widgets[FeatureFlag.TEXT_SIZE_CHANGER] = {"text_size": ts_slider}
        self.settings_layout.insertWidget(0, ts_frame); ts_frame.hide()
        # --- DELAY BEFORE SEND SETTINGS ---
        dbs_frame = QFrame(); dbs_layout = QFormLayout(dbs_frame)
        dbs_container, dbs_slider = create_modern_slider(1, 30, 2, "s")
        dbs_layout.addRow("Send Delay:", dbs_container)
        self.settings_frames[FeatureFlag.DELAY_BEFORE_SEND] = dbs_frame
        self.settings_widgets[FeatureFlag.DELAY_BEFORE_SEND] = {"delay_seconds": dbs_slider}
        self.settings_layout.insertWidget(0, dbs_frame); dbs_frame.hide()
        # --- AUTO END (MESSAGES) SETTINGS ---
        aenm_frame = QFrame(); aenm_layout = QFormLayout(aenm_frame)
        aenm_container, aenm_slider = create_modern_slider(1, 100, 10, " msgs")
        aenm_layout.addRow("Max Messages:", aenm_container)
        self.settings_frames[FeatureFlag.AUTO_END_AFTER_N_MSGS] = aenm_frame
        self.settings_widgets[FeatureFlag.AUTO_END_AFTER_N_MSGS] = {"auto_end_messages": aenm_slider}
        self.settings_layout.insertWidget(0, aenm_frame); aenm_frame.hide()
        # --- AUTO END (MINUTES) SETTINGS ---
        aetm_frame = QFrame(); aetm_layout = QFormLayout(aetm_frame)
        aetm_container, aetm_slider = create_modern_slider(1, 120, 5, " min")
        aetm_layout.addRow("Max Minutes:", aetm_container)
        self.settings_frames[FeatureFlag.AUTO_END_AFTER_T_MIN] = aetm_frame
        self.settings_widgets[FeatureFlag.AUTO_END_AFTER_T_MIN] = {"auto_end_minutes": aetm_slider}
        self.settings_layout.insertWidget(0, aetm_frame); aetm_frame.hide()
        # --- CUSTOM CHAT TITLE SETTINGS ---
        cct_frame = QFrame(); cct_layout = QFormLayout(cct_frame)
        title_edit = QLineEdit()
        cct_layout.addRow("Custom Chat Title:", title_edit)
        self.settings_frames[FeatureFlag.CUSTOM_CHAT_TITLE] = cct_frame
        self.settings_widgets[FeatureFlag.CUSTOM_CHAT_TITLE] = {"custom_chat_title": title_edit}
        self.settings_layout.insertWidget(0, cct_frame); cct_frame.hide()
        # --- BLOCK MESSAGES SETTINGS ---
        bm_frame = QFrame(); bm_layout = QFormLayout(bm_frame)
        bm_count_container, bm_count_slider = create_modern_slider(1, 100, 5, " msgs")
        bm_duration_container, bm_duration_slider = create_modern_slider(5, 300, 15, "s")
        bm_repeat_checkbox = create_modern_checkbox("Repeat block", checked=True)
        bm_layout.addRow("Block After Messages:", bm_count_container)
        bm_layout.addRow("Block Duration:", bm_duration_container)
        bm_layout.addRow(bm_repeat_checkbox)
        self.settings_frames[FeatureFlag.BLOCK_MSGS] = bm_frame
        self.settings_widgets[FeatureFlag.BLOCK_MSGS] = { "block_message_count": bm_count_slider, "block_duration_s": bm_duration_slider, "block_repeat": bm_repeat_checkbox }
        self.settings_layout.insertWidget(0, bm_frame); bm_frame.hide()
        # --- ERASE HISTORY SETTINGS ---
        eh_frame = QFrame(); eh_layout = QFormLayout(eh_frame)
        eh_delay_container, eh_delay_slider = create_modern_slider(10, 3600, 60, "s")
        eh_interval_container, eh_interval_slider = create_modern_slider(30, 3600, 120, "s")
        eh_repeat_checkbox = create_modern_checkbox("Repeat erase", checked=False)
        eh_layout.addRow("Initial Delay:", eh_delay_container)
        eh_layout.addRow("Repeat Interval:", eh_interval_container)
        eh_layout.addRow(eh_repeat_checkbox)
        self.settings_frames[FeatureFlag.ERASE_HISTORY] = eh_frame
        self.settings_widgets[FeatureFlag.ERASE_HISTORY] = { "erase_history_delay_s": eh_delay_slider, "erase_history_interval_s": eh_interval_slider, "erase_history_repeat": eh_repeat_checkbox }
        self.settings_layout.insertWidget(0, eh_frame); eh_frame.hide()
        # --- SLOWDOWN SETTINGS ---
        sd_frame = QFrame(); sd_layout = QFormLayout(sd_frame)
        sd_period_container, sd_period_slider = create_modern_slider(5, 3600, 100, "s")
        sd_window_container, sd_window_slider = create_modern_slider(1, 3600, 20, "s")
        sd_layout.addRow("Cycle Period:", sd_period_container); sd_layout.addRow("Slow Window:", sd_window_container)
        self.settings_frames[FeatureFlag.SLOWDOWN] = sd_frame
        self.settings_widgets[FeatureFlag.SLOWDOWN] = { "slowdown_period_s": sd_period_slider, "slowdown_window_s": sd_window_slider }
        self.settings_layout.insertWidget(0, sd_frame); sd_frame.hide()
        # --- TYPEWRITER SETTINGS ---
        tw_frame = QFrame(); tw_layout = QFormLayout(tw_frame)
        tw_speed_container, tw_speed_slider = create_modern_slider(1, 1000, 20, " ms")
        tw_layout.addRow("Typing Speed:", tw_speed_container)
        self.settings_frames[FeatureFlag.TYPEWRITER] = tw_frame
        self.settings_widgets[FeatureFlag.TYPEWRITER] = {"typewriter_speed_ms": tw_speed_slider}
        self.settings_layout.insertWidget(0, tw_frame); tw_frame.hide()

    def _update_settings_visibility(self):
        for flag in self.feature_buttons:
            frame = self.settings_frames.get(flag)
            button = self.feature_buttons.get(flag)
            if frame and button:
                frame.setVisible(button.isChecked())
    
    def _add_block(self):
        block_count = self.block_list_widget.count() + 1; block_name = f"Block {block_count}"
        new_block_data = { "id": f"block_{uuid.uuid4().hex[:6]}", "name": block_name, "duration_messages": 10, "features": {}, "settings": {}}
        item = QListWidgetItem(f"{block_name} ({new_block_data['duration_messages']} Messages)")
        item.setData(Qt.UserRole, new_block_data)
        self.block_list_widget.addItem(item); self.block_list_widget.setCurrentItem(item)

    def _remove_selected_block(self):
        current_item = self.block_list_widget.currentItem()
        if current_item: self.block_list_widget.takeItem(self.block_list_widget.row(current_item))

    def _on_block_selected(self, current_item, previous_item):
        if previous_item: self._save_editor_to_item(previous_item)
        if not current_item:
            self.editor_stack.setCurrentWidget(self.blank_editor); return

        data = current_item.data(Qt.UserRole)
        self.block_name_edit.setText(data.get("name", ""))
        self.block_duration_spin.setValue(data.get("duration_messages", 1))

        active_features = data.get("features", {})
        for flag, button in self.feature_buttons.items():
            button.setChecked(active_features.get(flag.name, False))
        
        block_settings = data.get("settings", {})
        for flag, widgets in self.settings_widgets.items():
            for setting_name, widget in widgets.items():
                default_val = None
                if isinstance(widget, (QSlider, QSpinBox)): default_val = widget.value()
                elif isinstance(widget, QCheckBox): default_val = widget.isChecked()
                else: default_val = widget.text()
                saved_val = block_settings.get(setting_name, default_val)

                if isinstance(widget, (QSlider, QSpinBox)): widget.setValue(saved_val)
                elif isinstance(widget, QCheckBox): widget.setChecked(saved_val)
                elif isinstance(widget, QLineEdit): widget.setText(saved_val)
        
        self.editor_stack.setCurrentWidget(self.block_editor)

    def _save_editor_to_item(self, item_to_save):
        if not item_to_save: return
        data = item_to_save.data(Qt.UserRole)
        data["name"] = self.block_name_edit.text()
        data["duration_messages"] = self.block_duration_spin.value()
        
        active_features = {}
        for flag, button in self.feature_buttons.items():
            if button.isChecked(): active_features[flag.name] = True
        data["features"] = active_features
        
        block_settings = {}
        for flag, widgets in self.settings_widgets.items():
            if self.feature_buttons.get(flag) and self.feature_buttons[flag].isChecked():
                for setting_name, widget in widgets.items():
                    if isinstance(widget, (QSlider, QSpinBox)): block_settings[setting_name] = widget.value()
                    elif isinstance(widget, QCheckBox): block_settings[setting_name] = widget.isChecked()
                    elif isinstance(widget, QLineEdit): block_settings[setting_name] = widget.text()
        data["settings"] = block_settings
        
        item_to_save.setText(f"{data['name']} ({data['duration_messages']} Messages)"); item_to_save.setData(Qt.UserRole, data)

    def _load_from_file(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Open Experiment Blueprint", "", "JSON Files (*.json)")
        if not filepath: return
        try:
            with open(filepath, 'r', encoding='utf-8') as f: all_data = json.load(f)
            if not isinstance(all_data, list): raise ValueError("Blueprint file is not a valid list of blocks.")
            self.block_list_widget.clear()
            for block_data in all_data:
                item = QListWidgetItem(f"{block_data['name']} ({block_data['duration_messages']} Messages)")
                item.setData(Qt.UserRole, block_data); self.block_list_widget.addItem(item)
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Failed to load or parse file:\n{e}")

    def _save_and_accept(self):
        self._save_editor_to_item(self.block_list_widget.currentItem())
        filepath, _ = QFileDialog.getSaveFileName(self, "Save Experiment Blueprint", "experiment_blueprint.json", "JSON Files (*.json)")
        if not filepath: return
        blueprint_to_save = []
        for i in range(self.block_list_widget.count()):
            item = self.block_list_widget.item(i); blueprint_to_save.append(item.data(Qt.UserRole))
        try:
            with open(filepath, 'w', encoding='utf-8') as f: json.dump(blueprint_to_save, f, indent=4)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Could not save file:\n{e}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    designer = ExperimentDesignerDialog()
    designer.show()
    sys.exit(app.exec())