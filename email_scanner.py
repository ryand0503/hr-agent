import os
import re
import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta

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


def find_folder(mail, folder_name):
    """Return the exact IMAP folder name, handling quoted names."""
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

    try:
        log("Connecting to mailbox...")
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(config.EMAIL_ADDRESS, config.EMAIL_PASSWORD)
        log("Connected.")
    except Exception as e:
        log(f"Login failed: {e}")
        log("TIP: If your account has MFA, generate an App Password at myaccount.microsoft.com → Security → App passwords")
        return {"saved": 0, "skipped": 0, "errors": 1, "error": str(e)}

    # Find the target folder
    if config.EMAIL_FOLDER == "INBOX":
        folder_name = "INBOX"
    else:
        folder_name = find_folder(mail, config.EMAIL_FOLDER)
        if not folder_name:
            log(f"WARNING: Folder '{config.EMAIL_FOLDER}' not found. Available folders:")
            _, folders = mail.list()
            for f in folders:
                if f:
                    name = f.decode("utf-8", errors="ignore").split('"/"')[-1].strip().strip('"')
                    log(f"  - {name}")
            log("Falling back to INBOX.")
            folder_name = "INBOX"
        else:
            log(f"Found folder: {folder_name}")

    # Select the folder
    status, _ = mail.select(f'"{folder_name}"')
    if status != "OK":
        # Try without quotes
        status, _ = mail.select(folder_name)
    if status != "OK":
        log(f"Could not open folder: {folder_name}")
        mail.logout()
        return {"saved": 0, "skipped": 0, "errors": 1}

    # Search emails since cutoff date
    since_date = (datetime.now() - timedelta(days=days_back)).strftime("%d-%b-%Y")
    _, msg_ids = mail.search(None, f'(SINCE "{since_date}")')

    ids = msg_ids[0].split()
    log(f"Found {len(ids)} emails in folder since {since_date}.")

    for uid in reversed(ids):  # newest first
        try:
            _, msg_data = mail.fetch(uid, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            sender_raw = msg.get("From", "")
            subject = decode_str(msg.get("Subject", ""))
            date_str = msg.get("Date", "")

            # Parse sender name and email
            sender_name = ""
            sender_email = ""
            if "<" in sender_raw:
                sender_name = sender_raw.split("<")[0].strip().strip('"')
                sender_email = sender_raw.split("<")[1].rstrip(">").strip()
            else:
                sender_email = sender_raw.strip()

            # Subject filter (skipped if keywords list is empty)
            if config.CV_SUBJECT_KEYWORDS:
                lower_subj = subject.lower()
                if not any(kw.lower() in lower_subj for kw in config.CV_SUBJECT_KEYWORDS):
                    continue

            # Walk attachments
            has_cv = False
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

                has_cv = True

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
