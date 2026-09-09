import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base


def new_id() -> str:
    return str(uuid.uuid4())


def now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("external_source", "external_user_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    external_source: Mapped[str | None] = mapped_column(String(80))
    external_user_id: Mapped[str | None] = mapped_column(String(120))
    display_name: Mapped[str] = mapped_column(String(100), default="训练用户")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class Department(Base):
    __tablename__ = "departments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class DepartmentAlias(Base):
    __tablename__ = "department_aliases"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    raw_alias: Mapped[str] = mapped_column(String(300))
    normalized_alias: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    department_id: Mapped[str] = mapped_column(ForeignKey("departments.id"), index=True)
    department_scope: Mapped[str] = mapped_column(String(30))
    department_type: Mapped[str] = mapped_column(String(40))
    match_method: Mapped[str] = mapped_column(String(80))
    match_confidence: Mapped[int] = mapped_column(Integer)
    review_status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    review_note: Mapped[str | None] = mapped_column(Text)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (UniqueConstraint("source_case_id", "question_type"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_case_id: Mapped[str] = mapped_column(String(100), index=True)
    case_origin: Mapped[str | None] = mapped_column(String(40), index=True)
    case_content: Mapped[str] = mapped_column(Text)
    correct_department_id: Mapped[str] = mapped_column(ForeignKey("departments.id"))
    explanation: Mapped[str] = mapped_column(Text)
    reference_basis: Mapped[str] = mapped_column(Text)
    reference_basis_title: Mapped[str | None] = mapped_column(String(300))
    reference_basis_source: Mapped[str | None] = mapped_column(String(100))
    reference_basis_excerpt: Mapped[str | None] = mapped_column(Text)
    reference_basis_locator: Mapped[str | None] = mapped_column(Text)
    reference_basis_reason: Mapped[str | None] = mapped_column(Text)
    question_type: Mapped[str] = mapped_column(String(20), index=True)
    difficulty_score: Mapped[int | None] = mapped_column(Integer)
    difficulty_dimension_1: Mapped[int | None] = mapped_column(Integer)
    difficulty_dimension_1_reason: Mapped[str | None] = mapped_column(String(300))
    difficulty_dimension_2: Mapped[int | None] = mapped_column(Integer)
    difficulty_dimension_2_reason: Mapped[str | None] = mapped_column(String(300))
    difficulty_dimension_3: Mapped[int | None] = mapped_column(Integer)
    difficulty_dimension_3_reason: Mapped[str | None] = mapped_column(String(300))
    difficulty_dimension_4: Mapped[int | None] = mapped_column(Integer)
    difficulty_dimension_4_reason: Mapped[str | None] = mapped_column(String(300))
    difficulty_dimension_5: Mapped[int | None] = mapped_column(Integer)
    difficulty_dimension_5_reason: Mapped[str | None] = mapped_column(String(300))
    review_status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    review_note: Mapped[str | None] = mapped_column(Text)
    reference_basis_status: Mapped[str] = mapped_column(String(30), default="needs_review")
    level: Mapped[int | None] = mapped_column(Integer, index=True)
    final_selection: Mapped[bool] = mapped_column(Boolean, default=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
    options: Mapped[list["QuestionOption"]] = relationship(cascade="all, delete-orphan")


class QuestionOption(Base):
    __tablename__ = "question_options"
    __table_args__ = (UniqueConstraint("question_id", "department_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"), index=True)
    department_id: Mapped[str] = mapped_column(ForeignKey("departments.id"))
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)


class UserProgress(Base):
    __tablename__ = "user_progress"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    highest_unlocked_level: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class LevelRecord(Base):
    __tablename__ = "level_records"
    __table_args__ = (UniqueConstraint("user_id", "level"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    level: Mapped[int] = mapped_column(Integer)
    is_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    best_score: Mapped[int] = mapped_column(Integer, default=0)
    latest_score: Mapped[int] = mapped_column(Integer, default=0)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class Attempt(Base):
    __tablename__ = "attempts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    mode: Mapped[str] = mapped_column(String(20), index=True)
    level: Mapped[int | None] = mapped_column(Integer)
    practice_cycle: Mapped[int | None] = mapped_column(Integer)
    score: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    total_count: Mapped[int] = mapped_column(Integer, default=10)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    questions: Mapped[list["AttemptQuestion"]] = relationship(cascade="all, delete-orphan")


class AttemptQuestion(Base):
    __tablename__ = "attempt_questions"
    __table_args__ = (UniqueConstraint("attempt_id", "question_id"), UniqueConstraint("attempt_id", "position"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("attempts.id"), index=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"))
    position: Mapped[int] = mapped_column(Integer)


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = (UniqueConstraint("attempt_id", "question_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("attempts.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"))
    selected_department_id: Mapped[str] = mapped_column(ForeignKey("departments.id"))
    correct_department_id: Mapped[str] = mapped_column(ForeignKey("departments.id"))
    is_correct: Mapped[bool] = mapped_column(Boolean)
    answered_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class PracticeQuestionProgress(Base):
    __tablename__ = "practice_question_progress"
    __table_args__ = (UniqueConstraint("user_id", "question_id", "cycle"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"), index=True)
    cycle: Mapped[int] = mapped_column(Integer)
    completed_count: Mapped[int] = mapped_column(Integer, default=1)
    last_answered_at: Mapped[datetime] = mapped_column(DateTime, default=now)
