"""Govern all historical dispatch-target names and assess case-source capacity.

This is a review-only pipeline. It never writes departments, aliases, questions,
or any other records to the training database.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.department_governance import (  # noqa: E402
    MUNICIPAL_ALIASES, OTHER_DISTRICTS, PUBLIC_SERVICE_GROUPS, canonical_code,
)
from scripts.question_builder import (  # noqa: E402
    DISPUTE_TERMS, MULTI_DEPARTMENT_PATTERN, collect_department_master, normalize,
    parse_original_files,
)

GENERIC_HANDLERS = {"广州政务"}
BAIYUN_GENERIC_HANDLERS = {"白云区政府", "广州市白云区政府", "白云区人民政府", "广州市白云区人民政府"}
VERTICAL_TERMS = ("分局", "税务局", "消防救援", "交警", "海关", "气象局")
PUBLIC_SERVICE_TERMS = ("供电", "地铁", "自来水", "排水", "公共交通", "公交集团", "燃气", "水务投资")
MUNICIPAL_PREFIXES = ("广州市", "市")
LOCATION_MARKERS = ("地址", "地点", "位于", "坐落", "路", "街", "巷", "村", "社区", "小区", "站")


def clean_name(raw: str) -> str:
    value = normalize(raw).strip("【】")
    value = re.sub(r"[，,]固定电话[:：]?\d+$", "", value)
    value = value.replace("街道办事处", "街").replace("街道办", "街").replace("街道", "街")
    value = value.replace("镇人民政府", "镇").replace("镇政府", "镇")
    return value


def canonical_baiyun_unit(unit: str) -> tuple[str, str]:
    unit = clean_name(unit).removeprefix("广州市").removeprefix("白云区政府-")
    unit = unit.removeprefix("白云区人民政府-")
    if unit.endswith("镇"):
        return f"广州市白云区人民政府-{unit}", "town"
    if unit.endswith("街"):
        return f"广州市白云区人民政府-{unit}", "subdistrict"
    if any(term in unit for term in VERTICAL_TERMS):
        return (unit if unit.startswith("白云区") else f"白云区{unit}"), "vertical_agency"
    if any(term in unit for term in PUBLIC_SERVICE_TERMS) or unit.endswith(("公司", "有限公司", "集团")):
        return unit, "public_service"
    return (f"广州市{unit}" if unit.startswith("白云区") else f"广州市白云区{unit}"), "district_department"


def build_known_local_units(names: list[str]) -> set[str]:
    units: set[str] = set()
    for raw in names:
        value = clean_name(raw)
        if "白云区" not in value:
            continue
        tail = value.split("-", 1)[-1]
        if tail.endswith(("街", "镇")):
            units.add(tail.removeprefix("白云区"))
    return units


def current_master_match(value: str, master: list[dict]) -> dict | None:
    variants = {normalize(value), normalize(value).removeprefix("广州市")}
    if "-" in value:
        tail = value.split("-", 1)[1]
        variants.update({normalize(tail), normalize("广州市" + tail)})
    matches = [x for x in master if normalize(x["department_name"]) in variants
               or normalize(x["department_name"]).removeprefix("广州市") in variants]
    return matches[0] if len(matches) == 1 else None


def classify_name(raw: str, master: list[dict], local_units: set[str]) -> dict:
    value = clean_name(raw)
    base = {
        "raw_department_name": raw, "normalized_name": value,
        "review_status": "pending", "review_note": "",
    }
    if not value:
        result = ("", "", "unknown", "other", "missing_name", 0.0, "needs_review")
    elif value in GENERIC_HANDLERS or value in BAIYUN_GENERIC_HANDLERS:
        result = (value, "", "guangzhou_city", "other", "exact_generic_handler", 1.0, "excluded_generic_handler")
    elif any(d in value for d in OTHER_DISTRICTS):
        result = (value, canonical_code(value), "other_district", "other", "district_prefix_rule", 0.99, "excluded_other_district")
    elif value in PUBLIC_SERVICE_GROUPS:
        canonical = PUBLIC_SERVICE_GROUPS[value]
        result = (canonical, canonical_code(canonical), "guangzhou_city", "public_service", "curated_alias_group", 0.98, "case_location_review")
    elif "白云区" in value:
        tail = value.split("-", 1)[1] if "-" in value else value.removeprefix("广州市白云区")
        canonical, org_type = canonical_baiyun_unit(tail)
        existing = current_master_match(canonical, master)
        if existing:
            canonical, code, action, method, confidence = existing["department_name"], existing["department_code"], "existing_dispatch_target_alias", "current_master_equivalence", 0.99
        else:
            code, action, method, confidence = canonical_code(canonical), "candidate_new_dispatch_target", "explicit_baiyun_name", 0.96
        result = (canonical, code, "baiyun", org_type, method, confidence, action)
    elif value in local_units:
        canonical, org_type = canonical_baiyun_unit(value)
        result = (canonical, canonical_code(canonical), "baiyun", org_type, "known_baiyun_unit_alias", 0.92, "candidate_alias_needs_review")
    elif value in MUNICIPAL_ALIASES:
        canonical = MUNICIPAL_ALIASES[value]
        result = (canonical, canonical_code(canonical), "guangzhou_city", "municipal_department", "curated_municipal_alias", 0.98, "conditional_municipal")
    elif any(term in value for term in PUBLIC_SERVICE_TERMS):
        result = (value, canonical_code(value), "guangzhou_city", "public_service", "service_keyword", 0.75, "case_location_review")
    else:
        existing = current_master_match(value, master)
        if existing:
            org_type = "subdistrict" if existing["department_kind"] == "street" and existing["department_name"].endswith("街") else "town" if existing["department_kind"] == "street" else "district_department"
            result = (existing["department_name"], existing["department_code"], "baiyun", org_type, "current_master_equivalence", 0.99, "existing_dispatch_target_alias")
        elif value.startswith(MUNICIPAL_PREFIXES) and not any(d in value for d in OTHER_DISTRICTS):
            result = (value, canonical_code(value), "guangzhou_city", "municipal_department", "municipal_name_pattern", 0.82, "conditional_municipal")
        else:
            result = ("", "", "unknown", "other", "unresolved", 0.0, "needs_review")
    keys = ("suggested_canonical_name", "suggested_department_code", "department_scope", "organization_type", "match_method", "match_confidence", "governance_status")
    return {**base, **dict(zip(keys, result))}


def location_scope(case, local_units: set[str]) -> tuple[str, str]:
    text = normalize(f"{case.title}\n{case.case_content}")
    has_baiyun = "白云区" in text
    other = [d for d in OTHER_DISTRICTS if d in text]
    if has_baiyun and not other:
        return "baiyun_confirmed", "题目标题或事项内容明确出现白云区"
    if has_baiyun and other:
        return "baiyun_probable", "同时出现白云区和其他行政区，需核实实际地点"
    if other:
        return "non_baiyun", "题目只出现广州其他行政区信号"
    hits = [unit for unit in local_units if unit in text]
    if hits:
        return "baiyun_probable", "出现已识别白云镇街名称，但没有明确白云区字样"
    return "unknown", "题目没有足够的白云区地点信号"


def complexity_status(case) -> tuple[str, str]:
    hits = [term for term in DISPUTE_TERMS if term in case.title or term in case.case_content]
    if hits:
        return "suspected_complex", "、".join(hits)
    return "clear", "未发现源数据可见的复杂或争议信号"


def assess_case(case, mapping: dict, local_units: set[str]) -> dict:
    location, location_reason = location_scope(case, local_units)
    complexity, complexity_reason = complexity_status(case)
    content_complete = bool(case.case_content and len(normalize(case.case_content)) >= 30)
    unique_handler = bool(case.actual_department_raw and not MULTI_DEPARTMENT_PATTERN.search(normalize(case.actual_department_raw)))
    status = mapping["governance_status"]
    exclusion = ""
    review = ""
    if status == "excluded_generic_handler": exclusion = "excluded_generic_handler"
    elif status == "excluded_other_district": exclusion = "excluded_other_district"
    elif mapping["department_scope"] == "unknown": exclusion = "unresolved_dispatch_target"
    elif not content_complete: exclusion = "case_content_missing_or_too_short"
    elif not unique_handler: exclusion = "multiple_dispatch_targets"
    elif complexity != "clear": exclusion = "suspected_complex_or_disputed"
    elif location == "baiyun_probable": review = "location_review"
    elif location in {"unknown", "non_baiyun"}: exclusion = "location_not_baiyun_confirmed"
    elif mapping["organization_type"] == "municipal_department": review = "conditional_municipal_case_review"
    eligible = not exclusion and not review
    return {
        "source_case_id": case.source_case_id, "source_file": case.source_file,
        "case_title": case.title, "case_content": case.case_content,
        "raw_department_name": case.actual_department_raw,
        "canonical_dispatch_target": mapping["suggested_canonical_name"],
        "dispatch_target_code": mapping["suggested_department_code"],
        "department_scope": mapping["department_scope"], "organization_type": mapping["organization_type"],
        "location_scope": location, "location_reason": location_reason,
        "content_complete": content_complete, "unique_handler": unique_handler,
        "complexity_status": complexity, "complexity_reason": complexity_reason,
        "case_status": "eligible" if eligible else ("needs_review" if review else "excluded"),
        "review_reason": review, "exclude_reason": exclusion,
        "review_status": "pending" if review else "not_required", "review_note": "",
    }


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    fields = list(rows[0])
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--asset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)

    cases = parse_original_files(args.source)
    master = collect_department_master(args.asset_root)
    counts = Counter(x.actual_department_raw for x in cases)
    local_units = build_known_local_units(list(counts))
    name_rows = []
    mappings = {}
    cumulative = 0
    for rank, (raw, count) in enumerate(counts.most_common(), 1):
        mapping = classify_name(raw, master, local_units)
        cumulative += count
        row = {"rank": rank, **mapping, "case_count": count,
               "cumulative_case_count": cumulative, "cumulative_coverage": cumulative / len(cases)}
        name_rows.append(row); mappings[raw] = mapping

    assessments = [assess_case(case, mappings[case.actual_department_raw], local_units) for case in cases]
    eligible = [x for x in assessments if x["case_status"] == "eligible"]
    municipal = [x for x in assessments if x["review_reason"] == "conditional_municipal_case_review"]
    unresolved = [x for x in name_rows if x["department_scope"] == "unknown"]
    public_candidates = [x for x in assessments if x["organization_type"] == "public_service"]
    new_baiyun = [x for x in name_rows if x["department_scope"] == "baiyun" and x["governance_status"] != "existing_dispatch_target_alias"]
    town_aliases = [x for x in name_rows if x["department_scope"] == "baiyun" and x["organization_type"] in {"subdistrict", "town"}]

    distribution_counts = Counter(x["canonical_dispatch_target"] for x in eligible)
    distribution = []
    running = 0
    for target, count in distribution_counts.most_common():
        running += count; share = count / len(eligible) if eligible else 0
        distribution.append({"canonical_dispatch_target": target, "eligible_case_count": count,
                             "share": share, "cumulative_share": running / len(eligible) if eligible else 0,
                             "concentration_flag": ">30%" if share > .3 else ">20%" if share > .2 else ">10%" if share > .1 else ""})
    name_scope_counts = Counter(x["department_scope"] for x in name_rows)
    name_status_counts = Counter(x["governance_status"] for x in name_rows)
    scope_case_counts = Counter()
    for x in name_rows: scope_case_counts[x["department_scope"]] += x["case_count"]
    type_eligible_counts = Counter(x["organization_type"] for x in eligible)
    exclusion_counts = Counter(x["exclude_reason"] for x in assessments if x["exclude_reason"])
    review_counts = Counter(x["review_reason"] for x in assessments if x["review_reason"])
    generic_names = [x for x in name_rows if x["governance_status"] == "excluded_generic_handler"]
    other_names = [x for x in name_rows if x["governance_status"] == "excluded_other_district"]
    recognizable = [x for x in assessments if x["department_scope"] != "unknown" and x["exclude_reason"] != "excluded_generic_handler"]
    allowed = [x for x in recognizable if x["department_scope"] == "baiyun" or x["organization_type"] in {"public_service", "municipal_department", "vertical_agency"}]
    located = [x for x in allowed if x["location_scope"] == "baiyun_confirmed"]
    unique = [x for x in located if x["unique_handler"]]
    complete = [x for x in unique if x["content_complete"]]
    clear = [x for x in complete if x["complexity_status"] == "clear"]
    canonical_stats = defaultdict(lambda: {"raw_names": set(), "case_count": 0})
    for row in name_rows:
        if row["suggested_canonical_name"]:
            key = (row["department_scope"], row["organization_type"], row["suggested_canonical_name"])
            canonical_stats[key]["raw_names"].add(row["raw_department_name"]); canonical_stats[key]["case_count"] += row["case_count"]
    target_type_summary = []
    for org_type in ("district_department", "subdistrict", "town", "vertical_agency", "public_service", "municipal_department"):
        groups = [(key, val) for key, val in canonical_stats.items() if key[1] == org_type and key[0] != "other_district"]
        target_type_summary.append({"organization_type": org_type, "canonical_target_count": len(groups),
                                    "raw_name_count": sum(len(v["raw_names"]) for _, v in groups),
                                    "source_case_count": sum(v["case_count"] for _, v in groups),
                                    "eligible_case_count": type_eligible_counts.get(org_type, 0)})
    capacity_band = "<600" if len(eligible) < 600 else "600-799" if len(eligible) < 800 else "800-999" if len(eligible) < 1000 else ">=1000"
    summary = {
        "raw_case_count": len(cases), "distinct_raw_department_names": len(name_rows),
        "current_master_count": len(master), "known_baiyun_local_units": sorted(local_units),
        "name_scope_counts": dict(name_scope_counts), "scope_case_counts": dict(scope_case_counts),
        "name_governance_status_counts": dict(name_status_counts),
        "other_district_name_count": len(other_names), "other_district_case_count": sum(x["case_count"] for x in other_names),
        "generic_handler_name_count": len(generic_names), "generic_handler_case_count": sum(x["case_count"] for x in generic_names),
        "eligible_count": len(eligible), "needs_review_count": sum(x["case_status"] == "needs_review" for x in assessments),
        "excluded_count": sum(x["case_status"] == "excluded" for x in assessments),
        "municipal_case_review_count": len(municipal), "public_service_candidate_count": len(public_candidates),
        "eligible_by_organization_type": dict(type_eligible_counts),
        "target_type_summary": target_type_summary,
        "funnel": {
            "raw_cases": len(assessments), "recognizable_dispatch_target": len(recognizable),
            "allowed_training_scope": len(allowed), "baiyun_location_confirmed": len(located),
            "unique_dispatch_target": len(unique), "content_complete": len(complete),
            "no_visible_complex_signal": len(clear), "strict_eligible": len(eligible),
        },
        "exclude_reasons": dict(exclusion_counts), "review_reasons": dict(review_counts),
        "capacity_band": capacity_band, "gap_to_600": max(0, 600-len(eligible)), "gap_to_800": max(0, 800-len(eligible)),
        "method_note": "严格eligible仅含地点明确为白云区、承办名称可规范化、单一承办、内容完整且未出现可见复杂争议信号的非市级案例；市级案例全部逐案待审。",
    }
    outputs = {
        "all_name_governance": name_rows, "case_assessments": assessments,
        "new_baiyun_targets": new_baiyun, "baiyun_town_aliases": town_aliases,
        "public_service_candidates": public_candidates, "municipal_case_candidates": municipal,
        "unknown_scope_candidates": unresolved, "eligible_sample": eligible[:100],
        "exclusion_reason_stats": [{"reason": k, "case_count": v} for k, v in exclusion_counts.most_common()] +
                                  [{"reason": k, "case_count": v} for k, v in review_counts.most_common()],
        "eligible_distribution": distribution,
    }
    write_json(args.output / "summary.json", summary)
    for name, rows in outputs.items():
        write_json(args.output / f"{name}.json", rows); write_csv(args.output / f"{name}.csv", rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
