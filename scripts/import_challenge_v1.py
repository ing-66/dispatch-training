"""Dry-run or safely install the approved V1 challenge set."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import models as m
from backend.db import Base
from backend.routes import import_questions
from backend.schemas import ImportPayload


def import_item(x: dict) -> dict:
    return {
        "source_case_id": x["source_case_id"], "question_type": "challenge", "level": x["final_level"],
        "case_content": x["case_content"], "correct_department_code": x["correct_department_id"],
        "correct_department_name": x["correct_department_name"],
        "wrong_options": [{"department_code": x[f"wrong_department_{i}_id"], "department_name": x[f"wrong_department_{i}"]} for i in range(1, 4)],
        "explanation": x["explanation"], "reference_basis": x["reference_basis"],
        "reference_basis_title": x["reference_basis_title"], "reference_basis_source": x["reference_basis_source"],
        "reference_basis_excerpt": x["reference_basis_excerpt"], "reference_basis_locator": x["reference_basis_locator"],
        "reference_basis_reason": x["reference_basis_reason"], "reference_basis_status": "verified",
        "difficulty_score": x["difficulty_score"],
        **{f"difficulty_dimension_{i}": x[f"difficulty_dimension_{i}"] for i in range(1, 6)},
        **{f"difficulty_dimension_{i}_reason": x[f"difficulty_dimension_{i}_reason"] for i in range(1, 6)},
        "review_status": "approved", "review_note": "Phase 3.2主审核及职责依据终验通过",
        "enabled": True, "final_selection": True,
    }


def ensure_departments(db: Session, rows: list[dict]) -> None:
    pairs = {}
    for x in rows:
        pairs[x["correct_department_id"]] = x["correct_department_name"]
        for i in range(1, 4): pairs[x[f"wrong_department_{i}_id"]] = x[f"wrong_department_{i}"]
    for code, name in pairs.items():
        department = db.scalar(select(m.Department).where(m.Department.code == code))
        if department:
            if department.name != name: raise SystemExit(f"部门代码名称冲突：{code}")
            department.is_enabled = True
        else:
            db.add(m.Department(code=code, name=name, is_enabled=True))
    db.commit()


def install(db: Session, rows: list[dict], disable_old: bool) -> dict:
    ensure_departments(db, rows)
    payload = ImportPayload.model_validate({"questions": [import_item(x) for x in rows], "replace": True})
    result = import_questions(payload, db)
    if disable_old:
        selected = {x["source_case_id"] for x in rows}
        db.execute(update(m.Question).where(m.Question.question_type == "challenge",
                                            m.Question.source_case_id.not_in(selected)).values(is_enabled=False, final_selection=False))
        db.commit()
    return result


def validate(db: Session) -> dict:
    rows = list(db.scalars(select(m.Question).where(m.Question.question_type == "challenge", m.Question.is_enabled.is_(True))))
    if len(rows) != 100: raise SystemExit(f"启用正式闯关题不是100道：{len(rows)}")
    for level in range(1, 11):
        if sum(x.level == level for x in rows) != 10: raise SystemExit(f"Level {level}不是10道")
    if any(x.review_status != "approved" or x.reference_basis_status != "verified" or not x.final_selection for x in rows):
        raise SystemExit("正式题状态门禁失败")
    for q in rows:
        options = list(db.scalars(select(m.QuestionOption).where(m.QuestionOption.question_id == q.id)))
        if len(options) != 4 or sum(x.is_correct for x in options) != 1 or len({x.department_id for x in options}) != 4:
            raise SystemExit(f"选项门禁失败：{q.source_case_id}")
        if not all((q.explanation, q.reference_basis, q.reference_basis_excerpt, q.reference_basis_locator)):
            raise SystemExit(f"解析或职责依据为空：{q.source_case_id}")
    return {"challenge": len(rows), "levels": {str(i): sum(x.level == i for x in rows) for i in range(1, 11)}}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approved", type=Path, required=True)
    parser.add_argument("--database-url", default="sqlite:///./dispatch_training.db")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--disable-old", action="store_true")
    args = parser.parse_args()
    rows = json.loads(args.approved.read_text(encoding="utf-8"))
    if len(rows) != 100: raise SystemExit("approved文件必须精确100题")
    database_url = "sqlite:///:memory:" if args.dry_run else args.database_url
    if not args.dry_run and database_url.startswith("sqlite:///./"):
        db_path = Path(database_url.removeprefix("sqlite:///./")).resolve()
        if db_path.exists():
            backup = db_path.with_name(f"{db_path.name}.pre-v1-{datetime.now():%Y%m%d-%H%M%S}.bak")
            shutil.copy2(db_path, backup); print(json.dumps({"backup": str(backup)}, ensure_ascii=False))
    engine = create_engine(database_url, connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {})
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        result = install(db, rows, args.disable_old)
        report = validate(db)
    print(json.dumps({**result, **report, "dry_run": args.dry_run}, ensure_ascii=False))


if __name__ == "__main__":
    main()
