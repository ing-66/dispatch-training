import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import models as m
from backend.db import Base
from backend.routes import import_questions
from backend.schemas import ImportPayload


def make_db():
    sql_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(sql_engine)
    return sessionmaker(bind=sql_engine, expire_on_commit=False)()


def payload(status="approved", code="D0"):
    return ImportPayload.model_validate({"questions": [{
        "source_case_id": "formal-1", "question_type": "practice", "case_content": "完整测试工单内容",
        "correct_department_code": code, "correct_department_name": "部门0",
        "wrong_options": [{"department_code": f"D{i}", "department_name": f"部门{i}"} for i in range(1, 4)],
        "explanation": "固定解析", "reference_basis": "待审核依据", "review_status": status,
    }]})


def test_only_approved_questions_can_be_imported():
    db = make_db()
    with pytest.raises(HTTPException, match="approved"):
        import_questions(payload("pending"), db)


def test_import_never_invents_departments():
    db = make_db()
    with pytest.raises(HTTPException, match="部门代码不存在"):
        import_questions(payload(), db)


def test_approved_question_imports_with_existing_departments():
    db = make_db()
    db.add_all([m.Department(code=f"D{i}", name=f"部门{i}") for i in range(4)])
    db.commit()
    assert import_questions(payload(), db)["imported"] == 1
