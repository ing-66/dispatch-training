"""add approved department alias layer

Revision ID: 0003_department_aliases
Revises: 0002_question_review_fields
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_department_aliases"
down_revision = "0002_question_review_fields"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if "department_aliases" in inspector.get_table_names():
        return
    op.create_table(
        "department_aliases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("raw_alias", sa.String(300), nullable=False),
        sa.Column("normalized_alias", sa.String(300), nullable=False),
        sa.Column("department_id", sa.String(36), sa.ForeignKey("departments.id"), nullable=False),
        sa.Column("department_scope", sa.String(30), nullable=False),
        sa.Column("department_type", sa.String(40), nullable=False),
        sa.Column("match_method", sa.String(80), nullable=False),
        sa.Column("match_confidence", sa.Integer(), nullable=False),
        sa.Column("review_status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("review_note", sa.Text()),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("normalized_alias"),
    )
    op.create_index("ix_department_aliases_normalized_alias", "department_aliases", ["normalized_alias"], unique=True)
    op.create_index("ix_department_aliases_department_id", "department_aliases", ["department_id"])
    op.create_index("ix_department_aliases_review_status", "department_aliases", ["review_status"])


def downgrade():
    op.drop_table("department_aliases")
