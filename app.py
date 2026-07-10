import os
import threading
from functools import wraps
from flask import (
    Flask, render_template, request, jsonify,
    send_from_directory, session, redirect, url_for
)

os.chdir(os.path.dirname(os.path.abspath(__file__)))

import database
import ai_ranker
import settings

database.init_db()

app = Flask(__name__)
# Secret key for sessions — set APP_SECRET env var in production
app.secret_key = os.environ.get("APP_SECRET", "dev-secret-change-in-production")

# App password — set APP_PASSWORD env var in production (Railway dashboard)
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")

scan_status = {"running": False, "log": [], "done": False, "result": {}}


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


@app.route("/scan", methods=["POST"])
@login_required
def scan():
    global scan_status
    if scan_status["running"]:
        return jsonify({"error": "Scan already running"}), 400

    days = int(request.json.get("days", 30))
    scan_status = {"running": True, "log": [], "done": False, "result": {}}

    def run():
        global scan_status
        try:
            import email_scanner
            def log(msg):
                scan_status["log"].append(msg)
            result = email_scanner.scan_emails(days_back=days, progress_callback=log)
            scan_status["result"] = result
        except Exception as e:
            scan_status["log"].append(f"Fatal error: {e}")
            scan_status["result"] = {"error": str(e)}
        finally:
            scan_status["running"] = False
            scan_status["done"] = True

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/scan_status")
@login_required
def get_scan_status():
    return jsonify(scan_status)


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
        return jsonify({"error": "No candidates in the database yet. Run an email scan first."}), 400

    if top_n > len(candidates):
        top_n = len(candidates)

    try:
        results = ai_ranker.rank_candidates(jd_text, candidates, top_n)
        database.save_rankings(jd_text[:200], results)
        return jsonify({"results": results, "total_candidates": len(candidates)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/settings", methods=["GET"])
@login_required
def get_settings():
    s = settings.load()
    safe = {k: v for k, v in s.items() if k != "email_password"}
    safe["email_password"] = "••••••••" if s.get("email_password") else ""
    safe["configured"] = settings.is_configured()
    return jsonify(safe)


@app.route("/settings", methods=["POST"])
@login_required
def save_settings():
    data = request.json or {}
    if data.get("email_password", "").startswith("•"):
        data.pop("email_password", None)
    allowed = [
        "email_address", "email_password", "email_server",
        "email_folder", "cv_subject_keywords", "anthropic_api_key",
        "days_back", "cv_save_dir",
        "tenant_id", "client_id", "client_secret",
    ]
    filtered = {k: v for k, v in data.items() if k in allowed}
    settings.save(filtered)
    return jsonify({"ok": True})


@app.route("/cv_files/<path:filename>")
@login_required
def serve_cv(filename):
    import config
    return send_from_directory(config.CV_SAVE_DIR, filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"HR AI Agent running at http://127.0.0.1:{port}")
    app.run(debug=False, host="0.0.0.0", port=port)
