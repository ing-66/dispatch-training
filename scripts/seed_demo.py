from sqlalchemy import select

from backend import models as m
from backend.db import Base, SessionLocal, engine


DEPARTMENTS = [
    ("HRSS", "区人力资源和社会保障局"),
    ("MARKET", "区市场监督管理局"),
    ("STREET", "属地街道办事处"),
    ("HOUSING", "区住房建设和交通局"),
]


def main():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        departments = {}
        for code, name in DEPARTMENTS:
            item = db.scalar(select(m.Department).where(m.Department.code == code))
            if not item:
                item = m.Department(code=code, name=name); db.add(item); db.flush()
            departments[code] = item
        for kind, count in (("challenge", 20), ("practice", 20)):
            for index in range(1, count + 1):
                source = f"DEMO-{kind.upper()}-{index:03d}"
                if db.scalar(select(m.Question).where(m.Question.source_case_id == source, m.Question.question_type == kind)):
                    continue
                correct_code = DEPARTMENTS[(index - 1) % 4][0]
                question = m.Question(source_case_id=source,
                    case_content=f"【演示题】市民反映第{index}类热线事项，请判断应由哪个部门承办。",
                    correct_department_id=departments[correct_code].id,
                    explanation=f"该演示事项按预设职责应由{departments[correct_code].name}承办。",
                    reference_basis="演示数据，无正式政策效力。正式上线前必须替换并人工复核。",
                    question_type=kind, level=((index - 1) // 10 + 1) if kind == "challenge" else None,
                    difficulty_score=20 + index if kind == "challenge" else None,
                    review_status="approved", review_note="演示数据，仅用于流程验证",
                    reference_basis_status="needs_review")
                db.add(question); db.flush()
                for code, _ in DEPARTMENTS:
                    db.add(m.QuestionOption(question_id=question.id, department_id=departments[code].id,
                                            is_correct=code == correct_code))
        db.commit()
    print("Demo seed ready: challenge levels 1-2 and 20 practice questions.")


if __name__ == "__main__":
    main()
