from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.routes import history
from app.storage import access


@pytest.mark.parametrize("mutation", ["issuer", "audience", "expiry", "signature", "subject"])
def test_oidc_rejects_invalid_signature_claims_and_unauthorized_subject(monkeypatch, mutation):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings = Settings(
        database_url="postgresql+psycopg://unused",
        app_env="production",
        auth_mode="oidc",
        oidc_issuer="https://issuer.example",
        oidc_audience="harness",
        oidc_jwks_url="https://issuer.example/keys",
        authorized_subjects=["authorized"],
    )
    monkeypatch.setattr(access, "get_settings", lambda: settings)
    monkeypatch.setattr(
        access,
        "jwks_client",
        lambda _: SimpleNamespace(
            get_signing_key_from_jwt=lambda _: SimpleNamespace(key=key.public_key())
        ),
    )
    claims = {
        "sub": "authorized",
        "iss": settings.oidc_issuer,
        "aud": "harness",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    if mutation == "issuer":
        claims["iss"] = "other"
    if mutation == "audience":
        claims["aud"] = "other"
    if mutation == "expiry":
        claims["exp"] = datetime.now(UTC) - timedelta(seconds=1)
    if mutation == "subject":
        claims["sub"] = "not-authorized"
    signing_key = (
        rsa.generate_private_key(public_exponent=65537, key_size=2048)
        if mutation == "signature"
        else key
    )
    token = jwt.encode(claims, signing_key, algorithm="RS256")
    app = FastAPI()
    app.include_router(history.router)
    with TestClient(app) as client:
        result = client.get("/history/runs", headers={"Authorization": "Bearer " + token})
    assert result.status_code == (403 if mutation == "subject" else 401)
    assert token not in result.text


def test_shared_mode_development_identity_fails_closed(monkeypatch):
    settings = Settings(
        database_url="postgresql+psycopg://unused",
        app_env="production",
        auth_mode="development",
        dev_subject="spoof",
    )
    monkeypatch.setattr(access, "get_settings", lambda: settings)
    app = FastAPI()
    app.include_router(history.router)
    with TestClient(app) as client:
        assert client.get("/history/runs").status_code == 503


def test_verified_token_uses_server_workspace(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings = Settings(
        database_url="postgresql+psycopg://unused",
        app_env="production",
        auth_mode="oidc",
        project_id="server-project",
        oidc_issuer="https://issuer.example",
        oidc_audience="harness",
        oidc_jwks_url="https://issuer.example/keys",
        authorized_subjects=["authorized"],
    )
    monkeypatch.setattr(access, "get_settings", lambda: settings)
    monkeypatch.setattr(
        access,
        "jwks_client",
        lambda _: SimpleNamespace(
            get_signing_key_from_jwt=lambda _: SimpleNamespace(key=key.public_key())
        ),
    )
    token = jwt.encode(
        {
            "sub": "authorized",
            "iss": settings.oidc_issuer,
            "aud": "harness",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
            "project_id": "client-project",
        },
        key,
        algorithm="RS256",
    )
    from fastapi.security import HTTPAuthorizationCredentials

    context = access.get_access(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))
    assert context.project_id == "server-project" and context.principal.subject == "authorized"
