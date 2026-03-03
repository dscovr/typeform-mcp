"""Tests for src/typeform/models.py"""

import pytest
from pydantic import ValidationError

from src.typeform.models import (
    Choice,
    Condition,
    ConditionVar,
    FieldType,
    Form,
    JumpAction,
    JumpDetails,
    LogicRule,
    LongTextProperties,
    MatrixColumn,
    MatrixProperties,
    MatrixRow,
    MultipleChoiceProperties,
    OpinionScaleProperties,
    ScreenProperties,
    ShortTextProperties,
    StatementProperties,
    SurveyField,
    ThankyouScreen,
    ThankyouScreenProperties,
    Validations,
    WelcomeScreen,
)


# ---------------------------------------------------------------------------
# FieldType enum
# ---------------------------------------------------------------------------


def test_field_type_values():
    assert FieldType.multiple_choice == "multiple_choice"
    assert FieldType.opinion_scale == "opinion_scale"
    assert FieldType.matrix == "matrix"
    assert FieldType.long_text == "long_text"
    assert FieldType.short_text == "short_text"
    assert FieldType.statement == "statement"


# ---------------------------------------------------------------------------
# Choice / MatrixRow / MatrixColumn
# ---------------------------------------------------------------------------


def test_choice():
    c = Choice(ref="c1", label="Option A")
    assert c.ref == "c1"
    assert c.label == "Option A"


def test_matrix_row_column():
    r = MatrixRow(ref="r1", label="Row 1")
    c = MatrixColumn(ref="c1", label="Col 1")
    assert r.ref == "r1"
    assert c.label == "Col 1"


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


def test_multiple_choice_properties_defaults():
    props = MultipleChoiceProperties(choices=[Choice(ref="a", label="A")])
    # allow_other_choice is None by default (not sent to the API unless explicitly set)
    assert props.allow_other_choice is None


def test_multiple_choice_properties_custom():
    props = MultipleChoiceProperties(
        choices=[Choice(ref="a", label="A"), Choice(ref="b", label="B")],
        allow_other_choice=True,
    )
    assert props.allow_other_choice is True
    assert len(props.choices) == 2


def test_opinion_scale_properties():
    props = OpinionScaleProperties(steps=7, labels={"left": "Bad", "right": "Good"})
    assert props.steps == 7
    assert props.start_at_one is True
    assert props.labels == {"left": "Bad", "right": "Good"}


def test_opinion_scale_no_labels():
    props = OpinionScaleProperties(steps=5)
    assert props.labels is None


def test_matrix_properties():
    props = MatrixProperties(
        rows=[MatrixRow(ref="r1", label="R1"), MatrixRow(ref="r2", label="R2")],
        columns=[MatrixColumn(ref="c1", label="C1")],
    )
    assert len(props.rows) == 2
    assert len(props.columns) == 1


def test_statement_properties_defaults():
    props = StatementProperties()
    assert props.button_text == "Continue"
    assert props.hide_marks is True


def test_long_text_short_text_properties():
    LongTextProperties()
    ShortTextProperties()


# ---------------------------------------------------------------------------
# Validations
# ---------------------------------------------------------------------------


def test_validations_defaults():
    v = Validations()
    assert v.required is True
    assert v.min_length is None
    assert v.max_length is None


def test_validations_custom():
    v = Validations(required=False, max_selection=3, min_selection=1)
    assert v.required is False
    assert v.max_selection == 3
    assert v.min_selection == 1


# ---------------------------------------------------------------------------
# SurveyField
# ---------------------------------------------------------------------------


def test_survey_field_enum_stored_as_string():
    """use_enum_values=True: the stored value must be the string, not the enum member."""
    field = SurveyField(ref="q1", title="Title", type=FieldType.multiple_choice)
    assert field.type == "multiple_choice"


def test_survey_field_to_api_excludes_none():
    field = SurveyField(ref="q1", title="Title", type=FieldType.short_text)
    payload = field.to_api()
    assert "properties" not in payload
    assert "validations" not in payload
    assert payload["ref"] == "q1"
    assert payload["title"] == "Title"
    assert payload["type"] == "short_text"


def test_survey_field_to_api_with_properties():
    field = SurveyField(
        ref="q1",
        title="Title",
        type=FieldType.multiple_choice,
        properties=MultipleChoiceProperties(choices=[Choice(ref="a", label="A")]),
        validations=Validations(required=True),
    )
    payload = field.to_api()
    assert "properties" in payload
    assert "validations" in payload
    assert payload["properties"]["choices"][0]["ref"] == "a"


def test_survey_field_opinion_scale_serialization():
    field = SurveyField(
        ref="q2",
        title="Scale",
        type=FieldType.opinion_scale,
        properties=OpinionScaleProperties(steps=5),
    )
    payload = field.to_api()
    # labels is None → excluded
    assert "labels" not in payload["properties"]
    assert payload["properties"]["steps"] == 5


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------


def test_screen_properties_defaults():
    sp = ScreenProperties()
    assert sp.show_button is True
    assert sp.button_text == "Next"


def test_welcome_screen():
    ws = WelcomeScreen(ref="welcome", title="Welcome!")
    assert ws.ref == "welcome"
    assert ws.properties.show_button is True


def test_thankyou_screen_default_properties():
    ts = ThankyouScreen(ref="end", title="Thank you!")
    # ThankyouScreenProperties has all None by default (no value sent to the API)
    assert ts.properties.show_button is None
    assert ts.properties.redirect_url is None
    assert ts.type is None


def test_thankyou_screen_custom_button():
    ts = ThankyouScreen(ref="end", title="Thank you!", properties=ThankyouScreenProperties(show_button=True))
    assert ts.properties.show_button is True


def test_thankyou_screen_redirect():
    ts = ThankyouScreen(
        ref="end",
        title="Thank you!",
        type="url_redirect",
        properties=ThankyouScreenProperties(redirect_url="https://example.com/cb"),
    )
    assert ts.type == "url_redirect"
    assert ts.properties.redirect_url == "https://example.com/cb"


# ---------------------------------------------------------------------------
# Logic
# ---------------------------------------------------------------------------


def test_condition_var():
    cv = ConditionVar(type="field", value="q1")
    assert cv.type == "field"
    assert cv.value == "q1"


def test_condition_var_int_value():
    cv = ConditionVar(type="constant", value=3)
    assert cv.value == 3


def test_condition_var_variable_and_hidden():
    cv_var = ConditionVar(type="variable", value="score")
    cv_hid = ConditionVar(type="hidden", value="sid")
    assert cv_var.type == "variable"
    assert cv_hid.type == "hidden"


def test_condition_var_invalid_type():
    with pytest.raises(ValidationError):
        ConditionVar(type="invalid_type", value="x")


def test_jump_action_default_action_literal():
    ja = JumpAction(
        details=JumpDetails(to={"type": "field", "value": "q2"}),
        condition=Condition(
            op="is",
            vars=[ConditionVar(type="field", value="q1"), ConditionVar(type="choice", value="a")],
        ),
    )
    assert ja.action == "jump"


def test_logic_rule():
    rule = LogicRule(
        ref="q1",
        actions=[
            JumpAction(
                details=JumpDetails(to={"type": "thankyou", "value": "end"}),
                condition=Condition(op="always", vars=[]),
            )
        ],
    )
    assert rule.type == "field"
    assert rule.ref == "q1"
    assert len(rule.actions) == 1


# ---------------------------------------------------------------------------
# Form
# ---------------------------------------------------------------------------


def test_form_defaults():
    form = Form(title="My Form")
    # language=None by default: not sent to the API (not accepted by POST /forms)
    assert form.language is None
    assert form.hidden == []
    assert form.variables is None
    assert form.fields == []
    assert form.welcome_screens == []
    assert form.thankyou_screens == []
    assert form.logic == []


def test_form_hidden_fields_and_variables():
    form = Form(title="F", hidden=["sid", "source"], variables={"score": 0, "price": 0.0})
    payload = form.to_api()
    assert payload["hidden"] == ["sid", "source"]
    assert payload["variables"] == {"score": 0, "price": 0.0}


def test_form_hidden_excluded_when_empty():
    form = Form(title="F")
    payload = form.to_api()
    # empty list → exclude_none does not remove empty lists, but hidden=[] is serialized
    # verify that variables (None) is excluded
    assert "variables" not in payload


def test_form_to_api_excludes_language_when_none():
    """language=None is excluded from to_api() thanks to exclude_none=True."""
    form = Form(title="Empty")
    payload = form.to_api()
    assert payload["title"] == "Empty"
    assert "language" not in payload


def test_form_to_api_full():
    form = Form(
        title="Full Form",
        welcome_screens=[WelcomeScreen(ref="w", title="Welcome")],
        thankyou_screens=[ThankyouScreen(ref="t", title="Thanks")],
        fields=[
            SurveyField(
                ref="q1",
                title="Role?",
                type=FieldType.multiple_choice,
                properties=MultipleChoiceProperties(
                    choices=[Choice(ref="q1_a", label="A"), Choice(ref="q1_b", label="B")]
                ),
            ),
            SurveyField(
                ref="q2",
                title="Scale?",
                type=FieldType.opinion_scale,
                properties=OpinionScaleProperties(steps=5),
            ),
        ],
        logic=[
            LogicRule(
                ref="q1",
                actions=[
                    JumpAction(
                        details=JumpDetails(to={"type": "field", "value": "q2"}),
                        condition=Condition(
                            op="is",
                            vars=[
                                ConditionVar(type="field", value="q1"),
                                ConditionVar(type="choice", value="q1_b"),
                            ],
                        ),
                    )
                ],
            )
        ],
    )
    payload = form.to_api()

    assert payload["title"] == "Full Form"
    assert len(payload["fields"]) == 2
    assert len(payload["welcome_screens"]) == 1
    assert len(payload["thankyou_screens"]) == 1
    assert len(payload["logic"]) == 1

    # logic serialization
    action = payload["logic"][0]["actions"][0]
    assert action["action"] == "jump"
    assert action["details"]["to"] == {"type": "field", "value": "q2"}

    # opinion scale: labels absent (None → excluded)
    scale_payload = payload["fields"][1]
    assert "labels" not in scale_payload.get("properties", {})


def test_form_to_api_returns_json_serializable():
    """to_api() must return a plain dict with no Pydantic/enum objects."""
    import json

    form = Form(
        title="Serializable",
        fields=[
            SurveyField(ref="q1", title="T", type=FieldType.matrix,
                        properties=MatrixProperties(
                            rows=[MatrixRow(ref="r1", label="R1")],
                            columns=[MatrixColumn(ref="c1", label="C1")],
                        ))
        ],
    )
    payload = form.to_api()
    # This must not raise
    json.dumps(payload)
