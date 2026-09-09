import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend import engine as quiz
from backend import models as m
from backend.db import Base
from scripts.build_practice_v1 import replace_from_reserve

ROOT = Path(__file__).resolve().parents[1]
CHALLENGE_HASH = "82023DF9C7672FA23FC579EB2A64F6BC59F9EC03266671F1D07DFBBC3833BB2D"


def load(name):
    return json.loads((ROOT / f"artifacts/practice-v1/{name}.json").read_text(encoding="utf-8"))


def test_practice_approved_is_exactly_450_and_reserve_15():
    approved = load("practice_questions_v1_approved")
    reserve = load("practice_questions_v1_reserve")
    audit = load("practice_questions_v1_audit")
    assert len(approved) == 450
    assert len(reserve) == 15
    assert len(audit) == 465
    assert {x["review_status"] for x in approved} == {"approved"}
    assert {x["reference_basis_status"] for x in approved} == {"verified"}


def test_practice_and_challenge_sources_do_not_overlap_and_hash_is_frozen():
    approved = load("practice_questions_v1_approved")
    challenge = json.loads((ROOT / "artifacts/challenge-v1/challenge_questions_v1_approved.json").read_text(encoding="utf-8"))
    practice_ids = {x["source_case_id"] for x in approved}
    challenge_ids = {x["source_case_id"] for x in challenge}
    assert len(challenge) == 100
    assert not (practice_ids & challenge_ids)
    actual = hashlib.sha256((ROOT / "artifacts/challenge-v1/challenge_questions_v1_approved.json").read_bytes()).hexdigest().upper()
    assert actual == CHALLENGE_HASH


def test_each_question_has_four_unique_options_and_single_correct():
    approved = load("practice_questions_v1_approved")
    for item in approved:
        codes = [item["correct_department_code"], *[x["department_code"] for x in item["wrong_options"]]]
        assert len(set(codes)) == 4
        assert len(item["wrong_options"]) == 3
        assert item["final_selection"] is True


def test_origins_and_original_source_are_preserved():
    approved = load("practice_questions_v1_approved")
    origins = {x["case_origin"] for x in approved}
    assert origins == {"baiyun_original", "cross_district_transfer", "citywide_same_target", "public_service_same_target"}
    for item in approved:
        assert item["source_case_id"]
        if item["case_origin"] != "baiyun_original":
            assert item["source_dispatch_target"]
            assert item["training_context"]


def make_db():
    sql_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(sql_engine)
    return sessionmaker(bind=sql_engine, expire_on_commit=False)()


def seed_practice(db, count):
    departments = [m.Department(code=f"D{i}", name=f"部门{i}") for i in range(4)]
    db.add_all(departments)
    db.flush()
    for index in range(count):
        q = m.Question(source_case_id=f"P450-{index}", case_content="正式练习测试工单",
                       correct_department_id=departments[0].id, explanation="职责解析",
                       reference_basis="职责依据原文", question_type="practice")
        db.add(q)
        db.flush()
        db.add_all([m.QuestionOption(question_id=q.id, department_id=d.id, is_correct=i == 0)
                    for i, d in enumerate(departments)])
    db.commit()


def finish(db, payload, user_id):
    for q in payload["questions"]:
        correct_id = db.get(m.Question, q["id"]).correct_department_id
        quiz.answer(db, payload["attempt_id"], user_id, q["id"], correct_id)
    return quiz.complete(db, payload["attempt_id"], user_id)


def test_450_practice_completes_cycle_after_45_rounds():
    db = make_db()
    seed_practice(db, 450)
    for round_no in range(1, 46):
        attempt = quiz.start_practice(db, "u")
        assert attempt["practice_cycle"] == 1
        assert len(attempt["questions"]) == 10
        if round_no == 45:
            seen = set(db.scalars(select(m.PracticeQuestionProgress.question_id).where(
                m.PracticeQuestionProgress.user_id == "u", m.PracticeQuestionProgress.cycle == 1)))
            assert {q["id"] for q in attempt["questions"]} == set(
                db.scalars(select(m.Question.id).where(m.Question.question_type == "practice"))) - seen
        finish(db, attempt, "u")
    completed = len(set(db.scalars(select(m.PracticeQuestionProgress.question_id).where(
        m.PracticeQuestionProgress.user_id == "u", m.PracticeQuestionProgress.cycle == 1))))
    assert completed == 450
    next_attempt = quiz.start_practice(db, "u")
    assert next_attempt["practice_cycle"] == 2


def test_runtime_pool_is_dynamic_and_no_hardcoded_500():
    db = make_db()
    seed_practice(db, 453)
    first = quiz.start_practice(db, "u")
    assert first["practice_cycle"] == 1
    finish(db, first, "u")
    second = quiz.start_practice(db, "u")
    assert len(second["questions"]) == 10


def test_reserve_replacement_mechanism():
    final = [
        {"source_case_id": "A", "topic_key": "education", "target_family": "education"},
        {"source_case_id": "B", "topic_key": "health", "target_family": "health"},
    ]
    reserve = [
        {"source_case_id": "R1", "topic_key": "health", "target_family": "health"},
        {"source_case_id": "R2", "topic_key": "education", "target_family": "education"},
    ]
    result, replaced = replace_from_reserve(final, reserve, ["B"])
    assert replaced == 1
    assert result[1]["source_case_id"] == "R1"
