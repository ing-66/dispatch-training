"""Produce a review-only governance proposal for the top historical department names.

No database writes are performed. Suggested mappings remain pending until a
human reviews the generated CSV/XLSX artifact.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.question_builder import (
    DISPUTE_TERMS, collect_department_master, map_department, normalize, parse_original_files,
)


OTHER_DISTRICTS = ("增城区", "番禺区", "荔湾区", "黄埔区", "花都区", "天河区", "南沙区", "越秀区", "海珠区", "从化区")
PUBLIC_SERVICE_GROUPS = {
    "广州供电局有限公司": "广东电网有限责任公司广州供电局",
    "广东电网有限责任公司广州供电局": "广东电网有限责任公司广州供电局",
    "市排水公司": "广州市城市排水有限公司",
    "广州市城市排水有限公司": "广州市城市排水有限公司",
    "广州市公共交通集团有限公司": "广州市公共交通集团有限公司",
    "广州地铁集团": "广州地铁集团有限公司",
    "广州地铁集团有限公司": "广州地铁集团有限公司",
    "广州市自来水公司": "广州市自来水有限公司",
}
MUNICIPAL_ALIASES = {
    "市公安局": "广州市公安局", "广州市公安局": "广州市公安局",
    "市交通运输局": "广州市交通运输局", "广州市交通运输局": "广州市交通运输局",
    "市教育局": "广州市教育局", "市住房城乡建设局": "广州市住房和城乡建设局",
    "市林业园林局": "广州市林业和园林局", "广州市林业和园林局": "广州市林业和园林局",
    "市卫生健康委": "广州市卫生健康委员会", "市医保局": "广州市医疗保障局",
    "市规划和自然资源局": "广州市规划和自然资源局",
}


def canonical_code(name: str) -> str:
    return "DEPT-" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:16]


def normalized_name(raw: str) -> str:
    value = normalize(raw).rstrip("】")
    value = re.sub(r"[，,]固定电话[:：]?\d+$", "", value)
    value = value.replace("街道办事处", "街").replace("街道办", "街").replace("街道", "街")
    value = value.replace("镇人民政府", "镇").replace("镇政府", "镇")
    return value


def canonicalize_other_district(value: str) -> str:
    if not value.startswith("广州市"):
        value = "广州市" + value
    value = value.replace("区政府-", "区人民政府-")
    value = re.sub(r"区政府$", "区人民政府", value)
    direct_unit = re.match(r"^广州市(.+区)([^-]+(?:街|镇))$", value)
    if direct_unit:
        value = f"广州市{direct_unit.group(1)}人民政府-{direct_unit.group(2)}"
    return value


def classify(raw: str, current_master: list[dict]) -> dict:
    value = normalized_name(raw)
    current_by_name = {normalize(x["department_name"]): x for x in current_master}
    direct = current_by_name.get(normalize(value))
    if direct:
        canonical, method, confidence = direct["department_name"], "exact_current_master", 1.0
        scope = "baiyun"
        dtype = direct["department_kind"] == "street" and "subdistrict_or_town" or "district_department"
        action = "existing_department_alias"
    elif "白云区" in value and ("-" in value) and value.endswith(("街", "镇")):
        unit = value.split("-", 1)[1]
        canonical, method, confidence = f"广州市白云区人民政府-{unit}", "baiyun_prefix_and_unit_rule", 0.98
        scope, dtype, action = "baiyun", "subdistrict_or_town", "candidate_new_department"
    elif value in PUBLIC_SERVICE_GROUPS:
        canonical, method = PUBLIC_SERVICE_GROUPS[value], "curated_alias_group"
        confidence, scope, dtype, action = 0.98, "guangzhou_city", "public_service", "candidate_citywide_service"
    elif value == "广州政务":
        canonical, method, confidence = "广州政务", "exact_name_scope_uncertain", 0.65
        scope, dtype, action = "guangzhou_city", "other", "needs_scope_review"
    elif value in MUNICIPAL_ALIASES:
        canonical, method = MUNICIPAL_ALIASES[value], "curated_municipal_alias"
        confidence, scope, dtype, action = 0.98, "guangzhou_city", "municipal_department", "needs_scope_review"
    elif any(district in value for district in OTHER_DISTRICTS):
        canonical, method, confidence = canonicalize_other_district(value), "district_prefix_rule", 0.96
        scope = "other_district"
        dtype = "subdistrict_or_town" if value.endswith(("街", "镇")) else "district_department"
        action = "exclude_other_district"
    elif "白云区" in value:
        canonical, method, confidence = value.removeprefix("广州市"), "baiyun_name_normalization", 0.9
        scope, dtype, action = "baiyun", "district_department", "candidate_new_department"
    else:
        canonical, method, confidence = "", "unresolved", 0.0
        scope, dtype, action = "unknown", "other", "needs_review"
    existing = current_by_name.get(normalize(canonical))
    return {
        "raw_department_name": raw,
        "normalized_name": value,
        "suggested_canonical_name": canonical,
        "suggested_department_code": existing["department_code"] if existing else (canonical_code(canonical) if canonical else ""),
        "department_scope": scope,
        "department_type": dtype,
        "match_method": method,
        "match_confidence": confidence,
        "existing_department": "yes" if existing else "no",
        "suggested_action": action,
        "review_status": "pending",
        "review_note": "",
    }


def basic_case_quality(case) -> bool:
    return bool(case.case_content and len(normalize(case.case_content)) >= 30
                and case.actual_department_raw
                and not any(term in case.case_content or term in case.title for term in DISPUTE_TERMS))


def in_scope_case(case, mapping: dict) -> tuple[bool, str]:
    if mapping["department_scope"] == "baiyun":
        return True, "白云区单位"
    if mapping["department_type"] in {"vertical_agency", "public_service"}:
        if "白云区" in case.case_content:
            return True, "市域公共服务单位且题面含白云区地点信号"
        return False, "市域公共服务单位但题面缺少白云区地点信号"
    return False, "市级单位待确认" if mapping["department_scope"] == "guangzhou_city" else "其他区或范围未知"


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--asset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--top", type=int, default=50)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    cases = parse_original_files(args.source)
    frequencies = Counter(x.actual_department_raw for x in cases if x.actual_department_raw)
    master = collect_department_master(args.asset_root)
    ordered = frequencies.most_common()
    top_rows = []
    mapping_by_raw = {}
    cumulative = 0
    for rank, (raw, count) in enumerate(ordered[:args.top], 1):
        cumulative += count
        mapping = classify(raw, master)
        mapping.update({"rank": rank, "case_count": count, "cumulative_case_count": cumulative,
                        "cumulative_coverage": round(cumulative / len(cases), 4)})
        top_rows.append(mapping)
        mapping_by_raw[raw] = mapping

    baseline_ids = set()
    for case in cases:
        if not basic_case_quality(case):
            continue
        current, _ = map_department(case.actual_department_raw, master)
        if current:
            baseline_ids.add(case.source_case_id)

    projected_ids = set(baseline_ids)
    projection_rows = []
    for case in cases:
        mapping = mapping_by_raw.get(case.actual_department_raw)
        if not mapping or not basic_case_quality(case):
            continue
        accepted, reason = in_scope_case(case, mapping)
        if accepted:
            projected_ids.add(case.source_case_id)
            projection_rows.append({"source_case_id": case.source_case_id, "raw_department_name": case.actual_department_raw,
                                    "suggested_canonical_name": mapping["suggested_canonical_name"],
                                    "case_title": case.title, "scope_reason": reason,
                                    "complexity_status": "needs_review"})

    coverage = {str(n): sum(count for _, count in ordered[:n]) for n in (20, 50, 100)}
    all_frequency_rows = []
    cumulative_all = 0
    for rank, (raw, count) in enumerate(ordered, 1):
        cumulative_all += count
        all_frequency_rows.append({"rank": rank, "raw_department_name": raw, "case_count": count,
                                   "cumulative_case_count": cumulative_all,
                                   "cumulative_coverage": round(cumulative_all / len(cases), 4),
                                   "governance_status": "processed_top50" if rank <= args.top else "not_processed"})
    summary = {
        "raw_case_count": len(cases), "distinct_department_names": len(frequencies),
        "top_coverage_counts": coverage,
        "top_coverage_rates": {key: round(value / len(cases), 4) for key, value in coverage.items()},
        "current_master_count": len(master),
        "top50_unique_canonical_suggestions": len({x["suggested_canonical_name"] for x in top_rows if x["suggested_canonical_name"]}),
        "top50_scope_case_counts": dict(Counter(x["department_scope"] for x in top_rows for _ in range(x["case_count"]))),
        "top50_scope_name_counts": dict(Counter(x["department_scope"] for x in top_rows)),
        "top50_type_case_counts": dict(Counter(x["department_type"] for x in top_rows for _ in range(x["case_count"]))),
        "top50_type_name_counts": dict(Counter(x["department_type"] for x in top_rows)),
        "top50_existing_alias_name_count": sum(x["existing_department"] == "yes" for x in top_rows),
        "baseline_questionable_pool": len(baseline_ids),
        "projected_pool_if_safe_top50_approved": len(projected_ids),
        "projected_increment": len(projected_ids - baseline_ids),
        "projection_note": "只计白云区单位，以及题面明确含白云区地点信号的公共服务单位；市级部门仍待人工确认。",
    }
    write_csv(args.output / "top50_department_governance.csv", top_rows)
    write_csv(args.output / "all_department_frequency.csv", all_frequency_rows)
    write_csv(args.output / "projected_in_scope_cases.csv", projection_rows)
    (args.output / "top50_department_governance.json").write_text(json.dumps(top_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output / "all_department_frequency.json").write_text(json.dumps(all_frequency_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output / "projected_in_scope_cases.json").write_text(json.dumps(projection_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
