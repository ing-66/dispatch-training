"""add question case_origin for provenance display

Revision ID: 0005_question_case_origin
Revises: 0004_question_evidence_fields
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_question_case_origin"
down_revision = "0004_question_evidence_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {x["name"] for x in inspector.get_columns("questions")}
    if "case_origin" not in columns:
        op.add_column("questions", sa.Column("case_origin", sa.String(40), nullable=True))


def downgrade() -> None:
    op.drop_column("questions", "case_origin")
