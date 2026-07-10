"""
Thin shim — reads live from settings.json each time an attribute is accessed.
Do not put credentials here. This file is safe to share.
"""
import settings as _s

_KEY_MAP = {
    "EMAIL_ADDRESS":       "email_address",
    "EMAIL_PASSWORD":      "email_password",
    "EMAIL_SERVER":        "email_server",
    "EMAIL_FOLDER":        "email_folder",
    "CV_SUBJECT_KEYWORDS": "cv_subject_keywords",
    "ANTHROPIC_API_KEY":   "anthropic_api_key",
    "DAYS_BACK":           "days_back",
    "CV_SAVE_DIR":         "cv_save_dir",
    "DB_PATH":             "db_path",
}

def __getattr__(name):
    key = _KEY_MAP.get(name)
    if key is None:
        raise AttributeError(f"No config setting: {name}")
    return _s.get(key)
