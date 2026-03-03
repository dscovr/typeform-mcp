"""
Typeform MCP Server

Exposes the Typeform API as MCP (Model Context Protocol) tools.

Direct start:
    TYPEFORM_TOKEN=tfp_... uv run python -m typeform.server

Install and run as a tool:
    uv tool install .
    TYPEFORM_TOKEN=tfp_... typeform-mcp

Install from GitHub:
    uvx --from git+https://github.com/dscovr/typeform-mcp typeform-mcp
"""

from __future__ import annotations

import base64
import csv
import functools
import io
import json
import logging
import os
import sys
import threading

from mcp.server.fastmcp import FastMCP

from .client import TypeformAPIError, TypeformClient
from .models import (
    ImageCreate,
    ThemeBackground,
    ThemeColors,
    ThemeCreate,
    WebhookUpsert,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("typeform_mcp")

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "typeform",
    instructions=(
        "Tools for managing Typeform forms: create, update, delete forms, "
        "read responses, manage webhooks, themes, images, and workspaces."
    ),
)

# ---------------------------------------------------------------------------
# Client singleton — thread-safe (double-checked locking)
# ---------------------------------------------------------------------------

_typeform_client: TypeformClient | None = None
_client_lock = threading.Lock()


def _client() -> TypeformClient:
    global _typeform_client
    if _typeform_client is None:
        with _client_lock:
            if _typeform_client is None:
                _typeform_client = TypeformClient()
    return _typeform_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB


def _ok(data: object) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


def _tool(fn):
    """
    Decorator that adds centralised error handling to every MCP tool.

    Catches TypeformAPIError and any unexpected Exception, logs them to
    stderr, and returns a structured JSON error response instead of
    propagating the exception (which would crash the MCP process).
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except TypeformAPIError as e:
            logger.error(
                "[%s] API error %d %s: %s",
                fn.__name__, e.status_code, e.code, e.description,
            )
            return json.dumps({
                "error": True,
                "status_code": e.status_code,
                "code": e.code,
                "description": e.description,
                "details": e.details,
            }, indent=2)
        except Exception as e:
            logger.exception("[%s] Unexpected error: %s", fn.__name__, e)
            return json.dumps({
                "error": True,
                "code": "INTERNAL_ERROR",
                "description": str(e),
            }, indent=2)
    return wrapper


def _build_theme_create(theme: dict) -> ThemeCreate:
    """Builds a ThemeCreate object from a raw dictionary."""
    return ThemeCreate(
        name=theme["name"],
        font=theme.get("font"),
        colors=ThemeColors(**theme["colors"]) if theme.get("colors") else None,
        background=ThemeBackground(**theme["background"]) if theme.get("background") else None,
        has_transparent_button=theme.get("has_transparent_button"),
        visibility=theme.get("visibility"),
    )


# ===========================================================================
# ACCOUNT
# ===========================================================================


@mcp.tool()
@_tool
def typeform_get_account() -> str:
    """
    Returns information about the current Typeform account.
    Useful to verify the token is working and to see the alias and email.
    """
    me = _client().get_me()
    return _ok(me.model_dump())


# ===========================================================================
# FORMS
# ===========================================================================


@mcp.tool()
@_tool
def typeform_list_forms(
    page: int = 1,
    page_size: int = 10,
    search: str = "",
    workspace_id: str = "",
) -> str:
    """
    Lists the Typeform forms in the account with pagination and optional search.

    Args:
        page:         Page number (default 1).
        page_size:    Results per page, max 200 (default 10).
        search:       Text to filter forms by title.
        workspace_id: Filter by a specific workspace ID.
    """
    page_size = min(max(1, page_size), 200)
    result = _client().list_forms(
        page=page,
        page_size=page_size,
        search=search or None,
        workspace_id=workspace_id or None,
    )
    return _ok({
        "total_items": result.total_items,
        "page_count": result.page_count,
        "items": [{"id": f.id, "title": f.title, "last_updated_at": f.last_updated_at} for f in result.items],
    })


@mcp.tool()
@_tool
def typeform_get_form(form_id: str) -> str:
    """
    Returns the full definition of a Typeform form (fields, logic, screens).

    Args:
        form_id: Form ID (e.g. "Zh4mK7He").
    """
    return _ok(_client().get_form(form_id))


@mcp.tool()
@_tool
def typeform_create_form(form_definition: dict) -> str:
    """
    Creates a new Typeform form.

    Args:
        form_definition: Complete form definition as a JSON object. Structure:
            {
              "title": "Form title",                           (required)
              "fields": [                                      (optional)
                {
                  "ref": "field_1",
                  "title": "Question text",
                  "type": "multiple_choice|short_text|opinion_scale|...",
                  "properties": { "choices": [{"ref": "a", "label": "Option A"}] },
                  "validations": { "required": true }
                }
              ],
              "hidden": ["sid", "source"],
              "welcome_screens": [{"ref": "welcome", "title": "Welcome!"}],
              "thankyou_screens": [{"ref": "end", "title": "Thank you!"}],
              "logic": [
                {
                  "type": "field",
                  "ref": "field_1",
                  "actions": [{
                    "action": "jump",
                    "details": {"to": {"type": "field", "value": "field_2"}},
                    "condition": {"op": "is", "vars": [
                      {"type": "field", "value": "field_1"},
                      {"type": "choice", "value": "choice_ref"}
                    ]}
                  }]
                }
              ]
            }
    """
    data = _client().create_form_raw(form_definition)
    return _ok({"id": data.get("id"), "title": data.get("title"), "_links": data.get("_links")})


@mcp.tool()
@_tool
def typeform_update_form(form_id: str, form_definition: dict) -> str:
    """
    Fully replaces the definition of an existing form (PUT).
    Use typeform_patch_form for partial updates.

    Args:
        form_id:         ID of the form to update.
        form_definition: New complete form definition (same schema as typeform_create_form).
    """
    data = _client().update_form_raw(form_id, form_definition)
    return _ok({"id": data.get("id"), "title": data.get("title")})


@mcp.tool()
@_tool
def typeform_patch_form(form_id: str, patch: dict) -> str:
    """
    Partially updates a Typeform form (PATCH).
    Only send the fields you want to change.

    Args:
        form_id: Form ID.
        patch:   Object with only the fields to change, e.g. {"title": "New title"}.
    """
    return _ok(_client().patch_form(form_id, patch))


@mcp.tool()
@_tool
def typeform_delete_form(form_id: str) -> str:
    """
    Permanently deletes a Typeform form and all its responses.
    WARNING: irreversible operation.

    Args:
        form_id: ID of the form to delete.
    """
    _client().delete_form(form_id)
    return _ok({
        "deleted": True,
        "form_id": form_id,
        "warning": "Irreversible operation: form and all its responses permanently deleted.",
    })


@mcp.tool()
@_tool
def typeform_duplicate_form(form_id: str) -> str:
    """
    Duplicates an existing Typeform form creating an identical copy.

    Args:
        form_id: ID of the form to duplicate.
    """
    data = _client().duplicate_form(form_id)
    return _ok({"id": data.get("id"), "title": data.get("title"), "_links": data.get("_links")})


@mcp.tool()
@_tool
def typeform_get_messages(form_id: str) -> str:
    """
    Returns the custom messages of a form (button texts, labels, etc.).

    Args:
        form_id: Form ID.
    """
    return _ok(_client().get_form_messages(form_id))


@mcp.tool()
@_tool
def typeform_update_messages(form_id: str, messages: dict) -> str:
    """
    Updates the custom messages of a form.

    Args:
        form_id:  Form ID.
        messages: Key→value dictionary of messages, e.g.
                  {"label.buttonHint.default": "Press Enter ↵"}.
    """
    return _ok(_client().update_form_messages(form_id, messages))


# ===========================================================================
# RESPONSES
# ===========================================================================


@mcp.tool()
@_tool
def typeform_list_responses(
    form_id: str,
    page_size: int = 25,
    since: str = "",
    until: str = "",
    query: str = "",
    after: str = "",
    before: str = "",
    sort: str = "submitted_at,desc",
    response_type: str = "",
    fields: str = "",
) -> str:
    """
    Retrieves responses for a form with optional filters.

    Args:
        form_id:       Form ID.
        page_size:     Number of responses to return (max 1000, default 25).
        since:         Filter responses after this date (ISO 8601, e.g. "2026-01-01T00:00:00Z").
        until:         Filter responses before this date (ISO 8601).
        query:         Free-text search within responses.
        after:         Cursor token for next page (forward pagination).
        before:        Cursor token for previous page (backward pagination).
        sort:          Sort order: "submitted_at,desc" (default) or "submitted_at,asc".
        response_type: Filter by type: "completed", "partial", "started" (or comma-separated combinations).
        fields:        Comma-separated field refs to include (e.g. "name,age"). Empty = all.
    """
    page_size = min(max(1, page_size), 1000)
    parsed_fields = [f.strip() for f in fields.split(",") if f.strip()] if fields else None
    result = _client().list_responses(
        form_id,
        page_size=page_size,
        since=since or None,
        until=until or None,
        query=query or None,
        after=after or None,
        before=before or None,
        sort=sort,
        response_type=response_type or None,
        fields=parsed_fields,
    )
    items = []
    for r in result.items:
        item = {
            "response_id": r.response_id,
            "response_type": r.response_type,
            "submitted_at": r.submitted_at,
            "landed_at": r.landed_at,
            "answers": r.answers_by_ref(),
        }
        if r.hidden:
            item["hidden"] = r.hidden
        if r.calculated:
            item["calculated"] = r.calculated
        if r.metadata:
            item["metadata"] = r.metadata.model_dump(exclude_none=True)
        items.append(item)
    return _ok({
        "total_items": result.total_items,
        "page_count": result.page_count,
        "items": items,
    })


@mcp.tool()
@_tool
def typeform_export_responses_csv(
    form_id: str,
    since: str = "",
    until: str = "",
    sort: str = "submitted_at,asc",
) -> str:
    """
    Exports all responses for a form as CSV.
    Handles pagination automatically and collects up to 10,000 responses.

    Args:
        form_id: Form ID.
        since:   Filter responses after this date (ISO 8601, e.g. "2026-01-01T00:00:00Z").
        until:   Filter responses before this date (ISO 8601).
        sort:    Sort order: "submitted_at,asc" (default) or "submitted_at,desc".

    Returns:
        CSV text with headers in the first row.
    """
    all_items = []
    after: str | None = None
    max_responses = 10_000

    while len(all_items) < max_responses:
        result = _client().list_responses(
            form_id,
            page_size=1000,
            since=since or None,
            until=until or None,
            sort=sort,
            after=after,
        )
        all_items.extend(result.items)
        if len(result.items) < 1000 or len(all_items) >= result.total_items:
            break
        after = result.items[-1].response_id

    if not all_items:
        return "response_id,submitted_at\n"

    # Collect all answer keys across all responses
    all_keys: list[str] = []
    seen: set[str] = set()
    for r in all_items:
        for k in r.answers_by_ref():
            if k not in seen:
                all_keys.append(k)
                seen.add(k)

    header = ["response_id", "submitted_at", "landed_at"] + all_keys

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for r in all_items:
        answers = r.answers_by_ref()
        row = [
            r.response_id,
            r.submitted_at or "",
            r.landed_at or "",
        ] + [answers.get(k, "") for k in all_keys]
        writer.writerow(row)

    return buf.getvalue()


@mcp.tool()
@_tool
def typeform_delete_responses(form_id: str, response_tokens: list[str]) -> str:
    """
    Deletes specific responses from a form.
    WARNING: irreversible operation.

    Args:
        form_id:         Form ID.
        response_tokens: List of response tokens (response_id) to delete.
    """
    if not response_tokens:
        return _ok({"deleted": False, "count": 0, "reason": "No tokens provided."})
    _client().delete_responses(form_id, response_tokens)
    return _ok({
        "deleted": True,
        "count": len(response_tokens),
        "warning": "Irreversible operation: responses permanently deleted.",
    })


@mcp.tool()
@_tool
def typeform_download_file(
    form_id: str,
    response_id: str,
    field_id: str,
    filename: str,
) -> str:
    """
    Downloads a file attached to a response (e.g. from a file_upload field).
    Returns the content as base64. Limit: 10 MB.

    Args:
        form_id:     Form ID.
        response_id: Response ID (token).
        field_id:    ID of the file_upload field.
        filename:    Name of the file to download.
    """
    content = _client().download_response_files(form_id, response_id, field_id, filename)
    return _ok({
        "filename": filename,
        "size_bytes": len(content),
        "content_base64": base64.b64encode(content).decode(),
    })


# ===========================================================================
# WEBHOOKS
# ===========================================================================


@mcp.tool()
@_tool
def typeform_list_webhooks(form_id: str) -> str:
    """
    Lists all webhooks configured for a form.

    Args:
        form_id: Form ID.
    """
    result = _client().list_webhooks(form_id)
    return _ok(result.model_dump())


@mcp.tool()
@_tool
def typeform_get_webhook(form_id: str, tag: str) -> str:
    """
    Returns the details of a specific webhook.

    Args:
        form_id: Form ID.
        tag:     Unique identifier of the webhook within the form.
    """
    w = _client().get_webhook(form_id, tag)
    return _ok(w.model_dump())


@mcp.tool()
@_tool
def typeform_upsert_webhook(
    form_id: str,
    tag: str,
    url: str,
    enabled: bool = True,
    secret: str = "",
) -> str:
    """
    Creates or updates a webhook for a form (PUT).

    Args:
        form_id: Form ID.
        tag:     Unique identifier for the webhook (e.g. "my-webhook").
        url:     Destination URL (must be HTTPS).
        enabled: Enable/disable the webhook (default True).
        secret:  Secret for verifying the payload signature (optional).
    """
    hook = WebhookUpsert(url=url, enabled=enabled, secret=secret or None)
    result = _client().upsert_webhook(form_id, tag, hook)
    return _ok(result.model_dump())


@mcp.tool()
@_tool
def typeform_delete_webhook(form_id: str, tag: str) -> str:
    """
    Deletes a webhook from a form.

    Args:
        form_id: Form ID.
        tag:     Identifier of the webhook to delete.
    """
    _client().delete_webhook(form_id, tag)
    return _ok({"deleted": True, "tag": tag})


# ===========================================================================
# THEMES
# ===========================================================================


@mcp.tool()
@_tool
def typeform_list_themes(page: int = 1, page_size: int = 10) -> str:
    """
    Lists the available themes in the account.

    Args:
        page:      Page number.
        page_size: Results per page.
    """
    result = _client().list_themes(page=page, page_size=page_size)
    return _ok({
        "total_items": result.total_items,
        "items": [{"id": t.id, "name": t.name, "visibility": t.visibility} for t in result.items],
    })


@mcp.tool()
@_tool
def typeform_get_theme(theme_id: str) -> str:
    """
    Returns the details of a specific theme.

    Args:
        theme_id: Theme ID.
    """
    t = _client().get_theme(theme_id)
    return _ok(t.model_dump())


@mcp.tool()
@_tool
def typeform_create_theme(theme: dict) -> str:
    """
    Creates a new custom theme.

    Args:
        theme: Theme definition. Structure:
            {
              "name": "Theme name",          (required)
              "font": "Roboto",
              "colors": {
                "question": "#000000",
                "answer": "#0000FF",
                "button": "#FF0000",
                "background": "#FFFFFF"
              },
              "background": {
                "href": "image-url",
                "brightness": 0,
                "layout": "fullscreen"
              },
              "has_transparent_button": false,
              "visibility": "private"
            }
    """
    t = _client().create_theme(_build_theme_create(theme))
    return _ok(t.model_dump())


@mcp.tool()
@_tool
def typeform_update_theme(theme_id: str, theme: dict) -> str:
    """
    Fully replaces a theme (PUT).

    Args:
        theme_id: ID of the theme to update.
        theme:    New complete definition (same schema as typeform_create_theme).
    """
    t = _client().update_theme(theme_id, _build_theme_create(theme))
    return _ok(t.model_dump())


@mcp.tool()
@_tool
def typeform_patch_theme(theme_id: str, patch: dict) -> str:
    """
    Partially updates a theme (PATCH).

    Args:
        theme_id: Theme ID.
        patch:    Object with only the fields to change, e.g. {"name": "New name"}.
    """
    t = _client().patch_theme(theme_id, patch)
    return _ok(t.model_dump())


@mcp.tool()
@_tool
def typeform_delete_theme(theme_id: str) -> str:
    """
    Deletes a theme.

    Args:
        theme_id: ID of the theme to delete.
    """
    _client().delete_theme(theme_id)
    return _ok({"deleted": True, "theme_id": theme_id})


# ===========================================================================
# IMAGES
# ===========================================================================


@mcp.tool()
@_tool
def typeform_list_images() -> str:
    """Lists all images uploaded to the account."""
    result = _client().list_images()
    return _ok({
        "total_items": result.total_items,
        "items": [
            {"id": img.id, "file_name": img.file_name, "width": img.width, "height": img.height}
            for img in result.items
        ],
    })


@mcp.tool()
@_tool
def typeform_get_image(image_id: str) -> str:
    """
    Returns the metadata of a specific image.

    Args:
        image_id: Image ID.
    """
    img = _client().get_image(image_id)
    return _ok(img.model_dump())


@mcp.tool()
@_tool
def typeform_create_image(file_name: str, image_base64: str, media_type: str) -> str:
    """
    Uploads a new image to the account (base64-encoded).

    Args:
        file_name:    File name (e.g. "logo.png").
        image_base64: Image content in base64 format.
        media_type:   MIME type: "image/jpeg", "image/png", "image/gif", etc.
    """
    payload = ImageCreate(file_name=file_name, image=image_base64, media_type=media_type)
    img = _client().create_image(payload)
    return _ok(img.model_dump())


@mcp.tool()
@_tool
def typeform_delete_image(image_id: str) -> str:
    """
    Deletes an image from the account.

    Args:
        image_id: ID of the image to delete.
    """
    _client().delete_image(image_id)
    return _ok({"deleted": True, "image_id": image_id})


# ===========================================================================
# WORKSPACES
# ===========================================================================


@mcp.tool()
@_tool
def typeform_list_workspaces(
    page: int = 1,
    page_size: int = 10,
    search: str = "",
) -> str:
    """
    Lists the workspaces in the account.

    Args:
        page:      Page number.
        page_size: Results per page.
        search:    Text to filter by workspace name.
    """
    result = _client().list_workspaces(page=page, page_size=page_size, search=search or None)
    return _ok({
        "total_items": result.total_items,
        "items": [{"id": w.id, "name": w.name, "default": w.default} for w in result.items],
    })


@mcp.tool()
@_tool
def typeform_get_workspace(workspace_id: str) -> str:
    """
    Returns the details of a specific workspace.

    Args:
        workspace_id: Workspace ID.
    """
    w = _client().get_workspace(workspace_id)
    return _ok(w.model_dump())


@mcp.tool()
@_tool
def typeform_create_workspace(name: str) -> str:
    """
    Creates a new workspace.

    Args:
        name: Workspace name.
    """
    w = _client().create_workspace(name)
    return _ok(w.model_dump())


@mcp.tool()
@_tool
def typeform_update_workspace(workspace_id: str, name: str) -> str:
    """
    Renames a workspace.

    Args:
        workspace_id: Workspace ID.
        name:         New name for the workspace.
    """
    w = _client().update_workspace(workspace_id, name)
    return _ok(w.model_dump())


@mcp.tool()
@_tool
def typeform_delete_workspace(workspace_id: str) -> str:
    """
    Deletes a workspace (must be empty).

    Args:
        workspace_id: ID of the workspace to delete.
    """
    _client().delete_workspace(workspace_id)
    return _ok({"deleted": True, "workspace_id": workspace_id})


# ===========================================================================
# TRANSLATIONS
# ===========================================================================


@mcp.tool()
@_tool
def typeform_get_translation_statuses(form_id: str) -> str:
    """
    Returns the status of available translations for a form.

    Args:
        form_id: Form ID.
    """
    statuses = _client().get_translation_statuses(form_id)
    return _ok([s.model_dump() for s in statuses])


@mcp.tool()
@_tool
def typeform_list_translations(form_id: str) -> str:
    """
    Returns the full payload of all translations for a form.

    Args:
        form_id: Form ID.
    """
    return _ok(_client().list_translations(form_id))


@mcp.tool()
@_tool
def typeform_update_translation(form_id: str, language: str, payload: dict) -> str:
    """
    Creates or updates the translation of a form in a specific language.

    Args:
        form_id:  Form ID.
        language: ISO 639-1 language code (e.g. "en", "fr", "de").
        payload:  Object with the translated strings (same schema as typeform_list_translations).
    """
    return _ok(_client().update_translation(form_id, language, payload))


@mcp.tool()
@_tool
def typeform_delete_translation(form_id: str, language: str) -> str:
    """
    Deletes the translation of a form in a specific language.

    Args:
        form_id:  Form ID.
        language: ISO 639-1 language code (e.g. "en", "fr").
    """
    _client().delete_translation(form_id, language)
    return _ok({"deleted": True, "form_id": form_id, "language": language})


@mcp.tool()
@_tool
def typeform_auto_translate(form_id: str, target_languages: list[str]) -> str:
    """
    Triggers automatic translation of a form into the specified languages.

    Args:
        form_id:          Form ID.
        target_languages: List of ISO 639-1 language codes (e.g. ["en", "fr", "de"]).
    """
    return _ok(_client().auto_translate(form_id, target_languages))


# ===========================================================================
# Entrypoint
# ===========================================================================


def main() -> None:
    token = os.environ.get("TYPEFORM_TOKEN")
    if not token:
        print(
            "Error: TYPEFORM_TOKEN environment variable is not set.\n"
            "Usage: TYPEFORM_TOKEN=tfp_... typeform-mcp",
            file=sys.stderr,
        )
        sys.exit(1)

    logger.info("Starting Typeform MCP server (stdio)")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
