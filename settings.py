"""
Loads settings from settings.json if it exists (local),
otherwise falls back to environment variables (Railway/cloud).
This file is safe to share — settings.json and env vars are not.
"""
import json
import os

SETTINGS_FILE = "settings.json"

DEFAULTS = {
    "email_address":          "",
    "email_password":         "",
    "email_server":           "outlook.office365.com",
    "email_folder":           "CV_Inbox",
    "cv_subject_keywords":    [],
    "anthropic_api_key":      "",
    "days_back":              30,
    "cv_save_dir":            "cv_files",
    "db_path":                "hr_agent.db",
    "tenant_id":              "",
    "client_id":              "",
    "client_secret":          "",
    "llm_mode":               "claude",
    "local_llm_url":          "http://127.0.0.1:8080",
    "scan_interval_minutes":  30,
}

# Map setting keys to environment variable names
ENV_MAP = {
    "email_address":         "EMAIL_ADDRESS",
    "email_password":        "EMAIL_PASSWORD",
    "email_folder":          "EMAIL_FOLDER",
    "anthropic_api_key":     "ANTHROPIC_API_KEY",
    "tenant_id":             "TENANT_ID",
    "client_id":             "CLIENT_ID",
    "client_secret":         "CLIENT_SECRET",
    "llm_mode":              "LLM_MODE",
    "scan_interval_minutes": "SCAN_INTERVAL_MINUTES",
}


def load():
    # Start with defaults
    merged = dict(DEFAULTS)

    # Layer in env vars (so Railway variables always work)
    for key, env_key in ENV_MAP.items():
        val = os.environ.get(env_key)
        if val:
            merged[key] = int(val) if key == "scan_interval_minutes" else val

    # Layer in settings.json on top (local overrides env vars)
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            saved = json.load(f)
        merged.update(saved)

    return merged


def save(data):
    current = load()
    current.update(data)
    # Only save to file — never write back to env vars
    with open(SETTINGS_FILE, "w") as f:
        json.dump(current, f, indent=2)


def get(key):
    return load().get(key, DEFAULTS.get(key))


def is_configured():
    s = load()
    has_email = bool(s.get("email_address"))
    has_auth  = bool(s.get("email_password") or (
        s.get("tenant_id") and s.get("client_id") and s.get("client_secret")
    ))
    has_api   = bool(s.get("anthropic_api_key"))
    return has_email and has_auth and has_api
