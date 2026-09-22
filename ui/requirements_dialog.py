"""Requirements profile editor — GUI for adding/editing curation checklists."""

import json
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QVBoxLayout,
)

from ui.dialogs import show_critical, show_info, show_warning
from ui.theme import action_button_style

from ui.widgets import AppButton, make_combo

from metadata_check import DEFAULT_PROFILE, PROFILES, profiles_path

PROFILES_PATH = profiles_path()


def load_profiles() -> dict:
    if PROFILES_PATH.exists():
        try:
            data = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data:
                return data
        except Exception:
            pass
    # return built-in
    return {k: {"label": v["label"], "rules": []} for k, v in PROFILES.items()}


def save_profiles(profiles: dict) -> None:
    import os
    import tempfile

    PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(profiles, indent=2, ensure_ascii=False)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(PROFILES_PATH.parent), prefix=PROFILES_PATH.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data)
        os.replace(tmp_name, PROFILES_PATH)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


class RequirementsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Requirements profiles — McMaster and custom")
        self.resize(760, 560)
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Profile:"))
        self.profile_combo = make_combo(min_width=200)
        self.profile_combo.currentTextChanged.connect(self._on_profile_changed)
        top.addWidget(self.profile_combo, 1)
        add_btn = AppButton("Add profile…", kind="secondary", size="sm")
        add_btn.clicked.connect(self._add_profile)
        top.addWidget(add_btn)
        delete_btn = AppButton("Delete", kind="secondary", size="sm")
        delete_btn.clicked.connect(self._delete_profile)
        top.addWidget(delete_btn)
        layout.addLayout(top)

        self._editor = QTextEdit()
        self._editor.setPlaceholderText("Edit the JSON for the selected profile. Each profile has label and rules. See docs/CurationLog.pdf / docs/DepositorChecklist.pdf for field names.")
        layout.addWidget(self._editor, 1)

        hint = QLabel(
            "Profiles are stored in <b>requirements_profiles.json</b> next to the executable. "
            "The <b>McMaster</b> profile is pre-filled from docs/CurationLog.pdf + docs/DepositorChecklist.pdf. "
            "Restart the app or re-select the profile in the dataset view to see changes."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        # Inline faces (see download_dialog.py): QSS alone can leave the
        # white primary text unpainted-background inside QDialog subtrees.
        cancel_btn = AppButton("Cancel", kind="secondary")
        cancel_btn.setStyleSheet(action_button_style(False))
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        save_btn = AppButton("Save", kind="primary")
        save_btn.setStyleSheet(action_button_style(True))
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)
        buttons.addWidget(save_btn)
        layout.addLayout(buttons)

        self._profiles: dict = {}
        self._load()

    def _load(self) -> None:
        # Prefer file, fall back to built-in PROFILES
        if PROFILES_PATH.exists():
            try:
                self._profiles = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
            except Exception as exc:
                show_warning(self, "Profiles", f"Could not load {PROFILES_PATH}:\n{exc}")
                self._profiles = {k: v for k, v in PROFILES.items()}
        else:
            # Seed file from built-ins on first open
            self._profiles = {
                k: {"label": v["label"], "description": v.get("description", ""), "note": "Edit rules here; see metadata_check.py for field names."}
                for k, v in PROFILES.items()
            }
        self.profile_combo.clear()
        for key in self._profiles:
            label = self._profiles[key].get("label", key)
            self.profile_combo.addItem(f"{key} — {label}", key)
        if self.profile_combo.count():
            self.profile_combo.setCurrentIndex(0)

    def _on_profile_changed(self, text: str) -> None:
        # Save current editor content back to previous profile before switching
        # (store on save, not on switch, to keep it simple)
        key = self.profile_combo.currentData()
        if key and key in self._profiles:
            self._editor.setPlainText(json.dumps(self._profiles[key], indent=2, ensure_ascii=False))

    def _add_profile(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, "Add profile", "Profile key (e.g. MyLab):")
        if not ok or not name.strip():
            return
        key = name.strip()
        if key in self._profiles:
            show_warning(self, "Profiles", f"Profile '{key}' already exists.")
            return
        self._profiles[key] = {"label": key, "description": "", "rules": []}
        self.profile_combo.addItem(f"{key} — {key}", key)
        self.profile_combo.setCurrentIndex(self.profile_combo.count() - 1)

    def _delete_profile(self) -> None:
        key = self.profile_combo.currentData()
        if not key:
            return
        if key == "McMaster":
            show_warning(self, "Profiles", "Cannot delete the built-in McMaster profile.")
            return
        del self._profiles[key]
        self._load()

    def _save(self) -> None:
        key = self.profile_combo.currentData()
        if key:
            try:
                data = json.loads(self._editor.toPlainText() or "{}")
                if not isinstance(data, dict):
                    raise ValueError("profile JSON must be an object")
                self._profiles[key] = data
            except Exception as exc:
                show_critical(self, "Profiles", f"Invalid JSON:\n{exc}")
                return
        try:
            save_profiles(self._profiles)
            # update in-memory profiles for live use
            try:
                import metadata_check

                metadata_check.PROFILES.clear()
                metadata_check.PROFILES.update(self._profiles)
            except Exception:
                pass
            show_info(self, "Profiles", f"Saved to {PROFILES_PATH.resolve()}")
            self.accept()
        except Exception as exc:
            show_critical(self, "Profiles", f"Could not save:\n{exc}")
