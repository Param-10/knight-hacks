from __future__ import annotations

import os
import re
import secrets
import sqlite3
from datetime import timedelta
from functools import wraps
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Dict

from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)

from legal_agents import AgentExecutionError, LegalAgentSystem
from storage import Database


BASE_DIR = Path(__file__).resolve().parent
EMAIL_PATTERN = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s]{2,}$")
PASSWORD_MIN_LENGTH = 12
NAME_MAX_LENGTH = 80
ORG_MAX_LENGTH = 120

try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} must be set. Add it to .env before starting LawyerUP.")
    return value


def configured_database_path() -> Path:
    raw_path = os.getenv("DATABASE_PATH", "instance/lawyerup.sqlite3").strip()
    path = Path(raw_path)
    return path if path.is_absolute() else BASE_DIR / path


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.update(
        SECRET_KEY=required_env("APP_SECRET_KEY"),
        DATABASE_PATH=configured_database_path(),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "0") == "1",
        SESSION_REFRESH_EACH_REQUEST=False,
        MAX_CONTENT_LENGTH=32 * 1024,
    )

    database = Database(Path(app.config["DATABASE_PATH"]))
    database.init_app()
    agent_system = LegalAgentSystem(
        lawyer_path=BASE_DIR / "lawyer_database.json",
        case_path=BASE_DIR / "case_database.json",
    )
    limiter = RateLimiter(limit=40, window_seconds=60)

    @app.before_request
    def load_current_user() -> None:
        g.db = database
        g.user = database.get_user(session["user_id"]) if session.get("user_id") else None
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)

    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'",
        )
        if app.config["SESSION_COOKIE_SECURE"]:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    @app.context_processor
    def inject_security_context() -> Dict[str, Any]:
        return {
            "csrf_token": session.get("csrf_token", ""),
            "current_user": g.get("user"),
        }

    @app.get("/")
    def landing():
        if g.user:
            return redirect(url_for("dashboard"))
        return render_template("landing.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if g.user:
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            validate_csrf()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            limiter.check_or_abort(f"login:{email or request_identity()}")
            user = database.authenticate_user(email, password)
            if not user:
                flash("Email or password is incorrect.", "error")
                return render_template("auth.html", mode="login"), 401
            establish_session(user["id"])
            return redirect(url_for("dashboard"))

        return render_template("auth.html", mode="login")

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if g.user:
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            validate_csrf()
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            organization = request.form.get("organization", "").strip()
            limiter.check_or_abort(f"signup:{request_identity()}")

            validation_error = validate_signup_fields(name, email, password, organization)
            if validation_error:
                flash(validation_error, "error")
                return render_template("auth.html", mode="signup"), 400

            try:
                user = database.create_user(name, email, password, organization)
            except sqlite3.IntegrityError:
                flash("An account already exists for that email.", "error")
                return render_template("auth.html", mode="signup"), 409

            establish_session(user["id"])
            return redirect(url_for("dashboard"))

        return render_template("auth.html", mode="signup")

    @app.post("/logout")
    @login_required
    def logout():
        validate_csrf()
        session.clear()
        flash("Signed out.", "success")
        return redirect(url_for("landing"))

    @app.get("/dashboard")
    @login_required
    def dashboard():
        reviews = database.list_reviews(g.user["id"], limit=8)
        return render_template(
            "dashboard.html",
            reviews=reviews,
            health=agent_system.health(),
            cases=agent_system.case_options(),
        )

    @app.get("/api/health")
    @login_required
    def health():
        return jsonify(agent_system.health())

    @app.get("/api/reviews")
    @login_required
    def list_reviews():
        return jsonify({"reviews": database.list_reviews(g.user["id"], limit=25)})

    @app.post("/api/intake")
    @login_required
    def intake():
        validate_csrf(header_only=True)
        limiter.check_or_abort(f"user:{g.user['id']}:intake")
        payload = request.get_json(silent=True) or {}
        message = (payload.get("message") or "").strip()
        if len(message) < 18:
            return jsonify({"error": "Add more detail before review."}), 400
        if len(message) > 3000:
            return jsonify({"error": "Matter notes must stay under 3,000 characters."}), 413

        try:
            result = agent_system.run(message)
        except AgentExecutionError as exc:
            return jsonify({"error": str(exc), "feature": exc.feature}), 502

        review_id = database.save_review(g.user["id"], message, result)
        result["review_id"] = review_id
        return jsonify(result)

    @app.post("/chat")
    @login_required
    def chat_compatibility():
        return intake()

    @app.get("/favicon.svg")
    def favicon():
        return send_from_directory(BASE_DIR, "favicon.svg")

    @app.errorhandler(404)
    def not_found(_error):
        if wants_json_response():
            return jsonify({"error": "Not found."}), 404
        return render_template("error.html", status_code=404, message="That page does not exist."), 404

    @app.errorhandler(400)
    def bad_request(error):
        message = getattr(error, "description", None) or "The request could not be processed."
        if wants_json_response():
            return jsonify({"error": str(message)}), 400
        return render_template("error.html", status_code=400, message=str(message)), 400

    @app.errorhandler(413)
    def too_large(_error):
        if wants_json_response():
            return jsonify({"error": "Request is too large."}), 413
        return render_template("error.html", status_code=413, message="Request is too large."), 413

    @app.errorhandler(429)
    def too_many_requests(_error):
        if wants_json_response():
            return jsonify({"error": "Too many requests. Please wait a moment."}), 429
        return (
            render_template("error.html", status_code=429, message="Too many requests. Please wait a moment."),
            429,
        )

    @app.errorhandler(500)
    def server_error(_error):
        if wants_json_response():
            return jsonify({"error": "The server could not complete the request."}), 500
        return (
            render_template(
                "error.html",
                status_code=500,
                message="The server could not complete the request.",
            ),
            500,
        )

    return app


def wants_json_response() -> bool:
    return request.path.startswith(("/api/", "/chat")) or request.accept_mimetypes.best == "application/json"


def request_identity() -> str:
    return request.remote_addr or "unknown"


def validate_signup_fields(name: str, email: str, password: str, organization: str) -> str:
    if len(name) < 2 or len(name) > NAME_MAX_LENGTH:
        return f"Use a name between 2 and {NAME_MAX_LENGTH} characters."
    if not EMAIL_PATTERN.fullmatch(email):
        return "Use a valid email address."
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"Use a password of at least {PASSWORD_MIN_LENGTH} characters."
    if len(password) > 256:
        return "Use a shorter password."
    if len(organization) > ORG_MAX_LENGTH:
        return f"Organization must stay under {ORG_MAX_LENGTH} characters."
    return ""


def login_required(view: Callable) -> Callable:
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.get("user"):
            if wants_json_response():
                return jsonify({"error": "Authentication required."}), 401
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def establish_session(user_id: int) -> None:
    session.clear()
    session.permanent = True
    session["user_id"] = user_id
    session["csrf_token"] = secrets.token_urlsafe(32)


def validate_csrf(header_only: bool = False) -> None:
    expected = session.get("csrf_token")
    supplied = request.headers.get("X-CSRF-Token") if header_only else request.form.get("csrf_token")
    if not expected or not supplied or not secrets.compare_digest(expected, supplied):
        abort(400, "Invalid CSRF token.")


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._requests: Dict[str, list[float]] = {}
        self._lock = Lock()

    def check_or_abort(self, key: str) -> None:
        import time

        now = time.monotonic()
        window_start = now - self.window_seconds
        with self._lock:
            recent = [timestamp for timestamp in self._requests.get(key, []) if timestamp >= window_start]
            if len(recent) >= self.limit:
                abort(429)
            recent.append(now)
            self._requests[key] = recent


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.getenv("FLASK_HOST", "127.0.0.1"),
        port=int(os.getenv("FLASK_PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
    )
