import os
import re
import json
import base64
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

import config
import database
import cv_parser

CV_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt"}
GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def get_token(tenant_id, client_id, client_secret):
    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())["access_token"]


def graph_get(token, path):
    req = urllib.request.Request(
        f"{GRAPH_BASE}{path}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def find_folder_id(token, email_address, folder_name):
    """Find the folder ID by name, searching top-level and child folders."""
    data = graph_get(token, f"/users/{email_address}/mailFolders?$top=50")
    for folder in data.get("value", []):
        if folder["displayName"].lower() == folder_name.lower():
            return folder["id"]
        # Check child folders
        children = graph_get(token, f"/users/{email_address}/mailFolders/{folder['id']}/childFolders?$top=50")
        for child in children.get("value", []):
            if child["displayName"].lower() == folder_name.lower():
                return child["id"]
    return None


def get_attachment_bytes(token, email_address, message_id, attachment_id):
    data = graph_get(token, f"/users/{email_address}/messages/{message_id}/attachments/{attachment_id}")
    content = data.get("contentBytes", "")
    return base64.b64decode(content) if content else None


def scan_emails(days_back=None, progress_callback=None):
    if days_back is None:
        days_back = config.DAYS_BACK

    def log(msg):
        if progress_callback:
            progress_callback(msg)

    s = __import__("settings").load()
    tenant_id     = s.get("tenant_id", "")
    client_id     = s.get("client_id", "")
    client_secret = s.get("client_secret", "")
    email_address = s.get("email_address", "")
    folder_name   = s.get("email_folder", "CV_inbox")

    if not all([tenant_id, client_id, client_secret, email_address]):
        log("Missing OAuth credentials. Go to Settings and fill in Tenant ID, Client ID and Client Secret.")
        return {"saved": 0, "skipped": 0, "errors": 1}

    saved = 0
    skipped = 0
    errors = 0

    try:
        log("Getting access token...")
        token = get_token(tenant_id, client_id, client_secret)
        log("Token obtained.")
    except Exception as e:
        log(f"Failed to get token: {e}")
        return {"saved": 0, "skipped": 0, "errors": 1, "error": str(e)}

    # Find the mail folder
    try:
        if folder_name.upper() == "INBOX":
            folder_id = "inbox"
            log("Using INBOX.")
        else:
            log(f"Looking for folder: {folder_name}...")
            folder_id = find_folder_id(token, email_address, folder_name)
            if not folder_id:
                log(f"Folder '{folder_name}' not found. Listing available folders:")
                data = graph_get(token, f"/users/{email_address}/mailFolders?$top=50")
                for f in data.get("value", []):
                    log(f"  - {f['displayName']}")
                log("Falling back to INBOX.")
                folder_id = "inbox"
            else:
                log(f"Found folder: {folder_name}")
    except Exception as e:
        log(f"Error finding folder: {e}")
        return {"saved": 0, "skipped": 0, "errors": 1, "error": str(e)}

    # Fetch messages with attachments since cutoff date
    since = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00Z")
    filter_q = urllib.parse.quote(f"hasAttachments eq true and receivedDateTime ge {since}")
    url_path = f"/users/{email_address}/mailFolders/{folder_id}/messages?$filter={filter_q}&$top=100&$select=id,subject,from,receivedDateTime,hasAttachments"

    try:
        log("Fetching emails...")
        data = graph_get(token, url_path)
        messages = data.get("value", [])
        log(f"Found {len(messages)} emails with attachments.")
    except Exception as e:
        log(f"Error fetching messages: {e}")
        return {"saved": 0, "skipped": 0, "errors": 1, "error": str(e)}

    for msg in messages:
        try:
            msg_id       = msg["id"]
            subject      = msg.get("subject", "")
            received_at  = msg.get("receivedDateTime", "")
            sender       = msg.get("from", {}).get("emailAddress", {})
            sender_email = sender.get("address", "")
            sender_name  = sender.get("name", "")

            # Subject filter (skipped if keywords list is empty)
            keywords = s.get("cv_subject_keywords", [])
            if keywords:
                if not any(kw.lower() in subject.lower() for kw in keywords):
                    continue

            # Get attachments list
            att_data = graph_get(token, f"/users/{email_address}/messages/{msg_id}/attachments?$select=id,name,contentType")
            attachments = att_data.get("value", [])

            for att in attachments:
                file_name = att.get("name", "")
                if not any(file_name.lower().endswith(ext) for ext in CV_EXTENSIONS):
                    continue

                if database.candidate_exists(sender_email, file_name):
                    skipped += 1
                    continue

                file_bytes = get_attachment_bytes(token, email_address, msg_id, att["id"])
                if not file_bytes:
                    continue

                cv_text = cv_parser.extract_text(file_name, file_bytes)
                candidate_name = cv_parser.guess_name_from_text(cv_text, sender_name)

                safe_name = re.sub(r"[^\w\-_\. ]", "_", file_name)
                file_path = os.path.join(config.CV_SAVE_DIR, safe_name)
                os.makedirs(config.CV_SAVE_DIR, exist_ok=True)
                with open(file_path, "wb") as f:
                    f.write(file_bytes)

                database.insert_candidate(
                    name=candidate_name,
                    email=sender_email,
                    subject=subject,
                    received_at=received_at,
                    file_name=file_name,
                    file_path=file_path,
                    cv_text=cv_text
                )
                saved += 1
                log(f"Saved: {candidate_name} ({file_name})")

        except Exception as e:
            errors += 1
            log(f"Error processing message: {e}")

    log(f"Scan complete. Saved: {saved} | Skipped: {skipped} | Errors: {errors}")
    return {"saved": saved, "skipped": skipped, "errors": errors}
