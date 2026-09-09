"""Approved-only historical department alias resolution."""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend import models as m


def normalize_department_name(value: str) -> str:
    return re.sub(r"\s+", "", value or "").strip().rstrip("】")


def resolve_approved_department_alias(db: Session, raw_name: str) -> m.Department | None:
    normalized = normalize_department_name(raw_name)
    alias = db.scalar(select(m.DepartmentAlias).where(
        m.DepartmentAlias.normalized_alias == normalized,
        m.DepartmentAlias.review_status == "approved",
        m.DepartmentAlias.is_enabled.is_(True),
    ))
    if not alias:
        return None
    department = db.get(m.Department, alias.department_id)
    return department if department and department.is_enabled else None
