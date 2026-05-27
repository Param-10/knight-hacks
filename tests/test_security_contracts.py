from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path


TEST_DB_PATH = Path(tempfile.gettempdir()) / "lawyerup-test.sqlite3"
os.environ["APP_SECRET_KEY"] = "test-secret-for-contract-tests"
os.environ["DATABASE_PATH"] = str(TEST_DB_PATH)
os.environ["GEMINI_API_KEY"] = "test-key"

from app import create_app  # noqa: E402
from legal_agents import LegalAgentSystem  # noqa: E402


def csrf_from(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    if not match:
        raise AssertionError("CSRF token missing from form.")
    return match.group(1)


class SecurityContractTests(unittest.TestCase):
    def setUp(self) -> None:
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()
        self.app = create_app()
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()

    def test_api_requires_authentication(self) -> None:
        response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json(), {"error": "Authentication required."})

    def test_signup_creates_authenticated_dashboard_session(self) -> None:
        signup_page = self.client.get("/signup")
        token = csrf_from(signup_page.get_data(as_text=True))

        response = self.client.post(
            "/signup",
            data={
                "csrf_token": token,
                "name": "Paramveer",
                "organization": "LawyerUP",
                "email": "paramveer.test@example.com",
                "password": "LongEnoughPass123",
            },
            follow_redirects=True,
        )

        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Dashboard | LawyerUP", html)
        self.assertIn("Run intake", html)

    def test_api_csrf_failure_is_json(self) -> None:
        signup_page = self.client.get("/signup")
        token = csrf_from(signup_page.get_data(as_text=True))
        self.client.post(
            "/signup",
            data={
                "csrf_token": token,
                "name": "Paramveer",
                "organization": "LawyerUP",
                "email": "csrf.test@example.com",
                "password": "LongEnoughPass123",
            },
        )

        response = self.client.post(
            "/api/intake",
            json={"message": "I need help after a car accident with an insurance adjuster calling."},
            headers={"X-CSRF-Token": "bad-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "Invalid CSRF token."})

    def test_health_reports_provider_error_without_enabling_fallbacks(self) -> None:
        system = LegalAgentSystem(Path("lawyer_database.json"), Path("case_database.json"))
        system.gateway.last_error = "quota"

        health = system.health()

        self.assertEqual(health["status"], "provider_error")
        self.assertFalse(health["fallbacks_enabled"])


if __name__ == "__main__":
    unittest.main()
