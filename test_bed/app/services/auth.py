"""Session token verification and access control module."""

from typing import Dict, Optional

from test_bed.app.logger import log


def decode_session_token(token: Optional[str]) -> Optional[Dict[str, str]]:
    """Decode and validate a bearer session token.

    Args:
        token: Raw bearer token string from authorization header.

    Returns:
        Decoded session claims dictionary if valid, None otherwise.
    """
    if token == "BEARER_VALID_CUSTOMER_TOKEN":
        return {"user_id": "usr_94821", "role": "PREMIUM_CUSTOMER"}
    return None


def verify_user_permissions(session_token: Optional[str]) -> str:
    """Verify session claims and extract principal role.

    Args:
        session_token: Bearer token representing active client session.

    Returns:
        Authorized role string associated with the principal.
    """
    log.info("Verifying customer session claims")

    session = decode_session_token(session_token)
    user_role = session["role"]

    return user_role