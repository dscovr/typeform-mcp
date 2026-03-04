"""
Typeform API — Pydantic models.

Organized into:
  - Form building models (Form, SurveyField, logic, ...)
  - API response models for all resources (Account, Theme, Image,
    Workspace, Response, Webhook, Translation, ...)
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Shared config for API response models
# (extra="allow" prevents errors on unmapped fields)
# ---------------------------------------------------------------------------

_api = ConfigDict(extra="allow")


# ===========================================================================
# ENUMERATIONS
# ===========================================================================


class FieldType(str, Enum):
    multiple_choice = "multiple_choice"
    opinion_scale   = "opinion_scale"
    matrix          = "matrix"
    long_text        = "long_text"
    short_text       = "short_text"
    statement        = "statement"
    number           = "number"
    rating           = "rating"
    date             = "date"
    yes_no           = "yes_no"
    dropdown         = "dropdown"
    ranking          = "ranking"
    file_upload      = "file_upload"
    picture_choice   = "picture_choice"
    payment          = "payment"
    website          = "website"
    email            = "email"
    phone_number     = "phone_number"
    legal            = "legal"
    group            = "group"


# ===========================================================================
# FORM — building primitives
# ===========================================================================


class Choice(BaseModel):
    ref: str
    label: str


class MatrixRow(BaseModel):
    ref: str
    label: str


class MatrixColumn(BaseModel):
    ref: str
    label: str


# --- Properties by field type ---

class MultipleChoiceProperties(BaseModel):
    choices: list[Choice]
    allow_multiple_selection: bool | None = None   # singular — API rejects "allow_multiple_selections"
    allow_other_choice: bool | None = None


class OpinionScaleProperties(BaseModel):
    steps: int
    start_at_one: bool = True
    labels: dict[str, str] | None = None  # {"left": "...", "right": "..."}


class MatrixProperties(BaseModel):
    rows: list[MatrixRow]
    columns: list[MatrixColumn]


class LongTextProperties(BaseModel):
    pass


class ShortTextProperties(BaseModel):
    pass


class StatementProperties(BaseModel):
    button_text: str = "Continue"
    hide_marks: bool = True


class DropdownProperties(BaseModel):
    choices: list[Choice]
    alphabetical_order: bool | None = None
    randomize: bool | None = None


class RatingProperties(BaseModel):
    shape: str | None = None   # "star", "heart", "circle", ...
    steps: int | None = None   # 3–10


class PictureChoiceProperties(BaseModel):
    choices: list[dict]        # {ref, label, attachment}
    allow_multiple_selection: bool | None = None   # singular
    allow_other_choice: bool | None = None


Properties = Union[
    MultipleChoiceProperties,
    OpinionScaleProperties,
    MatrixProperties,
    LongTextProperties,
    ShortTextProperties,
    StatementProperties,
    DropdownProperties,
    RatingProperties,
    PictureChoiceProperties,
]


class Validations(BaseModel):
    required: bool = True
    min_length: int | None = None
    max_length: int | None = None
    max_selection: int | None = None
    min_selection: int | None = None


class SurveyField(BaseModel):
    ref: str
    title: str
    type: FieldType
    properties: Properties | None = None
    validations: Validations | None = None

    model_config = ConfigDict(use_enum_values=True)

    def to_api(self) -> dict:
        return self.model_dump(exclude_none=True, mode="json")


# --- Screens ---

class ScreenProperties(BaseModel):
    show_button: bool = True
    button_text: str = "Next"


class WelcomeScreen(BaseModel):
    ref: str
    title: str
    properties: ScreenProperties = Field(default_factory=ScreenProperties)


class ThankyouScreenProperties(BaseModel):
    show_button: bool | None = None
    button_text: str | None = None
    redirect_url: str | None = None   # used with type="url_redirect"


class ThankyouScreen(BaseModel):
    ref: str
    title: str
    type: str | None = None   # None = default | "url_redirect"
    properties: ThankyouScreenProperties = Field(default_factory=ThankyouScreenProperties)


# --- Logic Jump ---

class ConditionVar(BaseModel):
    type: Literal["field", "choice", "constant", "variable", "hidden"]
    value: str | int


class Condition(BaseModel):
    op: str   # "is", "lower_equal_than", "always", ...
    vars: list[ConditionVar]


class JumpDetails(BaseModel):
    to: dict  # {"type": "field"/"thankyou", "value": ref}


class JumpAction(BaseModel):
    action: Literal["jump"] = "jump"
    details: JumpDetails
    condition: Condition


class LogicRule(BaseModel):
    type: Literal["field"] = "field"
    ref: str
    actions: list[JumpAction]


# --- Form top-level ---

class Form(BaseModel):
    title: str
    language: str | None = None        # not accepted by the Create POST API
    hidden: list[str] = Field(default_factory=list)   # hidden field names, e.g. ["sid", "source"]
    variables: dict[str, Any] | None = None            # variables/score, e.g. {"score": 0, "price": 0}
    welcome_screens: list[WelcomeScreen] = Field(default_factory=list)
    thankyou_screens: list[ThankyouScreen] = Field(default_factory=list)
    fields: list[SurveyField] = Field(default_factory=list)
    logic: list[LogicRule] = Field(default_factory=list)

    def to_api(self) -> dict:
        return self.model_dump(exclude_none=True, mode="json")


# ===========================================================================
# ACCOUNT
# ===========================================================================


class Account(BaseModel):
    model_config = _api

    alias: str
    email: str
    language: str | None = None


# ===========================================================================
# FORMS — response models
# ===========================================================================


class FormSummary(BaseModel):
    """Single item returned by GET /forms (list)."""
    model_config = _api

    id: str
    title: str
    last_updated_at: str | None = None
    created_at: str | None = None


class FormList(BaseModel):
    model_config = _api

    total_items: int
    page_count: int
    items: list[FormSummary]


# ===========================================================================
# THEMES
# ===========================================================================


class ThemeColors(BaseModel):
    model_config = _api

    question: str | None = None
    answer: str | None = None
    button: str | None = None
    background: str | None = None


class ThemeBackground(BaseModel):
    model_config = _api

    href: str | None = None
    brightness: float | None = None
    layout: str | None = None   # "fullscreen" | "repeat" | "no-repeat"


class Theme(BaseModel):
    model_config = _api

    id: str | None = None
    name: str
    font: str | None = None
    colors: ThemeColors | None = None
    background: ThemeBackground | None = None
    has_transparent_button: bool | None = None
    visibility: str | None = None   # "public" | "private"


class ThemeCreate(BaseModel):
    """Payload for creating or updating a theme."""
    name: str
    font: str | None = None
    colors: ThemeColors | None = None
    background: ThemeBackground | None = None
    has_transparent_button: bool | None = None
    visibility: str | None = None

    def to_api(self) -> dict:
        return self.model_dump(exclude_none=True, mode="json")


class ThemeList(BaseModel):
    model_config = _api

    total_items: int
    page_count: int
    items: list[Theme]


# ===========================================================================
# IMAGES
# ===========================================================================


class Image(BaseModel):
    model_config = _api

    id: str | None = None
    src: str | None = None
    file_name: str | None = None
    width: int | None = None
    height: int | None = None
    media_type: str | None = None
    has_alpha: bool | None = None
    avg_color: str | None = None


class ImageCreate(BaseModel):
    """Payload for uploading a new image (base64-encoded)."""
    file_name: str
    image: str       # base64-encoded
    media_type: str  # "image/jpeg" | "image/png" | "image/gif" | ...

    def to_api(self) -> dict:
        return self.model_dump(mode="json")


class ImageList(BaseModel):
    model_config = _api

    total_items: int
    page_count: int
    items: list[Image]


# ===========================================================================
# WORKSPACES
# ===========================================================================


class Workspace(BaseModel):
    model_config = _api

    id: str | None = None
    name: str
    default: bool | None = None
    shared: bool | None = None
    account_id: str | None = None


class WorkspaceList(BaseModel):
    model_config = _api

    total_items: int
    page_count: int
    items: list[Workspace]


# ===========================================================================
# RESPONSES
# ===========================================================================


class ResponseMetadata(BaseModel):
    model_config = _api

    user_agent: str | None = None
    platform: str | None = None
    referer: str | None = None
    network_id: str | None = None
    browser: str | None = None


class AnswerField(BaseModel):
    model_config = _api

    id: str | None = None
    type: str | None = None
    ref: str | None = None


class Answer(BaseModel):
    model_config = _api

    type: str
    field: AnswerField
    choice: dict[str, Any] | None = None
    choices: dict[str, Any] | None = None
    text: str | None = None
    email: str | None = None
    url: str | None = None
    file_url: str | None = None
    boolean: bool | None = None
    number: float | None = None
    date: str | None = None
    payment: dict[str, Any] | None = None
    phone_number: str | None = None

    def value(self) -> Any:
        """Returns the human-readable value regardless of the answer type."""
        if self.type == "choice":
            return self.choice.get("label") if self.choice else None
        if self.type == "choices":
            return self.choices.get("labels") if self.choices else []
        for attr in ("text", "email", "url", "file_url", "phone_number", "date"):
            v = getattr(self, attr)
            if v is not None:
                return v
        if self.boolean is not None:
            return self.boolean
        if self.number is not None:
            return self.number
        if self.payment:
            return self.payment
        return None


class FormResponse(BaseModel):
    model_config = _api

    landing_id: str | None = None
    token: str | None = None
    response_id: str | None = None
    response_type: str | None = None
    landed_at: str | None = None
    submitted_at: str | None = None
    metadata: ResponseMetadata | None = None
    hidden: dict[str, Any] | None = None
    calculated: dict[str, Any] | None = None
    answers: list[Answer] = Field(default_factory=list)

    @field_validator("answers", mode="before")
    @classmethod
    def _coerce_none_answers(cls, v: Any) -> list:
        return v if v is not None else []

    def answers_by_ref(self) -> dict[str, Any]:
        """Returns a ref → value mapping for quick access to answers."""
        return {
            a.field.ref: a.value()
            for a in self.answers
            if a.field.ref
        }


class ResponseList(BaseModel):
    model_config = _api

    total_items: int
    page_count: int
    items: list[FormResponse]


# ===========================================================================
# WEBHOOKS
# ===========================================================================


class Webhook(BaseModel):
    model_config = _api

    id: str | None = None
    form_id: str | None = None
    tag: str | None = None
    url: str
    enabled: bool = True
    secret: str | None = None
    verify_ssl: bool | None = None
    created_at: str | None = None
    updated_at: str | None = None


class WebhookUpsert(BaseModel):
    """Payload for creating or updating a webhook."""
    url: str
    enabled: bool = True
    secret: str | None = None
    verify_ssl: bool | None = None

    def to_api(self) -> dict:
        return self.model_dump(exclude_none=True, mode="json")


class WebhookList(BaseModel):
    model_config = _api

    total_items: int
    page_count: int
    items: list[Webhook]


# ===========================================================================
# TRANSLATIONS
# ===========================================================================


class TranslationStatus(BaseModel):
    model_config = _api

    language: str
    status: str          # "completed" | "in_progress" | ...
    percentage: int | None = None
