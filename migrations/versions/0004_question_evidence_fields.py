"""store traceable question evidence and final selection

Revision ID: 0004_question_evidence_fields
Revises: 0003_department_aliases
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_question_evidence_fields"
down_revision = "0003_department_aliases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {x["name"] for x in inspector.get_columns("questions")}
    additions = {
        "reference_basis_title": sa.Column("reference_basis_title", sa.String(300)),
        "reference_basis_source": sa.Column("reference_basis_source", sa.String(100)),
        "reference_basis_excerpt": sa.Column("reference_basis_excerpt", sa.Text()),
        "reference_basis_locator": sa.Column("reference_basis_locator", sa.Text()),
        "reference_basis_reason": sa.Column("reference_basis_reason", sa.Text()),
        "final_selection": sa.Column("final_selection", sa.Boolean(), nullable=False, server_default=sa.false()),
    }
    for name, column in additions.items():
        if name not in columns:
            op.add_column("questions", column)


def downgrade() -> None:
    for name in ["final_selection", "reference_basis_reason", "reference_basis_locator",
                 "reference_basis_excerpt", "reference_basis_source", "reference_basis_title"]:
        op.drop_column("questions", name)
