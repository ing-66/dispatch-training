from scripts.challenge_finalization import canonical_name, normalize_options, recalibrate_levels, retrieve_evidence


def test_authoritative_aliases_consolidate_department_names():
    assert canonical_name("广州市白云区住房建设和交通局") == "广州市白云区住房建设交通局"
    assert canonical_name("白云区公安分局") == "广州市公安局白云区分局"


def test_evidence_status_requires_direct_topic_overlap():
    docs = [{"title": "职责", "source": "机构职责", "path": "duty.md", "locator": "段落1",
             "text": "负责学校招生和教育管理。", "topics": {"学校", "招生", "教育"}}]
    verified = retrieve_evidence({"case_title": "学校招生问题", "core_issue": "教育", "case_content": ""}, docs)
    pending = retrieve_evidence({"case_title": "道路积水", "core_issue": "排水", "case_content": ""}, docs)
    insufficient = retrieve_evidence({"case_title": "道路积水", "core_issue": "排水", "case_content": ""}, [])

    assert verified["reference_basis_status"] == "verified" and verified["reference_basis_excerpt"]
    assert pending["reference_basis_status"] == "needs_review" and not pending["reference_basis_excerpt"]
    assert insufficient["reference_basis_status"] == "insufficient"


def test_normalized_options_are_four_distinct_real_targets():
    candidate = {"source_case_id": "x", "correct_department_name": "白云区教育局",
                 "organization_type": "district_department", "wrong_department_1": "白云区教育局",
                 "wrong_department_2": "单位B", "wrong_department_3": "单位B"}
    pool = [{"name": "广州市白云区教育局", "organization_type": "district_department"},
            {"name": "单位B", "organization_type": "other"}, {"name": "单位C", "organization_type": "other"},
            {"name": "单位D", "organization_type": "other"}, {"name": "单位E", "organization_type": "other"}]
    candidate["correct_department_name"] = canonical_name(candidate["correct_department_name"])
    normalize_options(candidate, pool)
    names = [candidate["correct_department_name"]] + [candidate[f"wrong_department_{i}"] for i in range(1, 4)]
    assert len(set(names)) == 4 and set(names) <= {x["name"] for x in pool}


def test_recalibration_uses_relative_distribution_not_ten_point_bands():
    rows = []
    for index in range(20):
        rows.append({"source_case_id": str(index), "correct_department_name": "单位A", "organization_type": "other",
                     "wrong_department_1": "单位B", "wrong_department_2": "单位C", "wrong_department_3": "单位D",
                     "difficulty_score": 40 + index, "difficulty_dimension_1": 5 + index % 5,
                     "difficulty_dimension_3": 6 + index % 7, "case_content": "普通事项", "suggested_level": 1})
    recalibrate_levels(rows)
    assert min(x["suggested_level"] for x in rows) == 1
    assert max(x["suggested_level"] for x in rows) == 10
    assert all("level_fit_score" in x and "level_fit_review" in x for x in rows)
