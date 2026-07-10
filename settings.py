"""
Loads and saves user settings from settings.json.
This file is safe to share — settings.json is not.
"""
import json
import os

SETTINGS_FILE = "settings.json"

DEFAULTS = {
    "email_address": "",
    "email_password": "",
    "email_server": "outlook.office365.com",
    "email_folder": "CV_inbox",
    "cv_subject_keywords": [],
    "anthropic_api_key": "",
    "days_back": 30,
    "cv_save_dir": "cv_files",
    "db_path": "hr_agent.db",
}


def load():
    if not os.path.exists(SETTINGS_FILE):
        return dict(DEFAULTS)
    with open(SETTINGS_FILE, "r") as f:
        saved = json.load(f)
    merged = dict(DEFAULTS)
    merged.update(saved)
    return merged


def save(data):
    current = load()
    current.update(data)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(current, f, indent=2)


def get(key):
    return load().get(key, DEFAULTS.get(key))


def is_configured():
    s = load()
    return bool(s.get("email_address") and s.get("email_password") and s.get("anthropic_api_key"))
