"""Repeated forms share one memory entry without mixing distinct candidate facts."""

import json
from types import SimpleNamespace

import pytest

from libs.common.screening_review import ScreeningReviewStore


def job(identifier=1):
    return SimpleNamespace(id=identifier, naukri_job_id=str(identifier), title="Java Developer")


def test_reordered_choices_and_question_punctuation_do_not_create_duplicates(tmp_path):
    store = ScreeningReviewStore(tmp_path)
    first = {"question": "Are you willing to relocate?", "options": ["Yes", "No"]}
    repeated = {"question": "ARE YOU WILLING TO RELOCATE!", "options": ["No", "Yes"]}
    identifier = store.remember(first, job())
    assert store.remember(repeated, job(2)) == identifier
    assert len(store.pending()) == 1
    assert store.save_answers({identifier: "No"}) == [1, 2]
    assert store.observe(repeated, "Yes", job(2), "ai_suggestion", "profile") == identifier
    assert store.answer_for(repeated, job(2)) == "No"
    assert store.memory()["total"] == 1
    with store._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0] == 1


def test_existing_option_order_ids_are_reused_after_upgrade(tmp_path):
    store = ScreeningReviewStore(tmp_path)
    with store._connect() as connection:
        connection.execute(
            "INSERT INTO questions VALUES(?,?,?,?,?,?,?,?)",
            (
                "legacy",
                "relocation",
                "Relocation?",
                "text",
                json.dumps(["Yes", "No"]),
                "",
                "2026-01-01",
                0,
            ),
        )
    question = {"question": "Relocation?", "options": ["No", "Yes"]}
    assert store.remember(question, job()) == "legacy"
    store.mark_resolved_from_facts(question, job())
    assert not store.pending()
    assert store.observe(question, "No", job(), "profile", "profile") == "legacy"
    assert store.memory()["total"] == 1


def test_memory_uses_latest_confirmation_once_and_combines_reuse_counts(tmp_path):
    store = ScreeningReviewStore(tmp_path)
    numeric = {"question": "Custom experience in years", "type": "number"}
    choice = {**numeric, "type": "dropdown", "options": ["0-2 years", "3-5 years"]}
    old = store.remember(numeric, job())
    store.save_answers({old: "1"})
    current = store.remember(choice, job(2))
    store.save_answers({current: "3-5 years"})
    store.observe({**numeric, "type": "text"}, "0", job(), "profile", "new-context")
    with store._connect() as connection:
        connection.execute("UPDATE answer_memory SET use_count=2 WHERE question_id=?", (old,))
        connection.execute("UPDATE answer_memory SET use_count=3 WHERE question_id=?", (current,))
    result = ScreeningReviewStore(tmp_path).memory()
    assert result["total"] == len(result["items"]) == 1
    assert result["items"][0]["id"] == current
    assert result["items"][0]["answer"] == "3-5 years"
    assert result["items"][0]["source"] == "confirmed"
    assert result["items"][0]["use_count"] == 5
    assert not store.answer_for(numeric, job())
    store.forget(current)
    assert store.memory() == {"items": [], "total": 0}


def test_pending_variants_share_one_prompt_and_confirmation_resolves_all_ready_jobs(tmp_path):
    store = ScreeningReviewStore(tmp_path)
    numeric = {"question": "Custom experience in years", "type": "number"}
    store.remember(numeric, job())
    store.remember({**numeric, "type": "text"}, job(2))
    pending = store.pending()
    assert len(pending) == 1
    assert [item["job_id"] for item in pending[0]["jobs"]] == [1, 2]
    assert store.save_answers({pending[0]["id"]: "1"}) == [1, 2]
    assert not store.pending()
    assert store.answer_for(numeric, job()) == "1"
    assert store.memory()["total"] == 1


def test_incompatible_format_stays_pending_instead_of_guessing_an_exact_value(tmp_path):
    store = ScreeningReviewStore(tmp_path)
    numeric = {"question": "Custom experience in years", "type": "number"}
    store.remember(numeric, job())
    choice = {**numeric, "type": "text", "options": ["0-2 years", "3-5 years"]}
    identifier = store.remember(choice, job(2))
    assert store.save_answers({identifier: "3-5 years"}) == [2]
    pending = store.pending()
    assert len(pending) == 1 and pending[0]["field_type"] == "number"
    assert [item["job_id"] for item in pending[0]["jobs"]] == [1]
    assert not store.answer_for(numeric, job())


def test_unique_counts_and_search_are_applied_after_selecting_current_answers(tmp_path):
    store = ScreeningReviewStore(tmp_path)
    numeric = {"question": "Experience in years", "type": "number"}
    store.observe(numeric, "1", job(), "profile", "first")
    store.observe({**numeric, "type": "text"}, "1", job(), "profile", "second")
    store.observe({"question": "Expected CTC in LPA"}, "8", job(), "profile", "second")
    assert store.memory(limit=1)["total"] == 2
    assert len(store.memory(limit=1)["items"]) == 1
    assert len(store.memory("experience")["items"]) == 1
    assert store.memory("nothing matches") == {"items": [], "total": 2}


def test_equal_answers_do_not_merge_different_skills_units_history_or_job_context(tmp_path):
    store = ScreeningReviewStore(tmp_path)
    questions = [
        "C++ experience in years",
        "C# experience in years",
        "C++ experience in months",
        "Education — College A — Start Year",
        "Education — College B — Start Year",
    ]
    for question in questions:
        store.observe({"question": question}, "1", job(), "profile", "context")
    for employer in [job(), job(2)]:
        identifier = store.remember({"question": "Why should we hire you?"}, employer)
        store.save_answers({identifier: "My published skills match this role."})
    assert store.memory()["total"] == len(store.memory()["items"]) == 7


def test_conflicting_duplicate_confirmations_are_rejected_atomically(tmp_path):
    store = ScreeningReviewStore(tmp_path)
    first = store.remember({"question": "Custom fact", "type": "text"}, job())
    second = store.remember({"question": "Custom fact", "type": "number"}, job())
    revision = store.revision()
    with pytest.raises(ValueError, match="one confirmation"):
        store.save_answers({first: "1", second: "2"})
    assert store.revision() == revision
    assert store.memory()["total"] == 0


def test_text_answer_never_resolves_a_matching_attachment_control(tmp_path):
    store = ScreeningReviewStore(tmp_path)
    store.remember({"question": "Supporting document", "type": "file"}, job())
    text = store.remember({"question": "Supporting document", "type": "text"}, job(2))
    assert store.save_answers({text: "Available on request"}) == [2]
    assert store.pending()[0]["field_type"] == "file"
