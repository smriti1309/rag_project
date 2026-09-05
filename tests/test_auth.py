import unittest
from unittest.mock import MagicMock, patch
from fastapi.security import HTTPAuthorizationCredentials
import jwt

from app.core.auth import get_current_user_id


class TestAuth(unittest.TestCase):
    """Unit test suite for authentication module."""

    def test_missing_credentials_returns_dev_user(self):
        """Test that missing credentials fall back to default dev user ID."""
        user_id = get_current_user_id(credentials=None)
        self.assertEqual(user_id, "dev-user-00000000-0000-0000-0000-000000000000")

    def test_unverified_token_decode_fallback(self):
        """Test decoding user sub from unverified JWT token payload."""
        token = jwt.encode({"sub": "user-decoded-999"}, "secret", algorithm="HS256")
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        user_id = get_current_user_id(credentials=creds)
        self.assertEqual(user_id, "user-decoded-999")

    @patch("app.core.auth.httpx.Client")
    def test_auth_api_verification_success(self, mock_httpx_client):
        """Test verifying bearer token via Supabase /auth/v1/user endpoint."""
        token = "valid_supabase_token"
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "user-supabase-auth-888"}

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_resp
        mock_httpx_client.return_value.__enter__.return_value = mock_client_instance

        with patch("app.core.auth.settings") as mock_settings:
            mock_settings.supabase_url = "https://example.supabase.co"
            mock_settings.supabase_anon_key = "anon_key"

            user_id = get_current_user_id(credentials=creds)
            self.assertEqual(user_id, "user-supabase-auth-888")


if __name__ == "__main__":
    unittest.main()
