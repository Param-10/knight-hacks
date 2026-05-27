import os
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from legal_agents import LegalAgentSystem


BASE_DIR = Path(__file__).resolve().parent

try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass


app = Flask(__name__, static_folder=None)
agent_system = LegalAgentSystem(
    lawyer_path=BASE_DIR / "lawyer_database.json",
    case_path=BASE_DIR / "case_database.json",
)


@app.get("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/style.css")
def stylesheet():
    return send_from_directory(BASE_DIR, "style.css")


@app.get("/script.js")
def script():
    return send_from_directory(BASE_DIR, "script.js")


@app.get("/favicon.svg")
def favicon():
    return send_from_directory(BASE_DIR, "favicon.svg")


@app.get("/api/health")
def health():
    return jsonify(agent_system.health())


@app.get("/api/cases")
def cases():
    return jsonify({"cases": agent_system.case_options()})


@app.post("/chat")
def chat():
    payload = request.get_json(silent=True) or {}
    message = (payload.get("message") or "").strip()

    if not message:
        return jsonify({"error": "Message is required."}), 400

    return jsonify(agent_system.run(message))


if __name__ == "__main__":
    app.run(
        host=os.getenv("FLASK_HOST", "127.0.0.1"),
        port=int(os.getenv("FLASK_PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
    )
