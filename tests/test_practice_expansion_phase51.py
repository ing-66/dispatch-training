from pathlib import Path

import pytest

from scripts.cross_district_transfer_assessment import target_pool
from scripts.practice_expansion_phase51 import (
    CITYWIDE_RULES,
    classify_citywide,
    classify_public,
    near_duplicate_groups,
)

ROOT = Path(__file__).resolve().parents[1]


def test_citywide_medical_insurance_is_detected_as_same_target():
    row = {
        "canonical_dispatch_target": "广州市医疗保障局",
        "case_title": "咨询广州医保定点问题",
        "case_content": "本人参加广州市职工医保，咨询医保定点医院变更和报销流程。",
    }
    key, rule = classify_citywide(row, CITYWIDE_RULES)
    assert key == "medical_insurance"
    assert rule["mapped_name"] == "广州市医疗保障局"
    assert rule["conflict_baiyun_key"] == ""


def test_citywide_human_resources_is_not_auto_allowed_as_same_target():
    row = {
        "canonical_dispatch_target": "广州市人力资源社会保障局",
        "case_title": "咨询社保卡问题",
        "case_content": "咨询新版电子社保卡如何申领。",
    }
    key, _ = classify_citywide(row, CITYWIDE_RULES)
    assert key is None  # Baiyun has its own HRSS department; the city/district boundary needs review.


def test_public_power_and_drainage_same_target_detected():
    power = {
        "canonical_dispatch_target": "广东电网有限责任公司广州供电局",
        "case_title": "反映供电服务问题",
        "case_content": "小区停电，请联系供电企业抢修并说明恢复时间。",
    }
    key, _ = classify_public(power, {
        "power": {"canonical_names": ("广东电网有限责任公司广州供电局",), "topic_terms": ("停电", "供电"),
                  "exclude_terms": ()}
    })
    assert key == "power"


def test_public_service_district_subsidiary_is_not_same_target():
    row = {
        "canonical_dispatch_target": "广州市增城排水有限公司",
        "case_title": "反映其他井盖问题",
        "case_content": "增城区某道路井盖破损需要维修。",
    }
    key, _ = classify_public(row, {})
    assert key is None


def test_pending_baiyun_targets_carry_authoritative_documents():
    pool = target_pool()
    for key in ("health", "culture_sports", "government_data"):
        assert pool[key]["approved"] == "pending"
        assert pool[key]["doc_section"]


def test_near_duplicate_clusters_are_detected_across_pools():
    rows = [
        {"source_case_id": "A", "case_content": "白云区某道路井盖破损，存在安全隐患，请尽快处理修复。", "mapped_dispatch_target": "广州市城市排水有限公司"},
        {"source_case_id": "B", "case_content": "白云区某道路井盖破损，存在安全隐患，请尽快处理修复。", "mapped_dispatch_target": "广州市城市排水有限公司"},
        {"source_case_id": "C", "case_content": "咨询幼儿园秋季招生与转学政策。", "mapped_dispatch_target": "广州市白云区教育局"},
    ]
    clusters = near_duplicate_groups(rows)
    assert len(clusters) == 1
    assert set(clusters[0]["source_case_ids"]) == {"A", "B"}


def test_three_pool_source_ids_are_unique_in_phase51_output():
    if not (ROOT / "artifacts/practice-expansion-phase51/combined_practice_candidates.json").is_file():
        pytest.skip("Phase 5.1 artifacts not generated")
    import json
    rows = json.loads((ROOT / "artifacts/practice-expansion-phase51/combined_practice_candidates.json").read_text(encoding="utf-8"))
    ids = [x["source_case_id"] for x in rows]
    assert len(ids) == len(set(ids))
    assert {x["case_origin"] for x in rows} <= {"baiyun_original", "cross_district_transfer",
                                                "citywide_same_target", "public_service_same_target"}
