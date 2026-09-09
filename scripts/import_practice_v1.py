"""Dry-run or install the approved 450-question practice V1 set."""
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


def load_approved(path: Path) -> list[dict]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if len(rows) != 450:
        raise SystemExit(f"approved文件必须精确450题：{len(rows)}")
    if any(x["question_type"] != "practice" for x in rows):
        raise SystemExit("approved文件包含非practice题")
    if any(x["review_status"] != "approved" or x["reference_basis_status"] != "verified" for x in rows):
        raise SystemExit("存在非approved或未verified题")
    ids = [x["source_case_id"] for x in rows]
    if len(ids) != len(set(ids)):
        raise SystemExit("source_case_id重复")
    return rows


def ensure_departments(db: Session, rows: list[dict]) -> None:
    pairs = {}
    for x in rows:
        pairs[x["correct_department_code"]] = x["correct_department_name"]
        for opt in x["wrong_options"]:
            pairs[opt["department_code"]] = opt["department_name"]
    for code, name in pairs.items():
        department = db.scalar(select(m.Department).where(m.Department.code == code))
        if department:
            if department.name != name:
                raise SystemExit(f"部门代码名称冲突：{code}")
            department.is_enabled = True
        else:
            db.add(m.Department(code=code, name=name, is_enabled=True))
    db.commit()


def validate(db: Session) -> dict:
    practice = list(db.scalars(select(m.Question).where(
        m.Question.question_type == "practice", m.Question.is_enabled.is_(True))))
    challenge = list(db.scalars(select(m.Question).where(
        m.Question.question_type == "challenge", m.Question.is_enabled.is_(True))))
    if len(practice) != 450:
        raise SystemExit(f"启用practice不是450：{len(practice)}")
    if len(challenge) != 100:
        raise SystemExit(f"启用challenge不是100：{len(challenge)}")
    practice_ids = {x.source_case_id for x in practice}
    challenge_ids = {x.source_case_id for x in challenge}
    if practice_ids & challenge_ids:
        raise SystemExit("challenge与practice source_case_id存在重叠")
    if any(x.review_status != "approved" or x.reference_basis_status != "verified" or not x.final_selection for x in practice):
        raise SystemExit("practice正式题状态门禁失败")
    for q in practice:
        options = list(db.scalars(select(m.QuestionOption).where(m.QuestionOption.question_id == q.id)))
        if len(options) != 4 or sum(x.is_correct for x in options) != 1 or len({x.department_id for x in options}) != 4:
            raise SystemExit(f"选项门禁失败：{q.source_case_id}")
        if not all((q.explanation, q.reference_basis, q.reference_basis_excerpt, q.reference_basis_locator)):
            raise SystemExit(f"解析或依据为空：{q.source_case_id}")
        if not q.case_origin:
            raise SystemExit(f"来源类型缺失：{q.source_case_id}")
    return {"practice": len(practice), "challenge": len(challenge),
            "origins": {origin: sum(1 for x in practice if x.case_origin == origin)
                        for origin in ("baiyun_original", "cross_district_transfer",
                                       "citywide_same_target", "public_service_same_target")}}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approved", type=Path, required=True)
    parser.add_argument("--database-url", default="sqlite:///./dispatch_training.db")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--disable-old", action="store_true")
    parser.add_argument("--challenge-approved", type=Path,
                        default=Path("artifacts/challenge-v1/challenge_questions_v1_approved.json"))
    args = parser.parse_args()
    rows = load_approved(args.approved)
    database_url = "sqlite:///:memory:" if args.dry_run else args.database_url
    backup_path = ""
    if not args.dry_run and database_url.startswith("sqlite:///./"):
        db_path = Path(database_url.removeprefix("sqlite:///./")).resolve()
        if db_path.exists():
            backup_path = str(db_path.with_name(
                f"{db_path.name}.pre-practice-v1-{datetime.now():%Y%m%d-%H%M%S}.bak"))
            shutil.copy2(db_path, backup_path)
    engine = create_engine(database_url,
                           connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {})
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        if args.dry_run:
            challenge = json.loads(args.challenge_approved.read_text(encoding="utf-8"))
            if len(challenge) != 100:
                raise SystemExit("challenge approved不是100")
            challenge_rows = [{
                "source_case_id": x["source_case_id"], "case_origin": "baiyun_original",
                "question_type": "challenge", "level": x["final_level"],
                "case_content": x["case_content"], "correct_department_code": x["correct_department_id"],
                "correct_department_name": x["correct_department_name"],
                "wrong_options": [{"department_code": x[f"wrong_department_{i}_id"],
                                   "department_name": x[f"wrong_department_{i}"]} for i in range(1, 4)],
                "explanation": x["explanation"], "reference_basis": x["reference_basis"],
                "reference_basis_title": x["reference_basis_title"],
                "reference_basis_source": x["reference_basis_source"],
                "reference_basis_excerpt": x["reference_basis_excerpt"],
                "reference_basis_locator": x["reference_basis_locator"],
                "reference_basis_reason": x["reference_basis_reason"], "reference_basis_status": "verified",
                "review_status": "approved", "enabled": True, "final_selection": True,
            } for x in challenge]
            ensure_departments(db, rows + challenge_rows)
            import_questions(ImportPayload.model_validate({"questions": challenge_rows, "replace": False}), db)
        ensure_departments(db, rows)
        payload = ImportPayload.model_validate({
            "questions": [{**x, "wrong_options": x["wrong_options"]} for x in rows],
            "replace": False,
        })
        result = import_questions(payload, db)
        if args.disable_old:
            selected = {x["source_case_id"] for x in rows}
            db.execute(update(m.Question).where(
                m.Question.question_type == "practice",
                m.Question.source_case_id.not_in(selected)).values(is_enabled=False, final_selection=False))
            db.commit()
        report = validate(db)
    print(json.dumps({**result, **report, "dry_run": args.dry_run, "backup": backup_path}, ensure_ascii=False))


if __name__ == "__main__":
    main()
