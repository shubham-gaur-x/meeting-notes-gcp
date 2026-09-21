"""Tests for Linear webhook endpoint with HMAC signature verification and Memgraph synchronization."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from api.deps import settings_dep
from api.main import create_app
from meeting_notes.config import Settings


def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_linear_webhook_valid_signature_done_state(app) -> None:
    secret = "test_webhook_secret_key_123"
    custom_settings = Settings(
        llm_backend="fake",
        linear_webhook_secret=secret,
    )
    app.dependency_overrides[settings_dep] = lambda: custom_settings

    payload = {
        "action": "update",
        "type": "Issue",
        "data": {
            "id": "linear_uuid_999",
            "identifier": "ENG-404",
            "title": "Fix scaling bottleneck",
            "state": {"id": "state_done", "name": "Done", "type": "completed"},
        },
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = _sign(raw_body, secret)

    mock_update = AsyncMock(return_value=True)
    with patch("meeting_notes.graph_client.update_action_linear_status_by_ref", mock_update):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/webhook/linear",
                content=raw_body,
                headers={"Linear-Signature": sig, "Content-Type": "application/json"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "accepted"
            assert data["issue"] == "ENG-404"
            assert data["state"] == "Done"
            assert data["done"] is True

        mock_update.assert_awaited_once_with("ENG-404", "Done", True)

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_linear_webhook_valid_signature_in_progress(app) -> None:
    secret = "test_webhook_secret_key_123"
    custom_settings = Settings(
        llm_backend="fake",
        linear_webhook_secret=secret,
    )
    app.dependency_overrides[settings_dep] = lambda: custom_settings

    payload = {
        "action": "update",
        "type": "Issue",
        "data": {
            "id": "linear_uuid_888",
            "identifier": "ENG-202",
            "title": "Implement cache layer",
            "state": {"id": "state_prog", "name": "In Progress", "type": "started"},
        },
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = _sign(raw_body, secret)

    mock_update = AsyncMock(return_value=True)
    with patch("meeting_notes.graph_client.update_action_linear_status_by_ref", mock_update):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/webhook/linear",
                content=raw_body,
                headers={"Linear-Signature": sig, "Content-Type": "application/json"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["issue"] == "ENG-202"
            assert data["done"] is False

        mock_update.assert_awaited_once_with("ENG-202", "In Progress", False)

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_linear_webhook_bad_signature_rejected(app) -> None:
    secret = "correct_secret"
    custom_settings = Settings(
        llm_backend="fake",
        linear_webhook_secret=secret,
    )
    app.dependency_overrides[settings_dep] = lambda: custom_settings

    raw_body = b'{"action": "update", "type": "Issue"}'
    sig = "bad_forged_signature_hex"

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/webhook/linear",
            content=raw_body,
            headers={"Linear-Signature": sig, "Content-Type": "application/json"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "bad signature"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_linear_webhook_missing_signature_rejected(app) -> None:
    secret = "configured_secret"
    custom_settings = Settings(
        llm_backend="fake",
        linear_webhook_secret=secret,
    )
    app.dependency_overrides[settings_dep] = lambda: custom_settings

    raw_body = b'{"action": "update", "type": "Issue"}'

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/webhook/linear",
            content=raw_body,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "bad signature"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_linear_webhook_unconfigured_in_gcp_project(app) -> None:
    custom_settings = Settings(
        llm_backend="fake",
        gcp_project_id="onix-prod-12345",
        linear_webhook_secret="",
    )
    app.dependency_overrides[settings_dep] = lambda: custom_settings

    raw_body = b'{"action": "update", "type": "Issue"}'

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/webhook/linear",
            content=raw_body,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"]

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_linear_webhook_non_issue_event_acknowledged(app) -> None:
    secret = "my_secret"
    custom_settings = Settings(
        llm_backend="fake",
        linear_webhook_secret=secret,
    )
    app.dependency_overrides[settings_dep] = lambda: custom_settings

    payload = {"action": "create", "type": "Comment", "data": {"id": "comm_123"}}
    raw_body = json.dumps(payload).encode("utf-8")
    sig = _sign(raw_body, secret)

    mock_update = AsyncMock()
    with patch("meeting_notes.graph_client.update_action_linear_status_by_ref", mock_update):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/webhook/linear",
                content=raw_body,
                headers={"Linear-Signature": sig, "Content-Type": "application/json"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "accepted"
            assert data["type"] == "Comment"

        mock_update.assert_not_called()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_linear_webhook_bad_json(app) -> None:
    secret = "my_secret"
    custom_settings = Settings(
        llm_backend="fake",
        linear_webhook_secret=secret,
    )
    app.dependency_overrides[settings_dep] = lambda: custom_settings

    raw_body = b"not-json-content"
    sig = _sign(raw_body, secret)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/webhook/linear",
            content=raw_body,
            headers={"Linear-Signature": sig, "Content-Type": "application/json"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "bad json"

    app.dependency_overrides.clear()
