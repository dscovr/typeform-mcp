"""Tests for src/typeform/server.py"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.typeform.client import TypeformAPIError
from src.typeform.models import Answer, AnswerField, FormResponse, ResponseList


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _field(ref: str) -> AnswerField:
    return AnswerField(ref=ref, type="text", id="id_" + ref)


def _answer(**kwargs) -> Answer:
    """Build an Answer with a default field ref."""
    kwargs.setdefault("field", _field("q1"))
    return Answer(**kwargs)


# ---------------------------------------------------------------------------
# Answer.value() — all answer types
# ---------------------------------------------------------------------------


def test_answer_value_choice():
    a = _answer(type="choice", choice={"label": "Yes", "ref": "c1"})
    assert a.value() == "Yes"


def test_answer_value_choice_none():
    a = _answer(type="choice", choice=None)
    assert a.value() is None


def test_answer_value_choices():
    a = _answer(type="choices", choices={"labels": ["A", "B"], "refs": ["a", "b"]})
    assert a.value() == ["A", "B"]


def test_answer_value_choices_none():
    a = _answer(type="choices", choices=None)
    assert a.value() == []


def test_answer_value_text():
    a = _answer(type="text", text="hello world")
    assert a.value() == "hello world"


def test_answer_value_email():
    a = _answer(type="email", email="user@example.com")
    assert a.value() == "user@example.com"


def test_answer_value_url():
    a = _answer(type="url", url="https://example.com")
    assert a.value() == "https://example.com"


def test_answer_value_file_url():
    a = _answer(type="file_url", file_url="https://cdn.typeform.com/file.pdf")
    assert a.value() == "https://cdn.typeform.com/file.pdf"


def test_answer_value_phone_number():
    a = _answer(type="phone_number", phone_number="+391234567890")
    assert a.value() == "+391234567890"


def test_answer_value_date():
    a = _answer(type="date", date="2026-01-15")
    assert a.value() == "2026-01-15"


def test_answer_value_boolean_true():
    a = _answer(type="boolean", boolean=True)
    assert a.value() is True


def test_answer_value_boolean_false():
    a = _answer(type="boolean", boolean=False)
    assert a.value() is False


def test_answer_value_number():
    a = _answer(type="number", number=42.5)
    assert a.value() == 42.5


def test_answer_value_number_zero():
    a = _answer(type="number", number=0)
    assert a.value() == 0


def test_answer_value_payment():
    payment = {"amount": "9.99", "last4": "4242", "name": "John"}
    a = _answer(type="payment", payment=payment)
    assert a.value() == payment


def test_answer_value_all_none_returns_none():
    a = _answer(type="unknown")
    assert a.value() is None


# ---------------------------------------------------------------------------
# FormResponse.answers_by_ref()
# ---------------------------------------------------------------------------


def test_answers_by_ref_basic():
    r = FormResponse(
        response_id="r1",
        answers=[
            Answer(type="text", field=_field("name"), text="Alice"),
            Answer(type="boolean", field=_field("has_car"), boolean=True),
        ],
    )
    result = r.answers_by_ref()
    assert result == {"name": "Alice", "has_car": True}


def test_answers_by_ref_skips_missing_ref():
    r = FormResponse(
        response_id="r1",
        answers=[
            Answer(type="text", field=AnswerField(ref=None), text="orphan"),
            Answer(type="text", field=_field("name"), text="Bob"),
        ],
    )
    result = r.answers_by_ref()
    assert list(result.keys()) == ["name"]


def test_answers_by_ref_empty():
    r = FormResponse(response_id="r1", answers=[])
    assert r.answers_by_ref() == {}


def test_answers_by_ref_choice_extracts_label():
    r = FormResponse(
        response_id="r1",
        answers=[
            Answer(type="choice", field=_field("insurance"), choice={"label": "Generali", "ref": "g"}),
        ],
    )
    assert r.answers_by_ref()["insurance"] == "Generali"


# ---------------------------------------------------------------------------
# _tool decorator
# ---------------------------------------------------------------------------


def _import_tool_decorator():
    from src.typeform.server import _tool
    return _tool


def test_tool_decorator_passes_through_return_value():
    _tool = _import_tool_decorator()

    @_tool
    def my_tool():
        return '{"ok": true}'

    assert my_tool() == '{"ok": true}'


def test_tool_decorator_catches_typeform_api_error():
    _tool = _import_tool_decorator()

    @_tool
    def my_tool():
        raise TypeformAPIError(404, "NOT_FOUND", "Form not found", [])

    result = json.loads(my_tool())
    assert result["error"] is True
    assert result["status_code"] == 404
    assert result["code"] == "NOT_FOUND"
    assert result["description"] == "Form not found"


def test_tool_decorator_catches_unexpected_exception():
    _tool = _import_tool_decorator()

    @_tool
    def my_tool():
        raise RuntimeError("something broke")

    result = json.loads(my_tool())
    assert result["error"] is True
    assert result["code"] == "INTERNAL_ERROR"
    assert "something broke" in result["description"]


def test_tool_decorator_preserves_function_name():
    _tool = _import_tool_decorator()

    @_tool
    def typeform_my_special_tool():
        return "{}"

    assert typeform_my_special_tool.__name__ == "typeform_my_special_tool"


# ---------------------------------------------------------------------------
# typeform_export_responses_csv
# ---------------------------------------------------------------------------


def _make_response(ref_values: dict, response_id: str = "r1") -> FormResponse:
    """Build a FormResponse from a {ref: value} dict of text answers."""
    answers = [
        Answer(type="text", field=_field(ref), text=str(val))
        for ref, val in ref_values.items()
    ]
    return FormResponse(
        response_id=response_id,
        submitted_at="2026-01-01T12:00:00Z",
        landed_at="2026-01-01T11:59:00Z",
        answers=answers,
    )


def _make_response_list(items, total=None) -> ResponseList:
    return ResponseList(
        total_items=total if total is not None else len(items),
        page_count=1,
        items=items,
    )


def test_export_csv_empty_form():
    from src.typeform.server import typeform_export_responses_csv

    with patch("src.typeform.server._client") as mock_client:
        mock_client.return_value.list_responses.return_value = _make_response_list([])
        result = typeform_export_responses_csv(form_id="abc")

    assert result == "response_id,submitted_at\n"


def test_export_csv_single_page():
    from src.typeform.server import typeform_export_responses_csv

    responses = [
        _make_response({"name": "Alice", "age": "30"}, "r1"),
        _make_response({"name": "Bob", "age": "25"}, "r2"),
    ]

    with patch("src.typeform.server._client") as mock_client:
        mock_client.return_value.list_responses.return_value = _make_response_list(responses)
        result = typeform_export_responses_csv(form_id="abc")

    lines = result.strip().split("\n")
    assert lines[0] == "response_id,submitted_at,landed_at,name,age"
    assert "Alice" in lines[1]
    assert "Bob" in lines[2]
    # Single page: list_responses called exactly once
    mock_client.return_value.list_responses.assert_called_once()


def test_export_csv_fetches_multiple_pages():
    from src.typeform.server import typeform_export_responses_csv

    page1 = [_make_response({"q": str(i)}, f"r{i}") for i in range(1000)]
    page2 = [_make_response({"q": str(i)}, f"r{i + 1000}") for i in range(3)]

    with patch("src.typeform.server._client") as mock_client:
        mock_client.return_value.list_responses.side_effect = [
            _make_response_list(page1, total=1003),
            _make_response_list(page2, total=1003),
        ]
        result = typeform_export_responses_csv(form_id="abc")

    assert mock_client.return_value.list_responses.call_count == 2
    lines = result.strip().split("\n")
    assert len(lines) == 1004  # 1 header + 1003 rows


def test_export_csv_column_order_is_insertion_order():
    from src.typeform.server import typeform_export_responses_csv

    # r1 has name+city, r2 adds age — age should appear after city
    r1 = _make_response({"name": "Alice", "city": "Rome"}, "r1")
    r2 = _make_response({"name": "Bob", "city": "Milan", "age": "40"}, "r2")

    with patch("src.typeform.server._client") as mock_client:
        mock_client.return_value.list_responses.return_value = _make_response_list([r1, r2])
        result = typeform_export_responses_csv(form_id="abc")

    header = result.split("\n")[0]
    assert header == "response_id,submitted_at,landed_at,name,city,age"


def test_export_csv_missing_field_is_empty_string():
    from src.typeform.server import typeform_export_responses_csv

    r1 = _make_response({"name": "Alice", "age": "30"}, "r1")
    r2 = _make_response({"name": "Bob"}, "r2")  # no "age"

    with patch("src.typeform.server._client") as mock_client:
        mock_client.return_value.list_responses.return_value = _make_response_list([r1, r2])
        result = typeform_export_responses_csv(form_id="abc")

    lines = result.strip().split("\n")
    bob_row = lines[2]
    assert bob_row.endswith(",")  # age column is empty


# ---------------------------------------------------------------------------
# Tool business logic
# ---------------------------------------------------------------------------


def test_list_forms_clamps_page_size_min():
    from src.typeform.server import typeform_list_forms

    with patch("src.typeform.server._client") as mock_client:
        mock_client.return_value.list_forms.return_value = MagicMock(
            total_items=0, page_count=0, items=[]
        )
        typeform_list_forms(page_size=0)

    _, kwargs = mock_client.return_value.list_forms.call_args
    assert kwargs["page_size"] == 1


def test_list_forms_clamps_page_size_max():
    from src.typeform.server import typeform_list_forms

    with patch("src.typeform.server._client") as mock_client:
        mock_client.return_value.list_forms.return_value = MagicMock(
            total_items=0, page_count=0, items=[]
        )
        typeform_list_forms(page_size=999)

    _, kwargs = mock_client.return_value.list_forms.call_args
    assert kwargs["page_size"] == 200


def test_list_responses_parses_fields_stripping_spaces():
    from src.typeform.server import typeform_list_responses

    with patch("src.typeform.server._client") as mock_client:
        mock_client.return_value.list_responses.return_value = MagicMock(
            total_items=0, page_count=0, items=[]
        )
        typeform_list_responses(form_id="abc", fields=" name , age , ")

    _, kwargs = mock_client.return_value.list_responses.call_args
    assert kwargs["fields"] == ["name", "age"]


def test_delete_responses_empty_list_returns_no_op():
    from src.typeform.server import typeform_delete_responses

    result = json.loads(typeform_delete_responses(form_id="abc", response_tokens=[]))
    assert result["deleted"] is False
    assert result["count"] == 0
