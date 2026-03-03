"""
Typeform MCP Server

Espone le API Typeform come strumenti MCP (Model Context Protocol).

Avvio diretto:
    TYPEFORM_TOKEN=tfp_... uv run python -m typeform.server

Installazione e uso come tool:
    uv tool install .
    TYPEFORM_TOKEN=tfp_... typeform-mcp

Installazione da GitHub:
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
        "Strumenti per gestire form Typeform: creare, aggiornare, eliminare form, "
        "leggere risposte, gestire webhook, temi, immagini e workspace."
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
    Decorator che aggiunge error handling centralizzato a ogni tool MCP.

    Cattura TypeformAPIError e qualsiasi Exception non prevista,
    li logga su stderr e restituisce una risposta JSON di errore strutturata
    invece di propagare l'eccezione (che crasherebbe il processo MCP).
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
    """Costruisce un ThemeCreate da un dizionario raw."""
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
    Restituisce le informazioni sull'account Typeform corrente.
    Utile per verificare che il token funzioni e per vedere alias ed email.
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
    Elenca i form Typeform dell'account con paginazione e ricerca opzionale.

    Args:
        page:         Numero di pagina (default 1).
        page_size:    Risultati per pagina, max 200 (default 10).
        search:       Testo per filtrare i form per titolo.
        workspace_id: Filtra per ID workspace specifico.
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
    Restituisce la definizione completa di un form Typeform (campi, logica, schermate).

    Args:
        form_id: ID del form (es. "Zh4mK7He").
    """
    return _ok(_client().get_form(form_id))


@mcp.tool()
@_tool
def typeform_create_form(form_definition: dict) -> str:
    """
    Crea un nuovo form Typeform.

    Args:
        form_definition: Definizione completa del form come oggetto JSON. Struttura:
            {
              "title": "Titolo form",                          (obbligatorio)
              "fields": [                                      (opzionale)
                {
                  "ref": "campo_1",
                  "title": "Testo della domanda",
                  "type": "multiple_choice|short_text|opinion_scale|...",
                  "properties": { "choices": [{"ref": "a", "label": "Opzione A"}] },
                  "validations": { "required": true }
                }
              ],
              "hidden": ["sid", "source"],
              "welcome_screens": [{"ref": "welcome", "title": "Benvenuto!"}],
              "thankyou_screens": [{"ref": "end", "title": "Grazie!"}],
              "logic": [
                {
                  "type": "field",
                  "ref": "campo_1",
                  "actions": [{
                    "action": "jump",
                    "details": {"to": {"type": "field", "value": "campo_2"}},
                    "condition": {"op": "is", "vars": [
                      {"type": "field", "value": "campo_1"},
                      {"type": "choice", "value": "ref_scelta"}
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
    Sostituisce interamente la definizione di un form esistente (PUT).
    Usa typeform_patch_form per aggiornamenti parziali.

    Args:
        form_id:         ID del form da aggiornare.
        form_definition: Nuova definizione completa del form (stesso schema di typeform_create_form).
    """
    data = _client().update_form_raw(form_id, form_definition)
    return _ok({"id": data.get("id"), "title": data.get("title")})


@mcp.tool()
@_tool
def typeform_patch_form(form_id: str, patch: dict) -> str:
    """
    Aggiorna parzialmente un form Typeform (PATCH).
    Invia solo i campi che vuoi modificare.

    Args:
        form_id: ID del form.
        patch:   Oggetto con i soli campi da modificare, es. {"title": "Nuovo titolo"}.
    """
    return _ok(_client().patch_form(form_id, patch))


@mcp.tool()
@_tool
def typeform_delete_form(form_id: str) -> str:
    """
    Elimina definitivamente un form Typeform e tutte le sue risposte.
    ATTENZIONE: operazione irreversibile.

    Args:
        form_id: ID del form da eliminare.
    """
    _client().delete_form(form_id)
    return _ok({
        "deleted": True,
        "form_id": form_id,
        "warning": "Operazione irreversibile: form e tutte le risposte eliminate permanentemente.",
    })


@mcp.tool()
@_tool
def typeform_duplicate_form(form_id: str) -> str:
    """
    Duplica un form Typeform esistente creando una copia identica.

    Args:
        form_id: ID del form da duplicare.
    """
    data = _client().duplicate_form(form_id)
    return _ok({"id": data.get("id"), "title": data.get("title"), "_links": data.get("_links")})


@mcp.tool()
@_tool
def typeform_get_messages(form_id: str) -> str:
    """
    Restituisce i messaggi personalizzati di un form (testi pulsanti, label, ecc.).

    Args:
        form_id: ID del form.
    """
    return _ok(_client().get_form_messages(form_id))


@mcp.tool()
@_tool
def typeform_update_messages(form_id: str, messages: dict) -> str:
    """
    Aggiorna i messaggi personalizzati di un form.

    Args:
        form_id:  ID del form.
        messages: Dizionario chiave→valore dei messaggi, es.
                  {"label.buttonHint.default": "Premi Invio ↵"}.
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
    Recupera le risposte di un form con filtri opzionali.

    Args:
        form_id:       ID del form.
        page_size:     Numero di risposte da restituire (max 1000, default 25).
        since:         Filtra risposte dopo questa data (ISO 8601, es. "2026-01-01T00:00:00Z").
        until:         Filtra risposte prima di questa data (ISO 8601).
        query:         Testo libero per cercare nelle risposte.
        after:         Token cursore per pagina successiva (paginazione forward).
        before:        Token cursore per pagina precedente (paginazione backward).
        sort:          Ordinamento: "submitted_at,desc" (default) o "submitted_at,asc".
        response_type: Filtra per tipo: "completed", "partial", "started" (o combinazioni separate da virgola).
        fields:        Ref dei campi da includere, separati da virgola (es. "nome,eta"). Vuoto = tutti.
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
    Esporta tutte le risposte di un form in formato CSV.
    Gestisce la paginazione automaticamente e raccoglie fino a 10.000 risposte.

    Args:
        form_id: ID del form.
        since:   Filtra risposte dopo questa data (ISO 8601, es. "2026-01-01T00:00:00Z").
        until:   Filtra risposte prima di questa data (ISO 8601).
        sort:    Ordinamento: "submitted_at,asc" (default) o "submitted_at,desc".

    Returns:
        Testo CSV con header nella prima riga.
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
    Elimina risposte specifiche da un form.
    ATTENZIONE: operazione irreversibile.

    Args:
        form_id:         ID del form.
        response_tokens: Lista di token (response_id) delle risposte da eliminare.
    """
    if not response_tokens:
        return _ok({"deleted": False, "count": 0, "reason": "Nessun token fornito."})
    _client().delete_responses(form_id, response_tokens)
    return _ok({
        "deleted": True,
        "count": len(response_tokens),
        "warning": "Operazione irreversibile: risposte eliminate permanentemente.",
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
    Scarica un file allegato a una risposta (es. da un campo file_upload).
    Restituisce il contenuto in base64. Limite: 10 MB.

    Args:
        form_id:     ID del form.
        response_id: ID della risposta (token).
        field_id:    ID del campo file_upload.
        filename:    Nome del file da scaricare.
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
    Elenca tutti i webhook configurati per un form.

    Args:
        form_id: ID del form.
    """
    result = _client().list_webhooks(form_id)
    return _ok(result.model_dump())


@mcp.tool()
@_tool
def typeform_get_webhook(form_id: str, tag: str) -> str:
    """
    Restituisce i dettagli di un webhook specifico.

    Args:
        form_id: ID del form.
        tag:     Identificatore univoco del webhook nel form.
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
    Crea o aggiorna un webhook per un form (PUT).

    Args:
        form_id: ID del form.
        tag:     Identificatore univoco del webhook (es. "my-webhook").
        url:     URL di destinazione (deve essere HTTPS).
        enabled: Attiva/disattiva il webhook (default True).
        secret:  Segreto per verificare la firma del payload (opzionale).
    """
    hook = WebhookUpsert(url=url, enabled=enabled, secret=secret or None)
    result = _client().upsert_webhook(form_id, tag, hook)
    return _ok(result.model_dump())


@mcp.tool()
@_tool
def typeform_delete_webhook(form_id: str, tag: str) -> str:
    """
    Elimina un webhook da un form.

    Args:
        form_id: ID del form.
        tag:     Identificatore del webhook da eliminare.
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
    Elenca i temi disponibili nell'account.

    Args:
        page:      Numero di pagina.
        page_size: Risultati per pagina.
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
    Restituisce i dettagli di un tema specifico.

    Args:
        theme_id: ID del tema.
    """
    t = _client().get_theme(theme_id)
    return _ok(t.model_dump())


@mcp.tool()
@_tool
def typeform_create_theme(theme: dict) -> str:
    """
    Crea un nuovo tema personalizzato.

    Args:
        theme: Definizione del tema. Struttura:
            {
              "name": "Nome tema",           (obbligatorio)
              "font": "Roboto",
              "colors": {
                "question": "#000000",
                "answer": "#0000FF",
                "button": "#FF0000",
                "background": "#FFFFFF"
              },
              "background": {
                "href": "url-immagine",
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
    Sostituisce interamente un tema (PUT).

    Args:
        theme_id: ID del tema da aggiornare.
        theme:    Nuova definizione completa (stesso schema di typeform_create_theme).
    """
    t = _client().update_theme(theme_id, _build_theme_create(theme))
    return _ok(t.model_dump())


@mcp.tool()
@_tool
def typeform_patch_theme(theme_id: str, patch: dict) -> str:
    """
    Aggiorna parzialmente un tema (PATCH).

    Args:
        theme_id: ID del tema.
        patch:    Oggetto con i soli campi da modificare, es. {"name": "Nuovo nome"}.
    """
    t = _client().patch_theme(theme_id, patch)
    return _ok(t.model_dump())


@mcp.tool()
@_tool
def typeform_delete_theme(theme_id: str) -> str:
    """
    Elimina un tema.

    Args:
        theme_id: ID del tema da eliminare.
    """
    _client().delete_theme(theme_id)
    return _ok({"deleted": True, "theme_id": theme_id})


# ===========================================================================
# IMAGES
# ===========================================================================


@mcp.tool()
@_tool
def typeform_list_images() -> str:
    """Elenca tutte le immagini caricate nell'account."""
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
    Restituisce i metadati di un'immagine specifica.

    Args:
        image_id: ID dell'immagine.
    """
    img = _client().get_image(image_id)
    return _ok(img.model_dump())


@mcp.tool()
@_tool
def typeform_create_image(file_name: str, image_base64: str, media_type: str) -> str:
    """
    Carica una nuova immagine nell'account (codificata in base64).

    Args:
        file_name:    Nome del file (es. "logo.png").
        image_base64: Contenuto dell'immagine in formato base64.
        media_type:   MIME type: "image/jpeg", "image/png", "image/gif", ecc.
    """
    payload = ImageCreate(file_name=file_name, image=image_base64, media_type=media_type)
    img = _client().create_image(payload)
    return _ok(img.model_dump())


@mcp.tool()
@_tool
def typeform_delete_image(image_id: str) -> str:
    """
    Elimina un'immagine dall'account.

    Args:
        image_id: ID dell'immagine da eliminare.
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
    Elenca i workspace dell'account.

    Args:
        page:      Numero di pagina.
        page_size: Risultati per pagina.
        search:    Testo per filtrare per nome workspace.
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
    Restituisce i dettagli di un workspace specifico.

    Args:
        workspace_id: ID del workspace.
    """
    w = _client().get_workspace(workspace_id)
    return _ok(w.model_dump())


@mcp.tool()
@_tool
def typeform_create_workspace(name: str) -> str:
    """
    Crea un nuovo workspace.

    Args:
        name: Nome del workspace.
    """
    w = _client().create_workspace(name)
    return _ok(w.model_dump())


@mcp.tool()
@_tool
def typeform_update_workspace(workspace_id: str, name: str) -> str:
    """
    Rinomina un workspace.

    Args:
        workspace_id: ID del workspace.
        name:         Nuovo nome del workspace.
    """
    w = _client().update_workspace(workspace_id, name)
    return _ok(w.model_dump())


@mcp.tool()
@_tool
def typeform_delete_workspace(workspace_id: str) -> str:
    """
    Elimina un workspace (deve essere vuoto).

    Args:
        workspace_id: ID del workspace da eliminare.
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
    Restituisce lo stato delle traduzioni disponibili per un form.

    Args:
        form_id: ID del form.
    """
    statuses = _client().get_translation_statuses(form_id)
    return _ok([s.model_dump() for s in statuses])


@mcp.tool()
@_tool
def typeform_list_translations(form_id: str) -> str:
    """
    Restituisce il payload completo di tutte le traduzioni di un form.

    Args:
        form_id: ID del form.
    """
    return _ok(_client().list_translations(form_id))


@mcp.tool()
@_tool
def typeform_update_translation(form_id: str, language: str, payload: dict) -> str:
    """
    Aggiorna (o crea) la traduzione di un form in una lingua specifica.

    Args:
        form_id:  ID del form.
        language: Codice lingua ISO 639-1 (es. "en", "fr", "de").
        payload:  Oggetto con le stringhe tradotte (stesso schema restituito da typeform_list_translations).
    """
    return _ok(_client().update_translation(form_id, language, payload))


@mcp.tool()
@_tool
def typeform_delete_translation(form_id: str, language: str) -> str:
    """
    Elimina la traduzione di un form in una lingua specifica.

    Args:
        form_id:  ID del form.
        language: Codice lingua ISO 639-1 (es. "en", "fr").
    """
    _client().delete_translation(form_id, language)
    return _ok({"deleted": True, "form_id": form_id, "language": language})


@mcp.tool()
@_tool
def typeform_auto_translate(form_id: str, target_languages: list[str]) -> str:
    """
    Avvia la traduzione automatica di un form nelle lingue indicate.

    Args:
        form_id:          ID del form.
        target_languages: Lista di codici lingua ISO 639-1 (es. ["en", "fr", "de"]).
    """
    return _ok(_client().auto_translate(form_id, target_languages))


# ===========================================================================
# Entrypoint
# ===========================================================================


def main() -> None:
    token = os.environ.get("TYPEFORM_TOKEN")
    if not token:
        print(
            "Errore: variabile TYPEFORM_TOKEN non impostata.\n"
            "Uso: TYPEFORM_TOKEN=tfp_... typeform-mcp",
            file=sys.stderr,
        )
        sys.exit(1)

    logger.info("Avvio Typeform MCP server (stdio)")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
