import ast
import json
from collections import Counter
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend import engine as quiz, models as m
from backend.db import Base
from scripts.import_challenge_v1 import install, validate

ROOT = Path(__file__).resolve().parents[1]
APPROVED = ROOT / "artifacts" / "challenge-v1" / "challenge_questions_v1_approved.json"


def rows():
    return json.loads(APPROVED.read_text(encoding="utf-8"))


def make_db(url="sqlite:///:memory:"):
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = Session(engine); install(db, rows(), True)
    return engine, db


def play(db, user, correct_count):
    attempt = quiz.start_level(db, user, 1)
    for index, item in enumerate(attempt["questions"]):
        q = db.get(m.Question, item["id"])
        selected = q.correct_department_id
        if index >= correct_count:
            selected = next(x.department_id for x in q.options if not x.is_correct)
        quiz.answer(db, attempt["attempt_id"], user, q.id, selected)
    return quiz.complete(db, attempt["attempt_id"], user)


def test_formal_file_has_exact_approved_verified_structure():
    data = rows()
    assert len(data) == len({x["source_case_id"] for x in data}) == 100
    assert Counter(x["final_level"] for x in data) == Counter({i: 10 for i in range(1, 11)})
    assert all(x["review_status"] == "approved" and x["reference_basis_status"] == "verified" for x in data)
    for x in data:
        names = [x["correct_department_name"]] + [x[f"wrong_department_{i}"] for i in range(1, 4)]
        assert len(set(names)) == 4
        assert x["explanation"] and x["reference_basis"] and x["reference_basis_excerpt"] and x["reference_basis_locator"]


def test_dry_run_import_has_exact_options_and_one_answer():
    _, db = make_db()
    assert validate(db)["challenge"] == 100


def test_level_questions_fixed_but_option_order_shuffles(monkeypatch):
    _, db = make_db()
    monkeypatch.setattr(quiz.random, "shuffle", lambda values: None)
    first = quiz.start_level(db, "fixed-a", 1)
    monkeypatch.setattr(quiz.random, "shuffle", lambda values: values.reverse())
    second = quiz.start_level(db, "fixed-b", 1)
    assert [x["id"] for x in first["questions"]] == [x["id"] for x in second["questions"]]
    assert any(a["options"] != b["options"] for a, b in zip(first["questions"], second["questions"]))
    for item in second["questions"]:
        q = db.get(m.Question, item["id"])
        result = quiz.answer(db, second["attempt_id"], "fixed-b", q.id, q.correct_department_id)
        assert result["is_correct"] and result["explanation"] and result["reference_basis"]


def test_score_boundary_unlock_and_permanent_pass():
    _, db = make_db()
    assert play(db, "score-50", 5)["is_passed"] is False
    result = play(db, "score-60", 6)
    assert result["score"] == 60 and result["is_passed"] is True
    assert db.get(m.UserProgress, "score-60").highest_unlocked_level == 2
    result = play(db, "score-60", 5)
    assert result["score"] == 50 and result["passed_this_attempt"] is False and result["is_passed"] is True
    assert play(db, "score-100", 10)["score"] == 100


def test_progress_survives_database_restart(tmp_path):
    url = f"sqlite:///{(tmp_path / 'restart.db').as_posix()}"
    engine, db = make_db(url); play(db, "restart-user", 6); db.close(); engine.dispose()
    engine2 = create_engine(url, connect_args={"check_same_thread": False})
    with Session(engine2) as reopened:
        assert reopened.get(m.UserProgress, "restart-user").highest_unlocked_level == 2
        assert reopened.scalar(select(m.LevelRecord).where(m.LevelRecord.user_id == "restart-user")).is_passed


def test_runtime_backend_has_no_qdrant_rag_or_llm_imports():
    banned = {"qdrant_client", "openai", "langchain"}
    for path in (ROOT / "backend").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = {node.names[0].name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)}
        imported |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
        assert not (imported & banned)
