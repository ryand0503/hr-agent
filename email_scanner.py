import os
import re
import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta
import base64
import json
import urllib.request
import urllib.parse

import config
import database
import cv_parser

CV_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt"}
IMAP_SERVER = "outlook.office365.com"
IMAP_PORT = 993


def decode_str(value):
    if not value:
        return ""
    parts = decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="ignore"))
        else:
            decoded.append(part)
    return "".join(decoded)


def get_oauth_token(tenant_id, client_id, client_secret, email_address):
    """Get an OAuth2 access token using client credentials + on-behalf-of IMAP scope."""
    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://outlook.office365.com/.default",
        "grant_type": "client_credentials",
    }).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
    return result["access_token"]


def build_auth_string(email_address, access_token):
    auth = f"user={email_address}\x01auth=Bearer {access_token}\x01\x01"
    return base64.b64encode(auth.encode()).decode()


def find_folder(mail, folder_name):
    _, folders = mail.list()
    for f in folders:
        if not f:
            continue
        name = f.decode("utf-8", errors="ignore").split('"/"')[-1].strip().strip('"')
        if name.lower() == folder_name.lower():
            return name
    return None


def scan_emails(days_back=None, progress_callback=None):
    if days_back is None:
        days_back = config.DAYS_BACK

    def log(msg):
        if progress_callback:
            progress_callback(msg)

    saved = 0
    skipped = 0
    errors = 0

    s = __import__("settings").load()
    tenant_id    = s.get("tenant_id", "")
    client_id    = s.get("client_id", "")
    client_secret = s.get("client_secret", "")
    email_address = s.get("email_address", "")

    if not all([tenant_id, client_id, client_secret, email_address]):
        log("Missing OAuth credentials. Go to Settings and fill in Client ID, Tenant ID and Client Secret.")
        return {"saved": 0, "skipped": 0, "errors": 1}

    try:
        log("Getting OAuth token...")
        token = get_oauth_token(tenant_id, client_id, client_secret, email_address)
        auth_string = build_auth_string(email_address, token)
        log("Connecting to mailbox...")
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.authenticate("XOAUTH2", lambda x: auth_string)
        log("Connected.")
    except Exception as e:
        log(f"Login failed: {e}")
        return {"saved": 0, "skipped": 0, "errors": 1, "error": str(e)}

    # Find the target folder
    folder_name = "INBOX"
    if config.EMAIL_FOLDER != "INBOX":
        found = find_folder(mail, config.EMAIL_FOLDER)
        if found:
            folder_name = found
            log(f"Found folder: {folder_name}")
        else:
            log(f"WARNING: Folder '{config.EMAIL_FOLDER}' not found. Available folders:")
            _, folders = mail.list()
            for f in folders:
                if f:
                    name = f.decode("utf-8", errors="ignore").split('"/"')[-1].strip().strip('"')
                    log(f"  - {name}")
            log("Falling back to INBOX.")

    status, _ = mail.select(f'"{folder_name}"')
    if status != "OK":
        status, _ = mail.select(folder_name)
    if status != "OK":
        log(f"Could not open folder: {folder_name}")
        mail.logout()
        return {"saved": 0, "skipped": 0, "errors": 1}

    since_date = (datetime.now() - timedelta(days=days_back)).strftime("%d-%b-%Y")
    _, msg_ids = mail.search(None, f'(SINCE "{since_date}")')
    ids = msg_ids[0].split()
    log(f"Found {len(ids)} emails since {since_date}.")

    for uid in reversed(ids):
        try:
            _, msg_data = mail.fetch(uid, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            sender_raw = msg.get("From", "")
            subject = decode_str(msg.get("Subject", ""))
            date_str = msg.get("Date", "")

            sender_name = ""
            sender_email = ""
            if "<" in sender_raw:
                sender_name = sender_raw.split("<")[0].strip().strip('"')
                sender_email = sender_raw.split("<")[1].rstrip(">").strip()
            else:
                sender_email = sender_raw.strip()

            if config.CV_SUBJECT_KEYWORDS:
                lower_subj = subject.lower()
                if not any(kw.lower() in lower_subj for kw in config.CV_SUBJECT_KEYWORDS):
                    continue

            for part in msg.walk():
                if part.get_content_maintype() == "multipart":
                    continue
                if part.get("Content-Disposition") is None:
                    continue
                file_name = part.get_filename()
                if not file_name:
                    continue
                file_name = decode_str(file_name)
                if not any(file_name.lower().endswith(ext) for ext in CV_EXTENSIONS):
                    continue
                if database.candidate_exists(sender_email, file_name):
                    skipped += 1
                    continue

                file_bytes = part.get_payload(decode=True)
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
                    received_at=date_str,
                    file_name=file_name,
                    file_path=file_path,
                    cv_text=cv_text
                )
                saved += 1
                log(f"Saved: {candidate_name} ({file_name})")

        except Exception as e:
            errors += 1
            log(f"Error on message {uid}: {e}")

    mail.logout()
    log(f"Scan complete. Saved: {saved} | Skipped: {skipped} | Errors: {errors}")
    return {"saved": saved, "skipped": skipped, "errors": errors}
