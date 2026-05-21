from __future__ import annotations

import base64
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from gptsession_converter import convert_text


FIXED_NOW = datetime(2026, 5, 21, 10, 0, 0, tzinfo=UTC)


def fake_jwt(payload: dict) -> str:
    header = {"alg": "none", "typ": "JWT"}

    def encode(value: dict) -> str:
        data = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

    return f"{encode(header)}.{encode(payload)}.signature"


class PythonConverterTest(unittest.TestCase):
    def test_chatgpt_session_to_cockpit(self) -> None:
        access_token = fake_jwt(
            {
                "exp": 1786026576,
                "email": "mark@example.com",
                "https://api.openai.com/auth": {
                    "chatgpt_account_id": "acct-test",
                    "chatgpt_user_id": "user-test",
                    "chatgpt_plan_type": "plus",
                },
            }
        )
        result = convert_text(
            json.dumps(
                {
                    "user": {"id": "user-test", "email": "mark@example.com"},
                    "account": {"id": "acct-test", "planType": "plus"},
                    "accessToken": access_token,
                    "sessionToken": "session-token",
                }
            ),
            output_format="cockpit",
            now=FIXED_NOW,
        )

        self.assertEqual(len(result.converted), 1)
        cockpit = result.output
        self.assertEqual(cockpit["type"], "codex")
        self.assertEqual(cockpit["account_id"], "acct-test")
        self.assertEqual(cockpit["email"], "mark@example.com")
        self.assertEqual(cockpit["refresh_token"], "")
        self.assertEqual(cockpit["expired"], "2026-08-06T14:29:36.000Z")

    def test_summary_json_wrapper_is_discovered_recursively(self) -> None:
        summary_like = {
            "source": "someone.summary.json",
            "metadata": {"status": "old-export"},
            "payload": {
                "session_json": {
                    "user": {"email": "wrapped@example.com"},
                    "account": {"id": "acct-wrapped", "planType": "plus"},
                    "accessToken": "access-token",
                    "sessionToken": "session-token",
                    "expires": "2026-08-06T14:29:36.155Z",
                }
            },
        }
        result = convert_text(json.dumps(summary_like), output_format="cockpit", now=FIXED_NOW)

        self.assertEqual(len(result.converted), 1)
        self.assertEqual(result.output["email"], "wrapped@example.com")
        self.assertEqual(result.output["account_id"], "acct-wrapped")
        self.assertEqual(result.sessions[0].path, "$.payload.session_json")

    def test_txt_with_embedded_json_is_supported(self) -> None:
        text = """
old note
```json
{"user":{"email":"txt@example.com"},"account":{"id":"acct-txt"},"accessToken":"access-token","expires":"2026-08-06T14:29:36.155Z"}
```
"""
        result = convert_text(text, output_format="cockpit", now=FIXED_NOW)

        self.assertEqual(len(result.converted), 1)
        self.assertEqual(result.output["email"], "txt@example.com")
        self.assertEqual(result.output["account_id"], "acct-txt")

    def test_cli_writes_cockpit_json_without_browser(self) -> None:
        session = {
            "user": {"email": "cli@example.com"},
            "account": {"id": "acct-cli"},
            "accessToken": "access-token",
            "expires": "2026-08-06T14:29:36.155Z",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "input.summary.json"
            output_path = temp_path / "cockpit.json"
            input_path.write_text(json.dumps({"old": {"session": session}}), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gptsession_converter",
                    "--format",
                    "cockpit",
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )

            self.assertEqual(completed.stdout, "")
            self.assertIn("wrote", completed.stderr)
            output = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(output["email"], "cli@example.com")
            self.assertEqual(output["account_id"], "acct-cli")


if __name__ == "__main__":
    unittest.main()
