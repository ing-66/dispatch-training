"""Normalize and assess a new practice source without generating questions."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FIELD_ALIASES = {
    "source_case_id": ("工单编号", "工单id", "工单ID", "流水号", "受理编号", "case_id", "caseid"),
    "case_title": ("诉求标题", "事项标题", "工单标题", "标题", "case_title"),
    "case_content": ("事项内容", "诉求内容", "问题描述", "来电内容", "工单内容", "case_content"),
    "case_type": ("诉求类型", "工单类型", "事项类型", "case_type"),
    "created_at": ("留言时间", "受理时间", "创建时间", "来电时间", "created_at"),
    "district": ("所属区", "行政区", "区域", "district"),
    "subdistrict": ("街道", "镇街", "属地", "subdistrict"),
    "address": ("事发地址", "发生地址", "地址", "address"),
    "raw_dispatch_target": ("最终承办单位", "承办单位", "办理单位", "责任单位", "处理部门", "actual_dispatch_target"),
    "main_target": ("主办单位", "主办部门"), "co_targets": ("协办单位", "协办部门"),
    "transfer_targets": ("转派单位", "转派部门"), "completion_target": ("办结单位", "最终办理单位"),
    "process": ("办理过程", "处理过程", "转派记录", "退单记录"),
}
BAIYUN_SUBDISTRICTS = {"三元里街", "松洲街", "景泰街", "同德街", "黄石街", "棠景街", "新市街", "同和街", "京溪街", "永平街", "嘉禾街", "均禾街", "石井街", "金沙街", "云城街", "鹤龙街", "白云湖街", "石门街", "龙归街", "大源街", "人和镇", "江高镇", "太和镇", "钟落潭镇"}
OTHER_DISTRICTS = {"越秀区", "海珠区", "荔湾区", "天河区", "黄埔区", "番禺区", "花都区", "南沙区", "从化区", "增城区"}
MULTI_SPLIT = re.compile(r"[、,，;；/|+]+")
COMPLEX_WORDS = ("主办", "协办", "转派", "退单", "共同办理", "联合办理", "责任不明", "存在争议")


def norm_header(value: Any) -> str:
    return re.sub(r"[\s_\-（）()]+", "", str(value)).lower()


def read_source(path: Path) -> tuple[list[dict], list[str], str]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        for encoding in ("utf-8-sig", "gb18030"):
            try: frame = pd.read_csv(path, dtype=object, encoding=encoding); break
            except UnicodeDecodeError: continue
        else: raise ValueError("CSV编码无法识别")
        sheet = "csv"
    elif suffix in {".xlsx", ".xls"}:
        try: frame = pd.read_excel(path, dtype=object)
        except ImportError as exc: raise RuntimeError("读取.xls需要项目可选依赖xlrd") from exc
        sheet = "first_sheet"
    elif suffix == ".json":
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(raw, dict):
            raw = next((raw[k] for k in ("records", "data", "items", "cases") if isinstance(raw.get(k), list)), [raw])
        if not isinstance(raw, list): raise ValueError("JSON根节点必须是数组或包含records/data/items/cases数组")
        frame = pd.DataFrame(raw); sheet = "json"
    else: raise ValueError("仅支持.xlsx/.xls/.csv/.json")
    frame = frame.where(pd.notna(frame), None)
    return frame.to_dict(orient="records"), [str(x) for x in frame.columns], sheet


def suggest_mapping(headers: list[str]) -> dict[str, dict]:
    result = {}
    normalized = {norm_header(h): h for h in headers}
    for target, aliases in FIELD_ALIASES.items():
        exact = next((normalized[norm_header(alias)] for alias in aliases if norm_header(alias) in normalized), None)
        result[target] = {"source_field": exact, "match_method": "exact_alias" if exact else "unmapped", "confidence": 1.0 if exact else 0.0, "review_status": "pending"}
    return result


def text(value: Any) -> str:
    if value is None: return ""
    try:
        if pd.isna(value): return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def json_value(value: Any) -> Any:
    if value is None: return None
    try:
        if pd.isna(value): return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (str, int, float, bool)): return value
    if isinstance(value, dict): return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [json_value(v) for v in value]
    return str(value)


def stable_id(dataset: str, source_file: str, content: str, target: str, created: str) -> str:
    value = "\x1f".join((dataset, source_file, content, target, created))
    return "NEW-" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def trigrams(value: str) -> set[str]:
    cleaned = re.sub(r"\s+", "", value)
    return {cleaned[i:i+3] for i in range(max(0, len(cleaned)-2))}


def similarity(a: str, b: str) -> float:
    left, right = trigrams(a), trigrams(b)
    return len(left & right) / len(left | right) if left and right else 0.0


def scope_of(district: str, subdistrict: str, address: str, content: str) -> tuple[str, str]:
    combined = district + address
    if "白云区" in district: return "baiyun_confirmed", "源数据district明确为白云区"
    if subdistrict in BAIYUN_SUBDISTRICTS: return "baiyun_confirmed", "结构化镇街属于白云区"
    if "白云区" in combined: return "baiyun_confirmed", "结构化地址明确包含白云区"
    if any(name in district or name in address for name in OTHER_DISTRICTS): return "non_baiyun", "结构化区域或地址明确属于广州其他区"
    mentioned = [name for name in BAIYUN_SUBDISTRICTS if name in content or name in address]
    if mentioned: return "baiyun_probable", f"文本出现白云区镇街线索：{mentioned[0]}"
    return "unknown", "缺少足够明确的白云区结构化或文本地点证据"


def load_registry(assessments_path: Path) -> tuple[dict[str, tuple[str, str]], set[str]]:
    rows = json.loads(assessments_path.read_text(encoding="utf-8"))
    eligible = [x for x in rows if x["case_status"] == "eligible"]
    aliases = {x["raw_department_name"]: (x["dispatch_target_code"], x["canonical_dispatch_target"]) for x in eligible}
    canonical = {x["canonical_dispatch_target"]: (x["dispatch_target_code"], x["canonical_dispatch_target"]) for x in eligible}
    return {**aliases, **canonical}, {x["source_case_id"] for x in eligible}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path); parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--output-root", type=Path, default=Path("artifacts/practice-source-ingest"))
    parser.add_argument("--challenge-ids", type=Path, default=Path("artifacts/practice-source-assessment/challenge_source_ids.json"))
    parser.add_argument("--challenge-questions", type=Path, default=Path("artifacts/challenge-v1/challenge_questions_v1_approved.json"))
    parser.add_argument("--case-assessments", type=Path, default=Path("artifacts/department-governance-full/case_assessments.json"))
    parser.add_argument("--build-workbook", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    if not args.source.is_file(): raise SystemExit("源文件不存在")
    out = args.output_root / args.dataset_id; out.mkdir(parents=True, exist_ok=True)
    rows, headers, sheet = read_source(args.source); mapping = suggest_mapping(headers)
    registry, existing_eligible_ids = load_registry(args.case_assessments)
    challenge_ids = set(json.loads(args.challenge_ids.read_text(encoding="utf-8")))
    existing_rows = json.loads(args.case_assessments.read_text(encoding="utf-8"))
    existing_practice = [x for x in existing_rows if x["case_status"] == "eligible" and x["source_case_id"] not in challenge_ids]
    challenge_questions = json.loads(args.challenge_questions.read_text(encoding="utf-8"))
    challenge_contents = [(x["source_case_id"], x["case_content"]) for x in challenge_questions]
    used_fields = {v["source_field"] for v in mapping.values() if v["source_field"]}
    normalized, dept_suggestions = [], {}
    seen_ids, seen_fingerprints = set(), set()
    for index, raw in enumerate(rows, 2):
        get = lambda field: text(raw.get(mapping[field]["source_field"])) if mapping[field]["source_field"] else ""
        content, target, created = get("case_content"), get("raw_dispatch_target"), get("created_at")
        source_id = get("source_case_id") or stable_id(args.dataset_id, args.source.name, content, target, created)
        district, subdistrict, address = get("district"), get("subdistrict"), get("address")
        scope, scope_reason = scope_of(district, subdistrict, address, content)
        targets = [x.strip() for x in MULTI_SPLIT.split(target) if x.strip()]
        extra_targets = [get(x) for x in ("main_target", "co_targets", "transfer_targets", "completion_target") if get(x)]
        multi = len(set(targets)) != 1 or bool(get("co_targets")) or len(set(extra_targets)) > 1
        resolved = registry.get(target)
        if not resolved and target:
            dept_suggestions.setdefault(target, {"raw_dispatch_target": target, "suggested_canonical_target": "", "match_method": "unmatched_new_name", "match_confidence": 0.0, "review_status": "pending", "review_note": ""})
        best_challenge_id, best_similarity = "", 0.0
        for challenge_id, challenge_content in challenge_contents:
            score = similarity(content, challenge_content)
            if score > best_similarity: best_challenge_id, best_similarity = challenge_id, score
        fingerprint = hashlib.sha256(re.sub(r"\s+", "", content).encode("utf-8")).hexdigest() if content else ""
        duplicate_in_dataset = source_id in seen_ids or (fingerprint and fingerprint in seen_fingerprints)
        seen_ids.add(source_id); seen_fingerprints.add(fingerprint)
        exact_challenge = source_id in challenge_ids
        near_challenge = best_similarity >= 0.86
        best_existing_id, best_existing_similarity = "", 0.0
        for existing in existing_practice:
            score = similarity(content, existing["case_content"])
            if score > best_existing_similarity: best_existing_id, best_existing_similarity = existing["source_case_id"], score
        existing_id_duplicate = source_id in existing_eligible_ids
        existing_content_duplicate = best_existing_similarity >= 0.86
        complex_signal = multi or any(word in content + get("process") for word in COMPLEX_WORDS)
        reasons = []
        if scope != "baiyun_confirmed": reasons.append(scope)
        if len(content) < 20: reasons.append("case_content_missing_or_too_short")
        if not target: reasons.append("dispatch_target_missing")
        if multi: reasons.append("multiple_dispatch_targets")
        if not resolved: reasons.append("canonical_target_not_approved")
        if exact_challenge: reasons.append("challenge_source_id_duplicate")
        elif near_challenge: reasons.append("challenge_content_near_duplicate_review")
        if existing_id_duplicate: reasons.append("existing_practice_source_id_duplicate")
        elif existing_content_duplicate: reasons.append("existing_practice_content_near_duplicate_review")
        if duplicate_in_dataset: reasons.append("source_dataset_duplicate")
        if complex_signal: reasons.append("complexity_signal")
        eligible = not reasons
        normalized.append({
            "source_dataset_id": args.dataset_id, "source_file": args.source.name, "source_row": index,
            "source_case_id": source_id, "case_title": get("case_title"), "case_content": content,
            "case_type": get("case_type"), "created_at": created, "district": district, "subdistrict": subdistrict, "address": address,
            "raw_dispatch_target": target, "canonical_dispatch_target_id": resolved[0] if resolved else "",
            "canonical_dispatch_target_name": resolved[1] if resolved else "", "dispatch_target_count": len(set(targets)),
            "has_unique_dispatch_target": not multi and len(set(targets)) == 1, "source_extra_fields": {k: json_value(v) for k, v in raw.items() if k not in used_fields},
            "baiyun_scope": scope, "scope_reason": scope_reason, "match_method": "approved_alias_or_exact" if resolved else "unmatched_new_name",
            "match_confidence": 1.0 if resolved else 0.0, "department_review_status": "approved" if resolved else "pending",
            "challenge_duplicate": exact_challenge, "challenge_near_duplicate": near_challenge, "nearest_challenge_source_id": best_challenge_id,
            "challenge_content_similarity": round(best_similarity, 3), "duplicate_in_source": duplicate_in_dataset,
            "existing_practice_duplicate": existing_id_duplicate, "existing_practice_near_duplicate": existing_content_duplicate,
            "nearest_existing_practice_source_id": best_existing_id, "existing_practice_content_similarity": round(best_existing_similarity, 3),
            "complexity_status": "needs_review" if complex_signal else "clear", "strict_practice_eligible": eligible,
            "exclude_reasons": reasons, "review_status": "pending", "review_note": "",
        })
    dates = [pd.to_datetime(x["created_at"], errors="coerce") for x in normalized if x["created_at"]]
    dates = [x for x in dates if not pd.isna(x)]
    profile = {"source_dataset_id": args.dataset_id, "source_file": str(args.source.resolve()), "source_format": args.source.suffix.lower(),
               "source_sheet": sheet, "record_count": len(rows), "fields": headers,
               "null_counts": {h: sum(text(row.get(h)) == "" for row in rows) for h in headers},
               "duplicate_records": sum(x["duplicate_in_source"] for x in normalized),
               "records_with_case_id": sum(bool((mapping["source_case_id"]["source_field"] and text(row.get(mapping["source_case_id"]["source_field"])))) for row in rows),
               "complete_content_records": sum(len(x["case_content"]) >= 20 for x in normalized),
               "records_with_region_field": sum(bool(x["district"] or x["subdistrict"] or x["address"]) for x in normalized),
               "baiyun_confirmed_records": sum(x["baiyun_scope"] == "baiyun_confirmed" for x in normalized),
               "records_with_dispatch_target": sum(bool(x["raw_dispatch_target"]) for x in normalized),
               "unique_dispatch_target_names": len({x["raw_dispatch_target"] for x in normalized if x["raw_dispatch_target"]}),
               "suspected_multi_handler_records": sum(not x["has_unique_dispatch_target"] for x in normalized),
               "created_at_min": min(dates).isoformat() if dates else "", "created_at_max": max(dates).isoformat() if dates else ""}
    new_eligible = [x for x in normalized if x["strict_practice_eligible"]]
    assessment = {"source_dataset_id": args.dataset_id, "new_records": len(normalized), "new_strict_practice_eligible": len(new_eligible),
                  "existing_strict_practice_eligible": len(existing_eligible_ids - challenge_ids),
                  "cross_dataset_exact_duplicates": sum(x["existing_practice_duplicate"] for x in normalized),
                  "cross_dataset_near_duplicate_signals": sum(x["existing_practice_near_duplicate"] for x in normalized),
                  "current_total_practice_capacity": len(existing_eligible_ids - challenge_ids) + len(new_eligible),
                  "gap_to_500": 0, "gap_to_650": 0, "gap_to_800": 0,
                  "scope_counts": dict(Counter(x["baiyun_scope"] for x in normalized)),
                  "exclusion_reason_counts": dict(Counter(reason for x in normalized for reason in x["exclude_reasons"]))}
    for target in (500, 650, 800): assessment[f"gap_to_{target}"] = max(0, target-assessment["current_total_practice_capacity"])
    (out / "raw_profile.json").write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "field_mapping.json").write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "normalized_cases.json").write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "eligible_cases.json").write_text(json.dumps(new_eligible, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "department_mapping_suggestions.json").write_text(json.dumps(list(dept_suggestions.values()), ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "assessment.json").write_text(json.dumps(assessment, ensure_ascii=False, indent=2), encoding="utf-8")
    excluded = [x for x in normalized if not x["strict_practice_eligible"]]
    fields = ["source_case_id", "source_row", "case_title", "case_content", "raw_dispatch_target", "baiyun_scope", "exclude_reasons", "review_status", "review_note"]
    with (out / "excluded_cases.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore"); writer.writeheader()
        for row in excluded: writer.writerow({**row, "exclude_reasons": "|".join(row["exclude_reasons"])})
    if args.build_workbook:
        runtime = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies"
        node, modules = runtime / "node" / "bin" / "node.exe", runtime / "node" / "node_modules"
        if not node.exists() or not modules.exists(): raise SystemExit("审核Excel生成环境不可用；JSON/CSV结果已保留")
        temp = out / ".workbook-runtime"; temp.mkdir(exist_ok=True)
        link = temp / "node_modules"
        link_path = str(link.absolute())
        if not link.exists():
            subprocess.run(["powershell", "-NoProfile", "-Command",
                            f"New-Item -ItemType Junction -Path '{link_path}' -Target '{modules}' | Out-Null"], check=True)
        builder = Path(__file__).with_name("build_practice_ingest_workbooks.mjs")
        temp_builder = temp / builder.name; shutil.copy2(builder, temp_builder)
        subprocess.run([node, temp_builder, "review", out, out / "practice_source_review.xlsx"], check=True)
        if not link.is_junction(): raise RuntimeError("临时node_modules不是预期的目录联接")
        os.rmdir(link_path)
        temp_builder.unlink(missing_ok=True); temp.rmdir()
    print(json.dumps(assessment, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
