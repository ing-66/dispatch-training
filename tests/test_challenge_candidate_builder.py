from scripts.challenge_candidate_builder import choose_distractors, dimension_scores, option_equivalence_key, select_balanced


def make_case(case_id: str, target: str, org_type: str = "subdistrict") -> dict:
    offset = sum(ord(char) for char in case_id) * 40
    unique_text = "".join(chr(0x4E00 + (offset + index) % 18000) for index in range(45))
    return {
        "source_case_id": case_id, "source_file": "test.md", "case_title": "反映设施问题",
        "case_content": f"事项发生在白云区，市民反映{target}辖区道路设施存在问题，希望有关单位处理。{unique_text}",
        "canonical_dispatch_target": target, "dispatch_target_code": f"DEPT-{case_id}",
        "organization_type": org_type, "case_status": "eligible",
    }


def test_balanced_selection_respects_per_target_cap():
    cases = [make_case(f"a{i}", "单位A") for i in range(5)] + [make_case(f"b{i}", "单位B") for i in range(5)]
    selected, _ = select_balanced(cases, count=6, per_target_cap=3)

    assert sum(x["canonical_dispatch_target"] == "单位A" for x in selected) == 3
    assert sum(x["canonical_dispatch_target"] == "单位B" for x in selected) == 3


def test_scores_have_five_components_and_match_total_range():
    scores, reasons = dimension_scores(make_case("1", "广州市白云区人民政府-人和镇", "town"))

    assert len(scores) == len(reasons) == 5
    assert all(0 <= score <= 20 for score in scores)
    assert 0 <= sum(scores) <= 100


def test_distractors_are_fixed_unique_real_targets():
    correct = make_case("1", "广州市白云区人民政府-人和镇", "town")
    targets = [correct] + [make_case(str(i), f"广州市白云区人民政府-测试街{i}") for i in range(2, 7)]
    wrong, _ = choose_distractors(correct, targets, tier=8)

    assert len(wrong) == 3
    assert len({x["canonical_dispatch_target"] for x in wrong}) == 3
    assert all(x["canonical_dispatch_target"] != correct["canonical_dispatch_target"] for x in wrong)
    assert len({option_equivalence_key(x["canonical_dispatch_target"]) for x in wrong}) == 3
