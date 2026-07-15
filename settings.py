"""
All settings come from environment variables (.env file locally, Railway vars in cloud).
No settings.json, no UI form needed.
"""
import os


def get(key):
    mapping = {
        "email_address":         os.environ.get("EMAIL_ADDRESS", ""),
        "email_password":        os.environ.get("EMAIL_PASSWORD", ""),
        "email_server":          os.environ.get("EMAIL_SERVER", "outlook.office365.com"),
        "email_folder":          os.environ.get("EMAIL_FOLDER", "CV_Inbox"),
        "cv_subject_keywords":   [],
        "anthropic_api_key":     os.environ.get("ANTHROPIC_API_KEY", ""),
        "days_back":             int(os.environ.get("DAYS_BACK", "30")),
        "cv_save_dir":           os.environ.get("CV_SAVE_DIR", "cv_files"),
        "tenant_id":             os.environ.get("TENANT_ID", ""),
        "client_id":             os.environ.get("CLIENT_ID", ""),
        "client_secret":         os.environ.get("CLIENT_SECRET", ""),
        "llm_mode":              os.environ.get("LLM_MODE", "claude"),
        "local_llm_url":         os.environ.get("LOCAL_LLM_URL", "http://127.0.0.1:8080"),
        "scan_interval_minutes": int(os.environ.get("SCAN_INTERVAL_MINUTES", "30")),
    }
    return mapping.get(key)


def load():
    return {
        "email_address":         get("email_address"),
        "email_folder":          get("email_folder"),
        "tenant_id":             get("tenant_id"),
        "client_id":             get("client_id"),
        "client_secret":         get("client_secret"),
        "anthropic_api_key":     get("anthropic_api_key"),
        "days_back":             get("days_back"),
        "scan_interval_minutes": get("scan_interval_minutes"),
        "llm_mode":              get("llm_mode"),
        "local_llm_url":         get("local_llm_url"),
    }


def is_configured():
    has_email = bool(get("email_address"))
    has_auth  = bool(get("tenant_id") and get("client_id") and get("client_secret"))
    has_api   = bool(get("anthropic_api_key"))
    return has_email and has_auth and has_api
