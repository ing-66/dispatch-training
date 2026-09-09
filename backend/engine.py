import random

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from backend import models as m


QUESTION_COUNT = 10
PASS_SCORE = 60


def ensure_user(db: Session, user_id: str, display_name: str = "训练用户") -> m.User:
    user = db.get(m.User, user_id)
    if not user:
        user = m.User(id=user_id, display_name=display_name)
        db.add(user)
        db.add(m.UserProgress(user_id=user_id, highest_unlocked_level=1))
        try:
            db.commit()
        except IntegrityError:
            # Concurrent first requests may both observe a missing user. The
            # winner creates it; the loser resumes from the committed row.
            db.rollback()
            user = db.get(m.User, user_id)
            if not user:
                raise
    return user


def _question_payload(db: Session, question: m.Question) -> dict:
    department_ids = [option.department_id for option in question.options]
    departments = {d.id: d for d in db.scalars(select(m.Department).where(m.Department.id.in_(department_ids)))}
    options = [{"department_id": did, "name": departments[did].name} for did in department_ids]
    random.shuffle(options)
    return {"id": question.id, "case_origin": question.case_origin or "baiyun_original",
            "case_content": question.case_content, "options": options}


def _attempt_payload(db: Session, attempt: m.Attempt, questions: list[m.Question]) -> dict:
    return {
        "attempt_id": attempt.id,
        "mode": attempt.mode,
        "level": attempt.level,
        "practice_cycle": attempt.practice_cycle,
        "total_count": len(questions),
        "questions": [_question_payload(db, q) for q in questions],
    }


def start_level(db: Session, user_id: str, level: int) -> dict:
    if not 1 <= level <= 10:
        raise HTTPException(404, "关卡不存在")
    ensure_user(db, user_id)
    progress = db.get(m.UserProgress, user_id)
    if level > progress.highest_unlocked_level:
        raise HTTPException(403, "关卡尚未解锁")
    questions = list(db.scalars(select(m.Question).options(selectinload(m.Question.options)).where(
        m.Question.question_type == "challenge", m.Question.level == level, m.Question.is_enabled.is_(True)
    ).order_by(m.Question.source_case_id)))
    if len(questions) != QUESTION_COUNT:
        raise HTTPException(409, f"第{level}关必须恰好配置10道启用题，当前{len(questions)}道")
    attempt = m.Attempt(user_id=user_id, mode="challenge", level=level, total_count=QUESTION_COUNT)
    db.add(attempt)
    db.flush()
    for index, question in enumerate(questions, 1):
        db.add(m.AttemptQuestion(attempt_id=attempt.id, question_id=question.id, position=index))
    db.commit()
    return _attempt_payload(db, attempt, questions)


def _current_practice_cycle(db: Session, user_id: str, pool_size: int) -> int:
    highest = db.scalar(select(func.max(m.PracticeQuestionProgress.cycle)).where(m.PracticeQuestionProgress.user_id == user_id)) or 1
    done = db.scalar(select(func.count()).select_from(m.PracticeQuestionProgress).where(
        m.PracticeQuestionProgress.user_id == user_id, m.PracticeQuestionProgress.cycle == highest
    )) or 0
    return highest + 1 if done >= pool_size else highest


def start_practice(db: Session, user_id: str) -> dict:
    ensure_user(db, user_id)
    pool = list(db.scalars(select(m.Question).options(selectinload(m.Question.options)).where(
        m.Question.question_type == "practice", m.Question.is_enabled.is_(True)
    )))
    if len(pool) < QUESTION_COUNT:
        raise HTTPException(409, "自由练习至少需要10道启用题")
    cycle = _current_practice_cycle(db, user_id, len(pool))
    completed_ids = set(db.scalars(select(m.PracticeQuestionProgress.question_id).where(
        m.PracticeQuestionProgress.user_id == user_id, m.PracticeQuestionProgress.cycle == cycle
    )))
    unseen = [q for q in pool if q.id not in completed_ids]
    chosen = random.sample(unseen, min(QUESTION_COUNT, len(unseen)))
    if len(chosen) < QUESTION_COUNT:
        remaining = [q for q in pool if q.id not in {x.id for x in chosen}]
        chosen.extend(random.sample(remaining, QUESTION_COUNT - len(chosen)))
    attempt = m.Attempt(user_id=user_id, mode="practice", practice_cycle=cycle, total_count=QUESTION_COUNT)
    db.add(attempt)
    db.flush()
    for index, question in enumerate(chosen, 1):
        db.add(m.AttemptQuestion(attempt_id=attempt.id, question_id=question.id, position=index))
    db.commit()
    return _attempt_payload(db, attempt, chosen)


def answer(db: Session, attempt_id: str, user_id: str, question_id: str, selected_department_id: str) -> dict:
    attempt = db.get(m.Attempt, attempt_id)
    if not attempt or attempt.user_id != user_id:
        raise HTTPException(404, "答题轮次不存在")
    if attempt.completed_at:
        raise HTTPException(409, "答题轮次已经完成")
    included = db.scalar(select(m.AttemptQuestion).where(
        m.AttemptQuestion.attempt_id == attempt_id, m.AttemptQuestion.question_id == question_id
    ))
    if not included:
        raise HTTPException(400, "题目不属于本轮答题")
    if db.scalar(select(m.Answer).where(m.Answer.attempt_id == attempt_id, m.Answer.question_id == question_id)):
        raise HTTPException(409, "本题已经提交")
    question = db.get(m.Question, question_id)
    valid_option = db.scalar(select(m.QuestionOption).where(
        m.QuestionOption.question_id == question_id,
        m.QuestionOption.department_id == selected_department_id,
    ))
    if not valid_option:
        raise HTTPException(400, "所选部门不是本题选项")
    correct = selected_department_id == question.correct_department_id
    db.add(m.Answer(attempt_id=attempt_id, user_id=user_id, question_id=question_id,
                    selected_department_id=selected_department_id,
                    correct_department_id=question.correct_department_id, is_correct=correct))
    db.commit()
    correct_department = db.get(m.Department, question.correct_department_id)
    selected_department = db.get(m.Department, selected_department_id)
    return {"is_correct": correct, "selected_department": selected_department.name,
            "correct_department": {"id": correct_department.id, "name": correct_department.name},
            "explanation": question.explanation, "reference_basis": question.reference_basis}


def complete(db: Session, attempt_id: str, user_id: str) -> dict:
    attempt = db.get(m.Attempt, attempt_id)
    if not attempt or attempt.user_id != user_id:
        raise HTTPException(404, "答题轮次不存在")
    if attempt.completed_at:
        return _result(db, attempt)
    answers = list(db.scalars(select(m.Answer).where(m.Answer.attempt_id == attempt_id)))
    if len(answers) != attempt.total_count:
        raise HTTPException(409, f"尚有{attempt.total_count - len(answers)}题未完成")
    correct_count = sum(item.is_correct for item in answers)
    attempt.correct_count = correct_count
    attempt.score = round(correct_count / attempt.total_count * 100)
    attempt.completed_at = m.now()
    if attempt.mode == "challenge":
        record = db.scalar(select(m.LevelRecord).where(m.LevelRecord.user_id == user_id, m.LevelRecord.level == attempt.level))
        if not record:
            record = m.LevelRecord(user_id=user_id, level=attempt.level, is_passed=False,
                                   best_score=0, latest_score=0, attempt_count=0)
            db.add(record)
        record.latest_score = attempt.score
        record.best_score = max(record.best_score, attempt.score)
        record.attempt_count += 1
        record.is_passed = record.is_passed or attempt.score >= PASS_SCORE
        if record.is_passed:
            progress = db.get(m.UserProgress, user_id)
            progress.highest_unlocked_level = max(progress.highest_unlocked_level, min(10, attempt.level + 1))
    else:
        for item in answers:
            progress = db.scalar(select(m.PracticeQuestionProgress).where(
                m.PracticeQuestionProgress.user_id == user_id,
                m.PracticeQuestionProgress.question_id == item.question_id,
                m.PracticeQuestionProgress.cycle == attempt.practice_cycle,
            ))
            if progress:
                progress.completed_count += 1
                progress.last_answered_at = m.now()
            else:
                db.add(m.PracticeQuestionProgress(user_id=user_id, question_id=item.question_id, cycle=attempt.practice_cycle))
    db.commit()
    return _result(db, attempt)


def _result(db: Session, attempt: m.Attempt) -> dict:
    passed = attempt.mode == "challenge" and attempt.score >= PASS_SCORE
    permanent_passed = False
    if attempt.mode == "challenge":
        record = db.scalar(select(m.LevelRecord).where(m.LevelRecord.user_id == attempt.user_id, m.LevelRecord.level == attempt.level))
        permanent_passed = bool(record and record.is_passed)
    return {"attempt_id": attempt.id, "mode": attempt.mode, "level": attempt.level,
            "score": attempt.score, "correct_count": attempt.correct_count,
            "incorrect_count": attempt.total_count - attempt.correct_count,
            "total_count": attempt.total_count, "passed_this_attempt": passed,
            "is_passed": permanent_passed, "completed_at": attempt.completed_at}
