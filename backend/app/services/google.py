"""Verification of Google Sign-In ID tokens.

The browser obtains a signed ID token (JWT) from Google and posts it to us. We
never trust its contents until the signature, audience, issuer and expiry have
been checked against Google's published keys.
"""

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError

from app.config import settings


GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}

# Keys are cached for an hour; PyJWKClient refetches on an unknown key id.
_jwks_client = PyJWKClient(GOOGLE_JWKS_URL, cache_keys=True, lifespan=3600, timeout=5)


class GoogleNotConfigured(Exception):
    """GOOGLE_CLIENT_ID is not set, so Google sign-in is switched off."""


class GoogleUnavailable(Exception):
    """Google's signing keys could not be fetched."""


class GoogleTokenError(Exception):
    """The credential is not a valid, current token for this application."""


def verify_google_id_token(credential: str) -> dict:
    client_id = settings.google_client_id
    if not client_id:
        raise GoogleNotConfigured()

    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(credential)
        # Algorithm is pinned: a token claiming "none" or HS256 is rejected.
        claims = jwt.decode(
            credential,
            signing_key.key,
            algorithms=["RS256"],
            audience=client_id,
            leeway=10,
            options={"require": ["exp", "iat", "aud", "iss", "sub"]},
        )
    except PyJWKClientConnectionError as exc:
        raise GoogleUnavailable() from exc
    except jwt.PyJWTError as exc:
        raise GoogleTokenError() from exc

    if claims["iss"] not in GOOGLE_ISSUERS:
        raise GoogleTokenError()

    # Only a verified address proves the person owns the mailbox.
    if claims.get("email_verified") not in (True, "true"):
        raise GoogleTokenError()

    if not isinstance(claims.get("email"), str) or not claims["email"].strip():
        raise GoogleTokenError()

    return claims
