from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from backend import engine, models as m
from backend.db import get_db
from backend.schemas import AnswerRequest, ImportPayload

router = APIRouter(prefix="/api")


def current_user(x_training_user_id: str = Header(default="demo-user")) -> str:
    return x_training_user_id


@router.get("/health")
def health():
    return {"status": "ok", "service": "dispatch-training", "runtime_dependencies": ["training_database"]}


@router.get("/levels")
def levels(user_id: str = Depends(current_user), db: Session = Depends(get_db)):
    engine.ensure_user(db, user_id)
    progress = db.get(m.UserProgress, user_id)
    records = {r.level: r for r in db.scalars(select(m.LevelRecord).where(m.LevelRecord.user_id == user_id))}
    return [{"level": level, "state": "locked" if level > progress.highest_unlocked_level else
             "passed" if records.get(level) and records[level].is_passed else "unlocked",
             "best_score": records[level].best_score if level in records else 0,
             "latest_score": records[level].latest_score if level in records else 0,
             "attempt_count": records[level].attempt_count if level in records else 0}
            for level in range(1, 11)]


@router.get("/training/dashboard")
def dashboard(user_id: str = Depends(current_user), db: Session = Depends(get_db)):
    engine.ensure_user(db, user_id)
    progress = db.get(m.UserProgress, user_id)
    practice_attempts = db.scalar(select(func.count()).select_from(m.Attempt).where(
        m.Attempt.user_id == user_id, m.Attempt.mode == "practice", m.Attempt.completed_at.is_not(None))) or 0
    practice_answers = db.scalar(select(func.count()).select_from(m.Answer).join(m.Attempt, m.Attempt.id == m.Answer.attempt_id).where(
        m.Attempt.user_id == user_id, m.Attempt.mode == "practice")) or 0
    practice_correct = db.scalar(select(func.count()).select_from(m.Answer).join(m.Attempt, m.Attempt.id == m.Answer.attempt_id).where(
        m.Attempt.user_id == user_id, m.Attempt.mode == "practice", m.Answer.is_correct.is_(True))) or 0
    return {"highest_unlocked_level": progress.highest_unlocked_level,
            "practice": {"completed_sessions": practice_attempts, "answered": practice_answers,
                         "correct": practice_correct,
                         "accuracy": round(practice_correct / practice_answers * 100) if practice_answers else 0}}


@router.post("/levels/{level}/start")
def start_level(level: int, user_id: str = Depends(current_user), db: Session = Depends(get_db)):
    return engine.start_level(db, user_id, level)


@router.post("/practice/start")
def start_practice(user_id: str = Depends(current_user), db: Session = Depends(get_db)):
    return engine.start_practice(db, user_id)


@router.post("/attempts/{attempt_id}/answer")
def submit_answer(attempt_id: str, payload: AnswerRequest, user_id: str = Depends(current_user), db: Session = Depends(get_db)):
    return engine.answer(db, attempt_id, user_id, payload.question_id, payload.selected_department_id)


@router.post("/attempts/{attempt_id}/complete")
def complete_attempt(attempt_id: str, user_id: str = Depends(current_user), db: Session = Depends(get_db)):
    return engine.complete(db, attempt_id, user_id)


@router.get("/attempts/{attempt_id}")
def attempt_result(attempt_id: str, user_id: str = Depends(current_user), db: Session = Depends(get_db)):
    attempt = db.get(m.Attempt, attempt_id)
    if not attempt or attempt.user_id != user_id:
        raise HTTPException(404, "答题轮次不存在")
    return engine._result(db, attempt)


@router.post("/admin/questions/import")
def import_questions(payload: ImportPayload, db: Session = Depends(get_db)):
    imported = 0
    for item in payload.questions:
        if item.review_status != "approved":
            raise HTTPException(422, "只有review_status=approved的题目可以导入")
        if item.question_type not in {"challenge", "practice"}:
            raise HTTPException(422, "question_type只能是challenge或practice")
        if item.question_type == "challenge" and not item.level:
            raise HTTPException(422, "闯关题必须指定level")
        if len(item.wrong_options) != 3:
            raise HTTPException(422, "每题必须恰好有3个错误选项")
        existing = db.scalar(select(m.Question).where(m.Question.source_case_id == item.source_case_id,
                                                       m.Question.question_type == item.question_type))
        if existing and not payload.replace:
            continue
        departments = [(item.correct_department_code, item.correct_department_name)] + [
            (x.department_code, x.department_name) for x in item.wrong_options]
        if len({code for code, _ in departments}) != 4:
            raise HTTPException(422, "四个部门选项不得重复")
        by_code = {}
        for code, name in departments:
            department = db.scalar(select(m.Department).where(m.Department.code == code))
            if not department:
                raise HTTPException(422, f"部门代码不存在：{code}")
            if department.name != name:
                raise HTTPException(422, f"部门名称与代码不匹配：{code}")
            if not department.is_enabled:
                raise HTTPException(422, f"部门已禁用：{code}")
            by_code[code] = department
        if existing:
            question = existing
            for option in list(db.scalars(select(m.QuestionOption).where(m.QuestionOption.question_id == question.id))):
                db.delete(option)
        else:
            question = m.Question(source_case_id=item.source_case_id)
            db.add(question)
        question.case_origin = item.case_origin
        question.case_content = item.case_content
        question.correct_department_id = by_code[item.correct_department_code].id
        question.explanation = item.explanation
        question.reference_basis = item.reference_basis
        question.reference_basis_title = item.reference_basis_title
        question.reference_basis_source = item.reference_basis_source
        question.reference_basis_excerpt = item.reference_basis_excerpt
        question.reference_basis_locator = item.reference_basis_locator
        question.reference_basis_reason = item.reference_basis_reason
        question.question_type = item.question_type
        question.level = item.level
        question.difficulty_score = item.difficulty_score
        for index in range(1, 6):
            setattr(question, f"difficulty_dimension_{index}", getattr(item, f"difficulty_dimension_{index}"))
            setattr(question, f"difficulty_dimension_{index}_reason", getattr(item, f"difficulty_dimension_{index}_reason"))
        question.review_status = item.review_status
        question.review_note = item.review_note
        question.reference_basis_status = item.reference_basis_status
        question.is_enabled = item.enabled
        question.final_selection = item.final_selection
        db.flush()
        for code, _ in departments:
            db.add(m.QuestionOption(question_id=question.id, department_id=by_code[code].id,
                                    is_correct=code == item.correct_department_code))
        imported += 1
    db.commit()
    return {"imported": imported, "received": len(payload.questions)}


@router.patch("/admin/questions/{question_id}/disable")
def disable_question(question_id: str, db: Session = Depends(get_db)):
    if not db.get(m.Question, question_id):
        raise HTTPException(404, "题目不存在")
    db.execute(update(m.Question).where(m.Question.id == question_id).values(is_enabled=False))
    db.commit()
    return {"id": question_id, "is_enabled": False}
