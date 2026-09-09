"""End-to-end verification against the installed training database only."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import engine as quiz, models as m
from scripts.import_challenge_v1 import validate


def play(db: Session, user: str, correct_count: int) -> dict:
    attempt = quiz.start_level(db, user, 1)
    for index, item in enumerate(attempt["questions"]):
        question = db.get(m.Question, item["id"])
        selected = question.correct_department_id if index < correct_count else next(x.department_id for x in question.options if not x.is_correct)
        answer = quiz.answer(db, attempt["attempt_id"], user, question.id, selected)
        if not answer["explanation"] or not answer["reference_basis"]:
            raise SystemExit("判题响应未返回固定解析或职责依据")
    return quiz.complete(db, attempt["attempt_id"], user)


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--database-url", default="sqlite:///./dispatch_training.db")
    args = parser.parse_args(); engine = create_engine(args.database_url, connect_args={"check_same_thread": False})
    with Session(engine) as db:
        inventory = validate(db)
        original_shuffle = quiz.random.shuffle
        quiz.random.shuffle = lambda values: None
        first = quiz.start_level(db, "phase32-fixed-a", 1)
        quiz.random.shuffle = lambda values: values.reverse()
        second = quiz.start_level(db, "phase32-fixed-b", 1)
        quiz.random.shuffle = original_shuffle
        if [x["id"] for x in first["questions"]] != [x["id"] for x in second["questions"]]: raise SystemExit("固定题集不一致")
        if not any(a["options"] != b["options"] for a, b in zip(first["questions"], second["questions"])): raise SystemExit("选项未shuffle")
        fifty = play(db, "phase32-score-50", 5); sixty = play(db, "phase32-score-60", 6)
        low_after_pass = play(db, "phase32-score-60", 5); hundred = play(db, "phase32-score-100", 10)
        if fifty["is_passed"] or not sixty["is_passed"] or not low_after_pass["is_passed"] or hundred["score"] != 100:
            raise SystemExit("通关边界或永久通关失败")
    engine.dispose()
    engine = create_engine(args.database_url, connect_args={"check_same_thread": False})
    with Session(engine) as db:
        if db.get(m.UserProgress, "phase32-score-60").highest_unlocked_level != 2: raise SystemExit("数据库重启后进度未保存")
    print(json.dumps({**inventory, "fixed_questions": True, "option_shuffle": True, "score_50": False,
                      "score_60": True, "score_100": True, "permanent_pass": True,
                      "restart_persistence": True, "runtime_dependencies": ["training_database"]}, ensure_ascii=False))


if __name__ == "__main__": main()
