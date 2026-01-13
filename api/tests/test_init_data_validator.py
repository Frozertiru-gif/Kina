import hashlib
import hmac
import json
import time
import unittest
from urllib.parse import quote, urlencode

from fastapi import HTTPException

from app.dependencies import _validate_init_data


BOT_TOKEN = "test-bot-token"


def _build_init_data(payload: dict[str, str]) -> str:
    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(payload.items())
    )
    secret = hmac.new(
        b"WebAppData",
        BOT_TOKEN.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    signature = hmac.new(secret, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    values = {**payload, "hash": signature}
    return urlencode(values, quote_via=quote)


class InitDataValidatorTests(unittest.TestCase):
    def test_valid_init_data(self) -> None:
        payload = {
            "auth_date": str(int(time.time())),
            "query_id": "AAH2E_123",
            "user": json.dumps({"id": 123, "first_name": "Tester"}),
        }
        init_data = _build_init_data(payload)
        parsed = _validate_init_data(init_data, BOT_TOKEN)
        self.assertEqual(parsed["query_id"], payload["query_id"])

    def test_double_encoded_wrapper(self) -> None:
        payload = {
            "auth_date": str(int(time.time())),
            "query_id": "AAH2E_789",
            "user": json.dumps({"id": 789, "first_name": "Tester"}),
        }
        init_data = _build_init_data(payload)
        wrapped = f"tgWebAppData={quote(init_data)}"
        parsed = _validate_init_data(wrapped, BOT_TOKEN)
        self.assertEqual(parsed["query_id"], payload["query_id"])

    def test_truncated_init_data(self) -> None:
        payload = {
            "auth_date": str(int(time.time())),
            "query_id": "AAH2E_999",
            "user": json.dumps({"id": 999, "first_name": "Tester"}),
        }
        init_data = _build_init_data(payload)
        with self.assertRaises(HTTPException):
            _validate_init_data(init_data[:-12], BOT_TOKEN)
