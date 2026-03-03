"""
Typeform API — client HTTP full-featured.

Copre tutti gli endpoint pubblici:
  - Account       GET /me
  - Forms         CRUD + messages + patch
  - Themes        CRUD + patch
  - Images        CRUD + download
  - Workspaces    CRUD + patch
  - Responses     list, delete, file download, audio/video master
  - Webhooks      list, get, upsert, delete
  - Translations  list, statuses, update, delete, auto-translate
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

from .models import (
    Account,
    Form,
    FormList,
    FormResponse,
    Image,
    ImageCreate,
    ImageList,
    ResponseList,
    Theme,
    ThemeCreate,
    ThemeList,
    TranslationStatus,
    Webhook,
    WebhookList,
    WebhookUpsert,
    Workspace,
    WorkspaceList,
)

TYPEFORM_API_URL = "https://api.typeform.com"


# ---------------------------------------------------------------------------
# Eccezione dedicata
# ---------------------------------------------------------------------------


class TypeformAPIError(Exception):
    """Eccezione sollevata per risposte HTTP non 2xx dall'API Typeform."""

    def __init__(
        self,
        status_code: int,
        code: str,
        description: str,
        details: list[dict] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.description = description
        self.details = details or []
        super().__init__(f"[{status_code}] {code}: {description}")


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class TypeformClient:
    """
    Client completo per le API Typeform.

    Uso:
        client = TypeformClient(token="tfp_...")
        # oppure con variabile d'ambiente TYPEFORM_TOKEN
        client = TypeformClient()
    """

    def __init__(self, token: str | None = None, timeout: int = 30) -> None:
        self.token = token or os.environ["TYPEFORM_TOKEN"]
        self.timeout = timeout
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # Metodi interni
    # ------------------------------------------------------------------

    def _headers(self, content_type: str | None = "application/json") -> dict:
        h: dict[str, str] = {"Authorization": f"Bearer {self.token}"}
        if content_type:
            h["Content-Type"] = content_type
        return h

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: Any = None,
        data: bytes | None = None,
        content_type: str | None = "application/json",
        _retries: int = 3,
    ) -> requests.Response:
        """Esegue la richiesta HTTP con retry su 429/503 e solleva TypeformAPIError in caso di errore."""
        url = f"{TYPEFORM_API_URL}{path}"
        for attempt in range(_retries + 1):
            resp = self._session.request(
                method,
                url,
                headers=self._headers(content_type),
                params=_clean_params(params),
                json=json,
                data=data,
                timeout=self.timeout,
            )
            if resp.status_code in (429, 503) and attempt < _retries:
                wait = min(2 ** attempt, 30)
                retry_after = resp.headers.get("Retry-After", "")
                if retry_after.isdigit():
                    wait = int(retry_after)
                logger.warning(
                    "%s %s → %d, retry %d/%d in %ds",
                    method, path, resp.status_code, attempt + 1, _retries, wait,
                )
                time.sleep(wait)
                continue
            if not resp.ok:
                try:
                    body = resp.json()
                except Exception:
                    body = {}
                raise TypeformAPIError(
                    status_code=resp.status_code,
                    code=body.get("code", "UNKNOWN"),
                    description=body.get("description", resp.text),
                    details=body.get("details"),
                )
            return resp
        # Irraggiungibile: l'ultimo tentativo o ritorna o solleva
        raise TypeformAPIError(status_code=0, code="MAX_RETRIES", description="Max retries exceeded")

    # ==================================================================
    # ACCOUNT
    # ==================================================================

    def get_me(self) -> Account:
        """GET /me — informazioni sull'account corrente."""
        resp = self._request("GET", "/me")
        return Account.model_validate(resp.json())

    # ==================================================================
    # FORMS
    # ==================================================================

    def list_forms(
        self,
        *,
        page: int = 1,
        page_size: int = 10,
        search: str | None = None,
        workspace_id: str | None = None,
    ) -> FormList:
        """GET /forms — lista dei form con paginazione e ricerca opzionale."""
        resp = self._request(
            "GET",
            "/forms",
            params={
                "page": page,
                "page_size": page_size,
                "search": search,
                "workspace_id": workspace_id,
            },
        )
        return FormList.model_validate(resp.json())

    def create_form(self, form: Form) -> dict:
        """POST /forms — crea un nuovo form da oggetto Form (validato da Pydantic)."""
        resp = self._request("POST", "/forms", json=form.to_api())
        return resp.json()

    def create_form_raw(self, form_definition: dict) -> dict:
        """POST /forms — crea un nuovo form da payload grezzo (dict)."""
        resp = self._request("POST", "/forms", json=form_definition)
        return resp.json()

    def get_form(self, form_id: str) -> dict:
        """GET /forms/{form_id} — recupera la definizione completa di un form."""
        resp = self._request("GET", f"/forms/{form_id}")
        return resp.json()

    def update_form(self, form_id: str, form: Form) -> dict:
        """PUT /forms/{form_id} — sostituisce il form da oggetto Form (validato da Pydantic)."""
        resp = self._request("PUT", f"/forms/{form_id}", json=form.to_api())
        return resp.json()

    def update_form_raw(self, form_id: str, form_definition: dict) -> dict:
        """PUT /forms/{form_id} — sostituisce il form da payload grezzo (dict)."""
        resp = self._request("PUT", f"/forms/{form_id}", json=form_definition)
        return resp.json()

    def patch_form(self, form_id: str, patch: dict) -> dict:
        """PATCH /forms/{form_id} — aggiorna parzialmente un form."""
        resp = self._request("PATCH", f"/forms/{form_id}", json=patch)
        return resp.json()

    def delete_form(self, form_id: str) -> None:
        """DELETE /forms/{form_id} — elimina un form."""
        self._request("DELETE", f"/forms/{form_id}")

    def duplicate_form(self, form_id: str) -> dict:
        """POST /forms/{form_id}/duplicate — duplica un form esistente."""
        resp = self._request("POST", f"/forms/{form_id}/duplicate")
        return resp.json()

    def get_form_messages(self, form_id: str) -> dict[str, str]:
        """GET /forms/{form_id}/messages — messaggi personalizzati del form."""
        resp = self._request("GET", f"/forms/{form_id}/messages")
        return resp.json()

    def update_form_messages(
        self, form_id: str, messages: dict[str, str]
    ) -> dict[str, str]:
        """PUT /forms/{form_id}/messages — aggiorna i messaggi personalizzati."""
        resp = self._request(
            "PUT", f"/forms/{form_id}/messages", json=messages
        )
        return resp.json()

    # ==================================================================
    # THEMES
    # ==================================================================

    def list_themes(
        self, *, page: int = 1, page_size: int = 10
    ) -> ThemeList:
        """GET /themes — lista dei temi."""
        resp = self._request(
            "GET", "/themes", params={"page": page, "page_size": page_size}
        )
        return ThemeList.model_validate(resp.json())

    def create_theme(self, theme: ThemeCreate) -> Theme:
        """POST /themes — crea un nuovo tema."""
        resp = self._request("POST", "/themes", json=theme.to_api())
        return Theme.model_validate(resp.json())

    def get_theme(self, theme_id: str) -> Theme:
        """GET /themes/{theme_id} — recupera un tema."""
        resp = self._request("GET", f"/themes/{theme_id}")
        return Theme.model_validate(resp.json())

    def update_theme(self, theme_id: str, theme: ThemeCreate) -> Theme:
        """PUT /themes/{theme_id} — sostituisce un tema."""
        resp = self._request("PUT", f"/themes/{theme_id}", json=theme.to_api())
        return Theme.model_validate(resp.json())

    def patch_theme(self, theme_id: str, patch: dict) -> Theme:
        """PATCH /themes/{theme_id} — aggiorna parzialmente un tema."""
        resp = self._request("PATCH", f"/themes/{theme_id}", json=patch)
        return Theme.model_validate(resp.json())

    def delete_theme(self, theme_id: str) -> None:
        """DELETE /themes/{theme_id} — elimina un tema."""
        self._request("DELETE", f"/themes/{theme_id}")

    # ==================================================================
    # IMAGES
    # ==================================================================

    def list_images(self) -> ImageList:
        """GET /images — lista delle immagini caricate."""
        resp = self._request("GET", "/images")
        return ImageList.model_validate(resp.json())

    def create_image(self, image: ImageCreate) -> Image:
        """POST /images — carica una nuova immagine (base64)."""
        resp = self._request("POST", "/images", json=image.to_api())
        return Image.model_validate(resp.json())

    def get_image(self, image_id: str) -> Image:
        """GET /images/{image_id} — recupera metadati di un'immagine."""
        resp = self._request("GET", f"/images/{image_id}")
        return Image.model_validate(resp.json())

    def delete_image(self, image_id: str) -> None:
        """DELETE /images/{image_id} — elimina un'immagine."""
        self._request("DELETE", f"/images/{image_id}")

    def download_image(self, image_id: str, size: str = "default") -> bytes:
        """GET /images/{image_id}/download — scarica il file immagine."""
        resp = self._request(
            "GET",
            f"/images/{image_id}/download",
            params={"size": size},
            content_type=None,
        )
        return resp.content

    # ==================================================================
    # WORKSPACES
    # ==================================================================

    def list_workspaces(
        self,
        *,
        page: int = 1,
        page_size: int = 10,
        search: str | None = None,
    ) -> WorkspaceList:
        """GET /workspaces — lista dei workspace."""
        resp = self._request(
            "GET",
            "/workspaces",
            params={"page": page, "page_size": page_size, "search": search},
        )
        return WorkspaceList.model_validate(resp.json())

    def create_workspace(self, name: str) -> Workspace:
        """POST /workspaces — crea un workspace."""
        resp = self._request("POST", "/workspaces", json={"name": name})
        return Workspace.model_validate(resp.json())

    def get_workspace(self, workspace_id: str) -> Workspace:
        """GET /workspaces/{workspace_id} — recupera un workspace."""
        resp = self._request("GET", f"/workspaces/{workspace_id}")
        return Workspace.model_validate(resp.json())

    def update_workspace(self, workspace_id: str, name: str) -> Workspace:
        """PATCH /workspaces/{workspace_id} — aggiorna il nome del workspace."""
        resp = self._request(
            "PATCH", f"/workspaces/{workspace_id}", json={"name": name}
        )
        return Workspace.model_validate(resp.json())

    def delete_workspace(self, workspace_id: str) -> None:
        """DELETE /workspaces/{workspace_id} — elimina un workspace."""
        self._request("DELETE", f"/workspaces/{workspace_id}")

    # ==================================================================
    # RESPONSES
    # ==================================================================

    def list_responses(
        self,
        form_id: str,
        *,
        page_size: int = 25,
        after: str | None = None,
        before: str | None = None,
        since: str | None = None,
        until: str | None = None,
        query: str | None = None,
        fields: list[str] | None = None,
        sort: str = "submitted_at,desc",
        response_type: str | None = None,
    ) -> ResponseList:
        """
        GET /forms/{form_id}/responses — recupera le risposte con filtri.

        Args:
            page_size:      max 1000.
            after:          token per cursore (paginazione forward).
            before:         token per cursore (paginazione backward).
            since:          ISO 8601 — risposte dopo questa data.
            until:          ISO 8601 — risposte prima di questa data.
            query:          testo libero per filtrare le risposte.
            fields:         lista di ref dei campi da includere.
            sort:           es. "submitted_at,desc".
            response_type:  "completed" | "landed".
        """
        resp = self._request(
            "GET",
            f"/forms/{form_id}/responses",
            params={
                "page_size": page_size,
                "after": after,
                "before": before,
                "since": since,
                "until": until,
                "query": query,
                "fields": ",".join(fields) if fields else None,
                "sort": sort,
                "response_type": response_type,
            },
        )
        return ResponseList.model_validate(resp.json())

    def delete_responses(
        self, form_id: str, included_tokens: list[str]
    ) -> None:
        """
        DELETE /forms/{form_id}/responses — elimina risposte per token.

        Args:
            included_tokens: lista dei token (response_id) da eliminare.
        """
        self._request(
            "DELETE",
            f"/forms/{form_id}/responses",
            params={"included_tokens": ",".join(included_tokens)},
        )

    def download_response_files(
        self,
        form_id: str,
        response_id: str,
        field_id: str,
        filename: str,
        max_bytes: int = 10 * 1024 * 1024,
    ) -> bytes:
        """
        GET /forms/{form_id}/responses/{response_id}/fields/{field_id}/files/{filename}
        — scarica un file allegato a una risposta.

        Args:
            max_bytes: Limite massimo in byte (default 10 MB). Solleva ValueError se superato.
        """
        resp = self._request(
            "GET",
            f"/forms/{form_id}/responses/{response_id}/fields/{field_id}/files/{filename}",
            content_type=None,
        )
        if len(resp.content) > max_bytes:
            raise ValueError(
                f"File troppo grande: {len(resp.content)} byte (limite {max_bytes} byte)"
            )
        return resp.content

    def request_audio_master(self, form_id: str) -> dict:
        """POST /forms/{form_id}/responses/audio/master — richiede generazione master audio."""
        resp = self._request(
            "POST", f"/forms/{form_id}/responses/audio/master"
        )
        return resp.json()

    def get_audio_master(self, form_id: str, master_id: str) -> bytes:
        """GET /forms/{form_id}/responses/audio/master/{master_id} — scarica master audio."""
        resp = self._request(
            "GET",
            f"/forms/{form_id}/responses/audio/master/{master_id}",
            content_type=None,
        )
        return resp.content

    def request_video_master(self, form_id: str) -> dict:
        """POST /forms/{form_id}/responses/video/master — richiede generazione master video."""
        resp = self._request(
            "POST", f"/forms/{form_id}/responses/video/master"
        )
        return resp.json()

    def get_video_master(self, form_id: str, master_id: str) -> bytes:
        """GET /forms/{form_id}/responses/video/master/{master_id} — scarica master video."""
        resp = self._request(
            "GET",
            f"/forms/{form_id}/responses/video/master/{master_id}",
            content_type=None,
        )
        return resp.content

    # ==================================================================
    # WEBHOOKS
    # ==================================================================

    def list_webhooks(self, form_id: str) -> WebhookList:
        """GET /forms/{form_id}/webhooks — lista webhook del form."""
        resp = self._request("GET", f"/forms/{form_id}/webhooks")
        return WebhookList.model_validate(resp.json())

    def get_webhook(self, form_id: str, tag: str) -> Webhook:
        """GET /forms/{form_id}/webhooks/{tag} — recupera un webhook."""
        resp = self._request("GET", f"/forms/{form_id}/webhooks/{tag}")
        return Webhook.model_validate(resp.json())

    def upsert_webhook(
        self, form_id: str, tag: str, webhook: WebhookUpsert
    ) -> Webhook:
        """
        PUT /forms/{form_id}/webhooks/{tag} — crea o aggiorna un webhook.
        Il tag identifica univocamente il webhook nel form.
        """
        resp = self._request(
            "PUT",
            f"/forms/{form_id}/webhooks/{tag}",
            json=webhook.to_api(),
        )
        return Webhook.model_validate(resp.json())

    def delete_webhook(self, form_id: str, tag: str) -> None:
        """DELETE /forms/{form_id}/webhooks/{tag} — elimina un webhook."""
        self._request("DELETE", f"/forms/{form_id}/webhooks/{tag}")

    # ==================================================================
    # TRANSLATIONS
    # ==================================================================

    def list_translations(self, form_id: str) -> list[dict]:
        """GET /forms/{form_id}/translations — payload di tutte le traduzioni."""
        resp = self._request("GET", f"/forms/{form_id}/translations")
        return resp.json()

    def get_translation_statuses(
        self, form_id: str
    ) -> list[TranslationStatus]:
        """GET /forms/{form_id}/translations/statuses — stato di ogni traduzione."""
        resp = self._request(
            "GET", f"/forms/{form_id}/translations/statuses"
        )
        return [TranslationStatus.model_validate(s) for s in resp.json()]

    def update_translation(
        self, form_id: str, language: str, payload: dict
    ) -> dict:
        """PUT /forms/{form_id}/translations/{language} — aggiorna una traduzione."""
        resp = self._request(
            "PUT",
            f"/forms/{form_id}/translations/{language}",
            json=payload,
        )
        return resp.json()

    def delete_translation(self, form_id: str, language: str) -> None:
        """DELETE /forms/{form_id}/translations/{language} — elimina una traduzione."""
        self._request("DELETE", f"/forms/{form_id}/translations/{language}")

    def auto_translate(
        self, form_id: str, target_languages: list[str]
    ) -> dict:
        """POST /forms/{form_id}/translations/auto — traduzione automatica."""
        resp = self._request(
            "POST",
            f"/forms/{form_id}/translations/auto",
            json={"target_languages": target_languages},
        )
        return resp.json()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean_params(params: dict | None) -> dict | None:
    """Rimuove le chiavi con valore None da un dict di query params."""
    if params is None:
        return None
    return {k: v for k, v in params.items() if v is not None}
