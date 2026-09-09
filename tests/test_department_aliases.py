from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import models as m
from backend.db import Base
from backend.department_aliases import normalize_department_name, resolve_approved_department_alias


def test_only_approved_alias_resolves():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    department = m.Department(code="EDU", name="白云区教育局")
    db.add(department); db.flush()
    db.add(m.DepartmentAlias(raw_alias=" 广州市白云区教育局 ", normalized_alias=normalize_department_name(" 广州市白云区教育局 "),
                             department_id=department.id, department_scope="baiyun", department_type="district_department",
                             match_method="human_review", match_confidence=100, review_status="pending"))
    db.commit()
    assert resolve_approved_department_alias(db, "广州市白云区教育局") is None
    alias = db.query(m.DepartmentAlias).one(); alias.review_status = "approved"; db.commit()
    assert resolve_approved_department_alias(db, "广州市白云区教育局").id == department.id
