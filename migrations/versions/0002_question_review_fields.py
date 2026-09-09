"""add question production review fields

Revision ID: 0002_question_review_fields
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_question_review_fields"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    existing_columns = {item["name"] for item in inspector.get_columns("questions")}
    for index in range(1, 6):
        score_name = f"difficulty_dimension_{index}"
        reason_name = f"difficulty_dimension_{index}_reason"
        if score_name not in existing_columns:
            op.add_column("questions", sa.Column(score_name, sa.Integer(), nullable=True))
        if reason_name not in existing_columns:
            op.add_column("questions", sa.Column(reason_name, sa.String(length=300), nullable=True))
    if "review_status" not in existing_columns:
        op.add_column("questions", sa.Column("review_status", sa.String(length=30), nullable=False, server_default="pending"))
    if "review_note" not in existing_columns:
        op.add_column("questions", sa.Column("review_note", sa.Text(), nullable=True))
    if "reference_basis_status" not in existing_columns:
        op.add_column("questions", sa.Column("reference_basis_status", sa.String(length=30), nullable=False, server_default="needs_review"))
    if "ix_questions_review_status" not in {item["name"] for item in inspector.get_indexes("questions")}:
        op.create_index("ix_questions_review_status", "questions", ["review_status"])


def downgrade():
    op.drop_index("ix_questions_review_status", table_name="questions")
    for name in ["reference_basis_status", "review_note", "review_status"]:
        op.drop_column("questions", name)
    for index in range(5, 0, -1):
        op.drop_column("questions", f"difficulty_dimension_{index}_reason")
        op.drop_column("questions", f"difficulty_dimension_{index}")
