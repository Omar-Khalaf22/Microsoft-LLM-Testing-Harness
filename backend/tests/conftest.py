"""Tests explicitly opt into a server configured development identity."""

import os
from uuid import uuid4

import pytest

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("AUTH_MODE", "development")
os.environ.setdefault("DEV_SUBJECT", "pytest-user")


@pytest.fixture
def access():
    from app.storage.access import AccessContext, Principal

    return AccessContext(Principal("actor", "pytest_" + uuid4().hex))
