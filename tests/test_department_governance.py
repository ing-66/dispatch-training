from types import SimpleNamespace

from scripts.department_governance import classify, in_scope_case


def test_baiyun_town_variants_share_canonical_department():
    first = classify("广州市白云区人民政府-人和镇", [])
    second = classify("白云区政府-人和镇", [])

    assert first["suggested_canonical_name"] == second["suggested_canonical_name"]
    assert first["department_scope"] == "baiyun"
    assert first["suggested_action"] == "candidate_new_department"


def test_known_public_service_aliases_are_grouped_but_location_is_required():
    short = classify("广州地铁集团", [])
    full = classify("广州地铁集团有限公司", [])

    assert short["suggested_canonical_name"] == full["suggested_canonical_name"]
    assert short["department_type"] == "public_service"
    assert in_scope_case(SimpleNamespace(case_content="白云区某地铁站设施故障"), short)[0]
    assert not in_scope_case(SimpleNamespace(case_content="某地铁站设施故障"), short)[0]


def test_other_district_and_ambiguous_city_unit_are_not_auto_accepted():
    other = classify("番禺区政府-洛浦街", [])
    ambiguous = classify("广州政务", [])

    assert other["department_scope"] == "other_district"
    assert other["suggested_action"] == "exclude_other_district"
    assert ambiguous["department_scope"] == "guangzhou_city"
    assert ambiguous["suggested_action"] == "needs_scope_review"
    assert not in_scope_case(SimpleNamespace(case_content="白云区事项"), ambiguous)[0]
