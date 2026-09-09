"""Verify 25 real-case candidates through an isolated training database."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend import engine as quiz_engine
from backend import models as m
from backend.db import Base
from backend.routes import import_questions
from backend.schemas import ImportPayload


def import_item(item: dict, level: int | None) -> dict:
    return {
        "source_case_id": item["source_case_id"], "question_type": item["question_type"],
        "level": level, "case_content": item["case_content"],
        "correct_department_code": item["correct_department_id"],
        "correct_department_name": item["correct_department_name"],
        "wrong_options": [
            {"department_code": item[f"wrong_department_{i}_id"],
             "department_name": item[f"wrong_department_{i}"]} for i in range(1, 4)
        ],
        "explanation": item["explanation"], "reference_basis": item["reference_basis"],
        "reference_basis_status": item["reference_basis_status"],
        "difficulty_score": item["difficulty_score"], "review_status": "approved",
        "review_note": "仅用于隔离数据库端到端技术验证；不代表业务人工审核通过。",
        **{f"difficulty_dimension_{i}": item[f"difficulty_dimension_{i}"] for i in range(1, 6)},
        **{f"difficulty_dimension_{i}_reason": item[f"difficulty_dimension_{i}_reason"] for i in range(1, 6)},
    }


def answer_attempt(db, payload: dict, user_id: str) -> dict:
    for question in payload["questions"]:
        stored = db.get(m.Question, question["id"])
        feedback = quiz_engine.answer(db, payload["attempt_id"], user_id, question["id"], stored.correct_department_id)
        assert feedback["is_correct"] and feedback["explanation"] and feedback["reference_basis"]
        assert len(question["options"]) == 4
    return quiz_engine.complete(db, payload["attempt_id"], user_id)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--database-url", default="sqlite:///:memory:")
    args = parser.parse_args()
    candidates = json.loads((args.artifact_dir / "candidates.json").read_text(encoding="utf-8"))
    departments = json.loads((args.artifact_dir / "departments.json").read_text(encoding="utf-8"))
    assert len(candidates) == 25
    sql_engine = create_engine(args.database_url)
    Base.metadata.create_all(sql_engine)
    db = sessionmaker(bind=sql_engine, expire_on_commit=False)()
    try:
        db.add_all([m.Department(code=x["department_code"], name=x["department_name"]) for x in departments])
        db.commit()
        rows = [import_item(item, 1 if item["question_type"] == "challenge" else None) for item in candidates]
        result = import_questions(ImportPayload.model_validate({"questions": rows}), db)
        assert result["imported"] == 25
        assert db.scalar(select(m.Question).where(m.Question.review_status != "approved")) is None
        challenge = answer_attempt(db, quiz_engine.start_level(db, "pipeline-user", 1), "pipeline-user")
        practice = answer_attempt(db, quiz_engine.start_practice(db, "pipeline-user"), "pipeline-user")
        assert challenge["score"] == 100 and practice["score"] == 100
        print(json.dumps({"imported": 25, "challenge_questions": 10, "practice_pool": 15,
                          "options_per_question": 4, "judgement": "passed",
                          "explanation": "present", "answers_saved": 20}, ensure_ascii=False))
    finally:
        db.close()


if __name__ == "__main__":
    main()
