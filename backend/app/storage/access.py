"""Server-derived identity and the prototype's one-workspace sharing policy."""

from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.storage.errors import AccessDenied


@dataclass(frozen=True)
class Principal:
    subject: str
    project_id: str

    def __post_init__(self):
        if not self.subject.strip() or not self.project_id.strip():
            raise AccessDenied("A server-derived subject and workspace are required.")


@dataclass(frozen=True)
class AccessContext:
    principal: Principal

    @property
    def project_id(self) -> str:
        return self.principal.project_id

    def require(self, project_id: str) -> None:
        if not self.principal.subject or project_id != self.project_id:
            raise AccessDenied("Resource is outside the authorized workspace.")


bearer = HTTPBearer(auto_error=False)


@lru_cache
def jwks_client(url: str):
    return jwt.PyJWKClient(url, cache_keys=True, timeout=10)


def get_access(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> AccessContext:
    settings = get_settings()
    if settings.app_env == "development" and settings.auth_mode == "development":
        if not settings.dev_subject:
            raise HTTPException(503, "Development identity is not configured.")
        return AccessContext(Principal(settings.dev_subject, settings.project_id))
    if settings.auth_mode != "oidc" or not all(
        (settings.oidc_issuer, settings.oidc_audience, settings.oidc_jwks_url)
    ):
        raise HTTPException(503, "Authentication is not configured.")
    if credentials is None:
        raise HTTPException(401, "Authentication required.", headers={"WWW-Authenticate": "Bearer"})
    try:
        key = jwks_client(settings.oidc_jwks_url).get_signing_key_from_jwt(credentials.credentials)
        claims = jwt.decode(
            credentials.credentials,
            key.key,
            algorithms=["RS256"],
            issuer=settings.oidc_issuer,
            audience=settings.oidc_audience,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
        # A valid token alone does not authorize access to this project's evidence.
        if claims["sub"] not in settings.authorized_subjects:
            raise HTTPException(403, "Workspace access is not granted.")
        return AccessContext(Principal(claims["sub"], settings.project_id))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(401, "Invalid or expired access token.") from None
