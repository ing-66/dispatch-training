from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.db import Base
from backend import engine as quiz
from backend import models as m


def make_db():
    sql_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(sql_engine)
    return sessionmaker(bind=sql_engine, expire_on_commit=False)()


def seed(db: Session, challenge_levels=(1, 2), practice_count=15):
    departments = [m.Department(code=f"D{i}", name=f"部门{i}") for i in range(4)]
    db.add_all(departments); db.flush()
    for level in challenge_levels:
        for index in range(10):
            q = m.Question(source_case_id=f"C-{level}-{index}", case_content="测试工单",
                           correct_department_id=departments[0].id, explanation="职责依据",
                           reference_basis="正式文件", question_type="challenge", level=level)
            db.add(q); db.flush()
            db.add_all([m.QuestionOption(question_id=q.id, department_id=d.id, is_correct=i == 0)
                        for i, d in enumerate(departments)])
    for index in range(practice_count):
        q = m.Question(source_case_id=f"P-{index}", case_content="练习工单",
                       correct_department_id=departments[0].id, explanation="职责依据",
                       reference_basis="正式文件", question_type="practice")
        db.add(q); db.flush()
        db.add_all([m.QuestionOption(question_id=q.id, department_id=d.id, is_correct=i == 0)
                    for i, d in enumerate(departments)])
    db.commit()
    return departments


def finish(db, payload, user_id, correct_count):
    for index, question in enumerate(payload["questions"]):
        selected = question["options"][0]["department_id"]
        correct_id = db.get(m.Question, question["id"]).correct_department_id
        if index < correct_count:
            selected = correct_id
        elif selected == correct_id:
            selected = question["options"][1]["department_id"]
        quiz.answer(db, payload["attempt_id"], user_id, question["id"], selected)
    return quiz.complete(db, payload["attempt_id"], user_id)


def test_scores_and_unlock_at_sixty():
    db = make_db(); seed(db)
    failed = finish(db, quiz.start_level(db, "u", 1), "u", 5)
    assert failed["score"] == 50 and not failed["is_passed"]
    assert db.get(m.UserProgress, "u").highest_unlocked_level == 1
    passed = finish(db, quiz.start_level(db, "u", 1), "u", 6)
    assert passed["score"] == 60 and passed["is_passed"]
    assert db.get(m.UserProgress, "u").highest_unlocked_level == 2


def test_pass_is_permanent_after_lower_retry():
    db = make_db(); seed(db)
    finish(db, quiz.start_level(db, "u", 1), "u", 7)
    retry = finish(db, quiz.start_level(db, "u", 1), "u", 3)
    record = db.scalar(select(m.LevelRecord).where(m.LevelRecord.user_id == "u", m.LevelRecord.level == 1))
    assert retry["passed_this_attempt"] is False
    assert retry["is_passed"] is True
    assert (record.best_score, record.latest_score, record.attempt_count) == (70, 30, 2)


def test_challenge_is_fixed_but_options_are_safe_to_shuffle():
    db = make_db(); seed(db)
    first = quiz.start_level(db, "u", 1)
    second = quiz.start_level(db, "u", 1)
    assert [q["id"] for q in first["questions"]] == [q["id"] for q in second["questions"]]
    for question in first["questions"]:
        stored = db.get(m.Question, question["id"])
        assert stored.correct_department_id in {o["department_id"] for o in question["options"]}


def test_practice_has_no_duplicates_and_prefers_unseen():
    db = make_db(); seed(db, practice_count=25)
    first = quiz.start_practice(db, "u")
    assert len({q["id"] for q in first["questions"]}) == 10
    finish(db, first, "u", 5)
    second = quiz.start_practice(db, "u")
    assert not ({q["id"] for q in first["questions"]} & {q["id"] for q in second["questions"]})


def test_practice_rolls_cycle_without_duplicates_in_session():
    db = make_db(); seed(db, challenge_levels=(), practice_count=12)
    first = quiz.start_practice(db, "u"); finish(db, first, "u", 10)
    second = quiz.start_practice(db, "u")
    assert len({q["id"] for q in second["questions"]}) == 10
    finish(db, second, "u", 10)
    third = quiz.start_practice(db, "u")
    assert third["practice_cycle"] == 2


def test_question_pools_are_isolated():
    db = make_db(); seed(db)
    challenge_ids = set(db.scalars(select(m.Question.id).where(m.Question.question_type == "challenge")))
    practice_ids = set(db.scalars(select(m.Question.id).where(m.Question.question_type == "practice")))
    assert challenge_ids.isdisjoint(practice_ids)
