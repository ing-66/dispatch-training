from types import SimpleNamespace

from scripts.department_governance_full import (
    assess_case, build_known_local_units, classify_name, location_scope,
)


def test_all_governance_excludes_generic_and_other_district():
    local = build_known_local_units(["白云区政府-人和镇"])

    assert classify_name("广州政务", [], local)["governance_status"] == "excluded_generic_handler"
    assert classify_name("白云区政府", [], local)["governance_status"] == "excluded_generic_handler"
    assert classify_name("番禺区政府-洛浦街", [], local)["governance_status"] == "excluded_other_district"


def test_explicit_baiyun_town_builds_safe_alias_and_location_is_conservative():
    local = build_known_local_units(["广州市白云区人民政府-人和镇"])
    mapped = classify_name("人和镇", [], local)

    assert mapped["suggested_canonical_name"] == "广州市白云区人民政府-人和镇"
    assert mapped["organization_type"] == "town"
    assert location_scope(SimpleNamespace(title="咨询", case_content="事项发生在白云区人和镇"), local)[0] == "baiyun_confirmed"
    assert location_scope(SimpleNamespace(title="咨询", case_content="事项发生在人和镇"), local)[0] == "baiyun_probable"


def test_municipal_case_requires_human_review_even_with_confirmed_location():
    case = SimpleNamespace(
        source_case_id="HC-test", source_file="test.md", title="咨询事项",
        case_content="该事项发生在白云区，历史记录包含足够完整的事项描述用于测试。",
        actual_department_raw="市交通运输局",
    )
    mapping = classify_name("市交通运输局", [], set())
    result = assess_case(case, mapping, set())

    assert result["location_scope"] == "baiyun_confirmed"
    assert result["case_status"] == "needs_review"
    assert result["review_reason"] == "conditional_municipal_case_review"
