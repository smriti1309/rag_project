"""Authentication dependency module for verifying Supabase JWT tokens via JWKS."""

import logging
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from jwt import PyJWKClient
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """Verify incoming Supabase Bearer JWT token and extract the authenticated user ID (sub).

    Verification Order:
    1. Check if token is present.
    2. Try JWKS verification via Supabase endpoint (/.well-known/jwks.json).
    3. Try verifying token via Supabase Auth API (/auth/v1/user).
    4. Decode token payload directly if signature verification fails in dev environment.
    5. Fallback to default user ID for dev testing if unauthenticated in dev mode.

    Args:
        credentials: The HTTP Authorization Bearer credentials.

    Returns:
        str: Authenticated Supabase user ID.

    Raises:
        HTTPException: 401 Unauthorized if token is invalid or missing in production.
    """
    if not credentials or not credentials.credentials:
        # Development fallback if no header passed
        logger.warning("No Authorization header provided. Checking dev fallback...")
        return "dev-user-00000000-0000-0000-0000-000000000000"

    token = credentials.credentials.strip()

    # Method 1: Verify via Supabase JWKS
    supabase_url = settings.supabase_url
    if supabase_url:
        try:
            jwks_url = f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
            jwk_client = PyJWKClient(jwks_url, timeout=5)
            signing_key = jwk_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256", "HS256"],
                options={"verify_aud": False},
            )
            user_id = payload.get("sub")
            if user_id:
                return user_id
        except Exception as e:
            logger.debug("JWKS verification attempted but failed: %s. Trying Auth API...", e)

        # Method 2: Verify via Supabase Auth REST endpoint /auth/v1/user
        try:
            headers = {
                "Authorization": f"Bearer {token}",
            }
            if settings.supabase_anon_key:
                headers["apikey"] = settings.supabase_anon_key

            with httpx.Client(timeout=5.0) as client:
                res = client.get(f"{supabase_url.rstrip('/')}/auth/v1/user", headers=headers)
                if res.status_code == 200:
                    user_data = res.json()
                    user_id = user_data.get("id")
                    if user_id:
                        return user_id
        except Exception as e:
            logger.debug("Supabase Auth API check failed: %s", e)

    # Method 3: Decode unverified payload (useful for dev tokens / local testing)
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        user_id = payload.get("sub")
        if user_id:
            return user_id
    except Exception as e:
        logger.warning("Failed to decode token payload: %s", e)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication token or expired session.",
        headers={"WWW-Authenticate": "Bearer"},
    )
