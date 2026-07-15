import os
import threading
import time
from datetime import datetime
from functools import wraps
from flask import (
    Flask, render_template, request, jsonify,
    send_from_directory, session, redirect, url_for
)
from werkzeug.utils import secure_filename

os.chdir(os.path.dirname(os.path.abspath(__file__)))

import database
import ai_ranker
import settings

database.init_db()

app = Flask(__name__)
app.secret_key = os.environ.get("APP_SECRET", "dev-secret-change-in-production")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")

# ---- Auto-sync state ----
sync_state = {
    "last_sync": None,
    "last_result": None,
    "last_log": [],
    "running": False,
}


def run_sync():
    """Run one email scan cycle."""
    if sync_state["running"]:
        return
    sync_state["running"] = True
    log = []
    try:
        import email_scanner
        result = email_scanner.scan_emails(
            days_back=settings.get("days_back"),
            progress_callback=lambda msg: log.append(msg)
        )
        sync_state["last_result"] = result
    except Exception as e:
        log.append(f"Error: {e}")
        sync_state["last_result"] = {"error": str(e)}
    finally:
        sync_state["last_sync"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sync_state["last_log"] = log
        sync_state["running"] = False


def auto_sync_loop():
    """Background thread: sync on startup then every scan_interval_minutes."""
    time.sleep(5)  # wait for app to fully start
    while True:
        s = settings.load()
        if s.get("tenant_id") and s.get("client_id") and s.get("client_secret") and s.get("email_address"):
            threading.Thread(target=run_sync, daemon=True).start()
        interval = int(s.get("scan_interval_minutes", 30)) * 60
        time.sleep(interval)


threading.Thread(target=auto_sync_loop, daemon=True).start()


# ---- Auth ----

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if APP_PASSWORD and not session.get("logged_in"):
            if request.is_json:
                return jsonify({"error": "Not logged in"}), 401
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET"])
def login_page():
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def do_login():
    data = request.json or {}
    if data.get("password") == APP_PASSWORD:
        session["logged_in"] = True
        return jsonify({"ok": True})
    return jsonify({"error": "Incorrect password"}), 403


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


# ---- Main routes ----

@app.route("/")
@login_required
def index():
    count = database.get_candidate_count()
    return render_template("index.html", candidate_count=count)


@app.route("/candidates")
@login_required
def candidates():
    rows = database.get_all_candidates()
    return jsonify(rows)


@app.route("/sync_status")
@login_required
def sync_status():
    return jsonify({
        "last_sync": sync_state["last_sync"],
        "last_result": sync_state["last_result"],
        "last_log": sync_state["last_log"],
        "running": sync_state["running"],
        "candidate_count": database.get_candidate_count(),
    })


@app.route("/sync_now", methods=["POST"])
@login_required
def sync_now():
    if sync_state["running"]:
        return jsonify({"error": "Sync already running"}), 400
    threading.Thread(target=run_sync, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/rank", methods=["POST"])
@login_required
def rank():
    data = request.json
    jd_text = data.get("jd", "").strip()
    top_n = int(data.get("top_n", 5))

    if not jd_text:
        return jsonify({"error": "Please provide a job description"}), 400

    candidates = database.get_candidates_for_ranking()
    if not candidates:
        return jsonify({"error": "No candidates in the database yet — waiting for email sync."}), 400

    if top_n > len(candidates):
        top_n = len(candidates)

    try:
        results = ai_ranker.rank_candidates(jd_text, candidates, top_n)
        database.save_rankings(jd_text[:200], results)
        return jsonify({"results": results, "total_candidates": len(candidates)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route("/upload", methods=["POST"])
@login_required
def upload_cvs():
    import cv_parser
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "No files received"}), 400

    saved = 0
    skipped = 0
    errors = []
    cv_dir = settings.get("cv_save_dir") or "cv_files"
    os.makedirs(cv_dir, exist_ok=True)

    for f in files:
        try:
            filename = secure_filename(f.filename)
            if not filename:
                continue
            ext = os.path.splitext(filename)[1].lower()
            if ext not in {".pdf", ".doc", ".docx", ".txt"}:
                errors.append(f"{filename}: unsupported file type")
                continue

            if database.candidate_exists("uploaded", filename):
                skipped += 1
                continue

            file_bytes = f.read()
            cv_text = cv_parser.extract_text(filename, file_bytes)
            candidate_name = cv_parser.guess_name_from_text(cv_text, "")

            file_path = os.path.join(cv_dir, filename)
            with open(file_path, "wb") as out:
                out.write(file_bytes)

            database.insert_candidate(
                name=candidate_name,
                email="uploaded",
                subject="Manual upload",
                received_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                file_name=filename,
                file_path=file_path,
                cv_text=cv_text,
            )
            saved += 1
        except Exception as e:
            errors.append(f"{f.filename}: {e}")

    return jsonify({"saved": saved, "skipped": skipped, "errors": errors})


@app.route("/import_folder", methods=["POST"])
@login_required
def import_folder():
    import cv_parser
    folder = request.json.get("folder_path", "").strip()
    if not folder or not os.path.isdir(folder):
        return jsonify({"error": f"Folder not found: {folder}"}), 400

    cv_dir = settings.get("cv_save_dir") or "cv_files"
    os.makedirs(cv_dir, exist_ok=True)

    CV_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt"}
    saved = 0
    skipped = 0
    errors = []

    for file_name in os.listdir(folder):
        ext = os.path.splitext(file_name)[1].lower()
        if ext not in CV_EXTENSIONS:
            continue
        try:
            if database.candidate_exists("uploaded", file_name):
                skipped += 1
                continue

            file_path_src = os.path.join(folder, file_name)
            with open(file_path_src, "rb") as f:
                file_bytes = f.read()

            cv_text = cv_parser.extract_text(file_name, file_bytes)
            candidate_name = cv_parser.guess_name_from_text(cv_text, "")

            safe_name = secure_filename(file_name)
            file_path_dst = os.path.join(cv_dir, safe_name)
            with open(file_path_dst, "wb") as f:
                f.write(file_bytes)

            database.insert_candidate(
                name=candidate_name,
                email="uploaded",
                subject="Folder import",
                received_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                file_name=file_name,
                file_path=file_path_dst,
                cv_text=cv_text,
            )
            saved += 1
        except Exception as e:
            errors.append(f"{file_name}: {e}")

    return jsonify({"saved": saved, "skipped": skipped, "errors": errors})


@app.route("/cv_files/<path:filename>")
@login_required
def serve_cv(filename):
    return send_from_directory(settings.get("cv_save_dir"), filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"HR AI Agent running at http://127.0.0.1:{port}")
    app.run(debug=False, host="0.0.0.0", port=port)
