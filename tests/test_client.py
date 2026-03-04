"""Tests for src/typeform/client.py"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.typeform.client import TypeformAPIError, TypeformClient
from src.typeform.models import Choice, FieldType, Form, MultipleChoiceProperties, SurveyField


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(token: str = "tfp_test_token") -> TypeformClient:
    return TypeformClient(token=token)


def _simple_form() -> Form:
    return Form(
        title="Test Form",
        fields=[
            SurveyField(
                ref="q1",
                title="Role?",
                type=FieldType.multiple_choice,
                properties=MultipleChoiceProperties(
                    choices=[Choice(ref="q1_a", label="A"), Choice(ref="q1_b", label="B")]
                ),
            )
        ],
    )


def _mock_response(status_code: int, body: dict | None = None) -> MagicMock:
    """Creates a mock requests.Response compatible with the client."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.ok = status_code < 400
    mock.json.return_value = body or {}
    mock.text = json.dumps(body or {})
    mock.content = b""
    return mock


def _patch_session(client: TypeformClient, response: MagicMock):
    """Replaces session.request with a mock that returns the given response."""
    client._session.request = MagicMock(return_value=response)
    return client._session.request


# ---------------------------------------------------------------------------
# TypeformClient.__init__
# ---------------------------------------------------------------------------


def test_client_explicit_token():
    client = TypeformClient(token="my_token")
    assert client.token == "my_token"


def test_client_reads_env_token(monkeypatch):
    monkeypatch.setenv("TYPEFORM_TOKEN", "env_token")
    client = TypeformClient()
    assert client.token == "env_token"


def test_client_missing_token_raises(monkeypatch):
    monkeypatch.delenv("TYPEFORM_TOKEN", raising=False)
    with pytest.raises(KeyError):
        TypeformClient()


# ---------------------------------------------------------------------------
# _headers
# ---------------------------------------------------------------------------


def test_headers_contain_bearer():
    client = _make_client("tfp_abc123")
    headers = client._headers()
    assert headers["Authorization"] == "Bearer tfp_abc123"
    assert headers["Content-Type"] == "application/json"


def test_headers_no_content_type_when_none():
    client = _make_client()
    headers = client._headers(content_type=None)
    assert "Content-Type" not in headers


# ---------------------------------------------------------------------------
# TypeformAPIError
# ---------------------------------------------------------------------------


def test_api_error_attributes():
    err = TypeformAPIError(400, "INVALID_REQUEST", "Bad payload", [{"field": "/title"}])
    assert err.status_code == 400
    assert err.code == "INVALID_REQUEST"
    assert err.description == "Bad payload"
    assert len(err.details) == 1
    assert "400" in str(err)


def test_api_error_no_details():
    err = TypeformAPIError(404, "NOT_FOUND", "Form not found")
    assert err.details == []


# ---------------------------------------------------------------------------
# create_form
# ---------------------------------------------------------------------------


def test_create_form_success():
    client = _make_client()
    mock = _patch_session(client, _mock_response(200, {"id": "form123", "title": "Test Form"}))

    result = client.create_form(_simple_form())

    assert result["id"] == "form123"
    call_kwargs = mock.call_args
    assert call_kwargs[0][1].endswith("/forms")
    assert call_kwargs[1]["json"]["title"] == "Test Form"


def test_create_form_api_error_raises():
    client = _make_client()
    _patch_session(client, _mock_response(400, {"code": "INVALID_REQUEST", "description": "Bad"}))

    with pytest.raises(TypeformAPIError) as exc_info:
        client.create_form(_simple_form())

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "INVALID_REQUEST"


# ---------------------------------------------------------------------------
# get_form
# ---------------------------------------------------------------------------


def test_get_form_success():
    client = _make_client()
    mock = _patch_session(client, _mock_response(200, {"id": "form123", "title": "My Form"}))

    result = client.get_form("form123")

    assert result["id"] == "form123"
    call_url = mock.call_args[0][1]
    assert "form123" in call_url


def test_get_form_not_found_raises():
    client = _make_client()
    _patch_session(client, _mock_response(404, {"code": "NOT_FOUND", "description": "Not found"}))

    with pytest.raises(TypeformAPIError) as exc_info:
        client.get_form("nonexistent")

    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# update_form (PUT)
# ---------------------------------------------------------------------------


def test_update_form_success():
    client = _make_client()
    mock = _patch_session(client, _mock_response(200, {"id": "form123", "title": "Updated"}))

    result = client.update_form("form123", _simple_form())

    assert result["id"] == "form123"
    assert "form123" in mock.call_args[0][1]


def test_update_form_error_raises():
    client = _make_client()
    _patch_session(client, _mock_response(422, {"code": "VALIDATION_ERROR", "description": "Invalid"}))

    with pytest.raises(TypeformAPIError) as exc_info:
        client.update_form("form123", _simple_form())

    assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# patch_form (PATCH)
# ---------------------------------------------------------------------------


def test_patch_form_success():
    client = _make_client()
    ops = [{"op": "replace", "path": "/title", "value": "Patched"}]
    mock = _patch_session(client, _mock_response(200, {"id": "form123", "title": "Patched"}))

    result = client.patch_form("form123", ops)

    assert result["title"] == "Patched"
    assert mock.call_args[1]["json"] == ops  # must be a list, not a dict


# ---------------------------------------------------------------------------
# delete_form
# ---------------------------------------------------------------------------


def test_delete_form_success():
    client = _make_client()
    mock = _patch_session(client, _mock_response(204))

    client.delete_form("form123")  # must not raise

    assert "form123" in mock.call_args[0][1]


def test_delete_form_error_raises():
    client = _make_client()
    _patch_session(client, _mock_response(404, {"code": "NOT_FOUND", "description": "Gone"}))

    with pytest.raises(TypeformAPIError):
        client.delete_form("form123")


# ---------------------------------------------------------------------------
# get/update form messages
# ---------------------------------------------------------------------------


def test_get_form_messages_success():
    client = _make_client()
    messages = {"label.buttonHint.default": "Press Enter ↵"}
    _patch_session(client, _mock_response(200, messages))

    result = client.get_form_messages("form123")

    assert result == messages


def test_update_form_messages_success():
    client = _make_client()
    messages = {"label.buttonHint.default": "Go ahead"}
    mock = _patch_session(client, _mock_response(200, messages))

    result = client.update_form_messages("form123", messages)

    assert result == messages
    assert mock.call_args[1]["json"] == messages


# ---------------------------------------------------------------------------
# list_forms
# ---------------------------------------------------------------------------


def test_list_forms_returns_form_list():
    from src.typeform.models import FormList
    client = _make_client()
    body = {
        "total_items": 2,
        "page_count": 1,
        "items": [
            {"id": "abc", "title": "Form 1"},
            {"id": "def", "title": "Form 2"},
        ],
    }
    _patch_session(client, _mock_response(200, body))

    result = client.list_forms(page_size=5)

    assert isinstance(result, FormList)
    assert result.total_items == 2
    assert result.items[0].id == "abc"


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------


def test_list_webhooks():
    from src.typeform.models import WebhookList
    client = _make_client()
    body = {"total_items": 1, "page_count": 1, "items": [{"url": "https://example.com/hook", "enabled": True}]}
    _patch_session(client, _mock_response(200, body))

    result = client.list_webhooks("form123")

    assert isinstance(result, WebhookList)
    assert result.total_items == 1


def test_upsert_webhook():
    from src.typeform.models import Webhook, WebhookUpsert
    client = _make_client()
    returned = {"url": "https://example.com/hook", "enabled": True, "tag": "my-hook"}
    mock = _patch_session(client, _mock_response(200, returned))

    hook = WebhookUpsert(url="https://example.com/hook")
    result = client.upsert_webhook("form123", "my-hook", hook)

    assert isinstance(result, Webhook)
    assert "my-hook" in mock.call_args[0][1]


def test_delete_webhook():
    client = _make_client()
    mock = _patch_session(client, _mock_response(204))

    client.delete_webhook("form123", "my-hook")

    assert "my-hook" in mock.call_args[0][1]


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


def test_list_responses_returns_response_list():
    from src.typeform.models import ResponseList
    client = _make_client()
    body = {
        "total_items": 1,
        "page_count": 1,
        "items": [{
            "response_id": "resp1",
            "submitted_at": "2026-01-01T12:00:00Z",
            "answers": [],
        }],
    }
    _patch_session(client, _mock_response(200, body))

    result = client.list_responses("form123", page_size=10)

    assert isinstance(result, ResponseList)
    assert result.items[0].response_id == "resp1"


def test_delete_responses():
    client = _make_client()
    mock = _patch_session(client, _mock_response(204))

    client.delete_responses("form123", ["tok1", "tok2"])

    params = mock.call_args[1]["params"]
    assert "tok1" in params["included_tokens"]


# ---------------------------------------------------------------------------
# get_me
# ---------------------------------------------------------------------------


def test_get_me():
    from src.typeform.models import Account
    client = _make_client()
    _patch_session(client, _mock_response(200, {"alias": "tester", "email": "test@example.com"}))

    result = client.get_me()

    assert isinstance(result, Account)
    assert result.email == "test@example.com"


# ---------------------------------------------------------------------------
# duplicate_form
# ---------------------------------------------------------------------------


def test_duplicate_form_success():
    client = _make_client()
    mock = _patch_session(client, _mock_response(200, {"id": "copy123", "title": "Test Form (copy)"}))

    result = client.duplicate_form("form123")

    assert result["id"] == "copy123"
    call_url = mock.call_args[0][1]
    assert "form123/duplicate" in call_url


def test_duplicate_form_error_raises():
    client = _make_client()
    _patch_session(client, _mock_response(404, {"code": "NOT_FOUND", "description": "Not found"}))

    with pytest.raises(TypeformAPIError):
        client.duplicate_form("nonexistent")


# ---------------------------------------------------------------------------
# create_form_raw / update_form_raw
# ---------------------------------------------------------------------------


def test_create_form_raw_success():
    client = _make_client()
    raw = {"title": "Raw Form", "fields": []}
    mock = _patch_session(client, _mock_response(200, {"id": "raw123", "title": "Raw Form"}))

    result = client.create_form_raw(raw)

    assert result["id"] == "raw123"
    assert mock.call_args[1]["json"] == raw


def test_update_form_raw_success():
    client = _make_client()
    raw = {"title": "Updated Raw"}
    mock = _patch_session(client, _mock_response(200, {"id": "form123", "title": "Updated Raw"}))

    result = client.update_form_raw("form123", raw)

    assert result["title"] == "Updated Raw"
    assert "form123" in mock.call_args[0][1]


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------


def test_client_default_timeout():
    client = _make_client()
    assert client.timeout == 30


def test_client_custom_timeout():
    client = TypeformClient(token="tok", timeout=60)
    assert client.timeout == 60


def test_request_passes_timeout_to_session():
    client = TypeformClient(token="tok", timeout=15)
    mock = _patch_session(client, _mock_response(200, {"alias": "a", "email": "b@b.com"}))

    client.get_me()

    assert mock.call_args[1]["timeout"] == 15


# ---------------------------------------------------------------------------
# Retry on 429 / 503
# ---------------------------------------------------------------------------


def test_retry_on_429_then_success():
    client = _make_client()
    resp_429 = _mock_response(429, {"code": "RATE_LIMITED", "description": "Too many requests"})
    resp_200 = _mock_response(200, {"alias": "ok", "email": "ok@ok.com"})
    client._session.request = MagicMock(side_effect=[resp_429, resp_200])

    import unittest.mock as um
    with um.patch("time.sleep"):
        result = client.get_me()

    assert result.email == "ok@ok.com"
    assert client._session.request.call_count == 2


def test_retry_on_503_exhausted_raises():
    client = TypeformClient(token="tok")
    resp_503 = _mock_response(503, {"code": "SERVICE_UNAVAILABLE", "description": "Down"})
    client._session.request = MagicMock(return_value=resp_503)

    import unittest.mock as um
    with um.patch("time.sleep"):
        with pytest.raises(TypeformAPIError) as exc_info:
            client.get_me()

    assert exc_info.value.status_code == 503
    assert client._session.request.call_count == 4  # 1 attempt + 3 retries


# ---------------------------------------------------------------------------
# download_response_files size limit
# ---------------------------------------------------------------------------


def test_download_response_files_size_limit():
    client = _make_client()
    big_content = b"x" * (11 * 1024 * 1024)  # 11 MB
    mock_resp = _mock_response(200)
    mock_resp.content = big_content
    _patch_session(client, mock_resp)

    with pytest.raises(ValueError, match="too large"):
        client.download_response_files("f", "r", "fid", "file.pdf", max_bytes=10 * 1024 * 1024)


def test_download_response_files_within_limit():
    client = _make_client()
    small_content = b"hello world"
    mock_resp = _mock_response(200)
    mock_resp.content = small_content
    _patch_session(client, mock_resp)

    result = client.download_response_files("f", "r", "fid", "file.txt")
    assert result == small_content


# ---------------------------------------------------------------------------
# Themes
# ---------------------------------------------------------------------------


def test_list_themes():
    from src.typeform.models import ThemeList
    client = _make_client()
    body = {"total_items": 2, "page_count": 1, "items": [{"name": "Default", "id": "t1"}, {"name": "Dark", "id": "t2"}]}
    _patch_session(client, _mock_response(200, body))

    result = client.list_themes()

    assert isinstance(result, ThemeList)
    assert result.total_items == 2


# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------


def test_list_workspaces():
    from src.typeform.models import WorkspaceList
    client = _make_client()
    body = {"total_items": 1, "page_count": 1, "items": [{"id": "ws1", "name": "My Workspace"}]}
    _patch_session(client, _mock_response(200, body))

    result = client.list_workspaces()

    assert isinstance(result, WorkspaceList)
    assert result.items[0].name == "My Workspace"
