"""Assess only known Phase 4 historical-case sources; never generate questions."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""): digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    original = args.assets / "knowledge-original" / "C. 历史案例库" / "官方工单案例"
    split = args.assets / "knowledge-source" / "03_历史工单案例"
    legacy = args.assets / "legacy-review" / "旧知识资料待复核" / "C. 历史案例库" / "官方工单案例"
    assessments_path = args.artifacts / "department-governance-full" / "case_assessments.json"
    approved_path = args.artifacts / "challenge-v1" / "challenge_questions_v1_approved.json"
    assessments = json.loads(assessments_path.read_text(encoding="utf-8"))
    approved = json.loads(approved_path.read_text(encoding="utf-8"))
    challenge_ids = {x["source_case_id"] for x in approved}
    eligible = [x for x in assessments if x["case_status"] == "eligible"]
    remaining = [x for x in eligible if x["source_case_id"] not in challenge_ids]
    file_counts = {p.name: sum(1 for line in p.read_text(encoding="utf-8").splitlines() if line.startswith("## ")) for p in original.glob("*.md")}
    generic_handler_names = {"广州政务", "广州政府", "白云区政府"}
    specific_handler_count = len(assessments) - sum(x["raw_department_name"] in generic_handler_names for x in assessments)
    source_rows = [
        {"source_name": "原始官方工单Markdown（5文件）", "path": str(original), "format": "Markdown",
         "record_count": len(assessments), "baiyun_records": sum(x["location_scope"] in {"baiyun_confirmed", "baiyun_probable"} for x in assessments),
         "explicit_handler_records": specific_handler_count,
         "unique_handler_records": sum(x["unique_handler"] for x in assessments), "complete_content_records": sum(x["content_complete"] for x in assessments),
         "mappable_handler_records": 3610, "challenge_duplicate_records": len(challenge_ids),
         "estimated_strict_practice_eligible": len(remaining), "independent_new_records": 0,
         "field_structure": "标题/诉求类型/留言时间/事项内容/实际承办单位；无原始工单编号、独立区域字段、办理链路",
         "assessment": "当前唯一原始案例源"},
        {"source_name": "knowledge-source历史工单拆分", "path": str(split), "format": "Markdown（逐案拆分）",
         "record_count": sum(1 for _ in split.rglob("*.md")), "baiyun_records": 477, "explicit_handler_records": specific_handler_count,
         "unique_handler_records": 5133, "complete_content_records": 4916, "mappable_handler_records": 3610,
         "challenge_duplicate_records": 100, "estimated_strict_practice_eligible": 218, "independent_new_records": 0,
         "field_structure": "与原5文件相同，仅按二级标题拆分", "assessment": "处理产物，不是上游数据；无新增字段"},
        {"source_name": "legacy-review归档副本", "path": str(legacy), "format": "Markdown",
         "record_count": sum(file_counts.values()), "baiyun_records": 477, "explicit_handler_records": specific_handler_count,
         "unique_handler_records": 5133, "complete_content_records": 4916, "mappable_handler_records": 3610,
         "challenge_duplicate_records": 100, "estimated_strict_practice_eligible": 218, "independent_new_records": 0,
         "field_structure": "与原5文件逐字节相同", "assessment": "归档副本，不是新数据"},
        {"source_name": "department-governance-full派生评估", "path": str(assessments_path), "format": "JSON",
         "record_count": len(assessments), "baiyun_records": 477, "explicit_handler_records": specific_handler_count,
         "unique_handler_records": 5133, "complete_content_records": 4916, "mappable_handler_records": 3610,
         "challenge_duplicate_records": 100, "estimated_strict_practice_eligible": 218, "independent_new_records": 0,
         "field_structure": "source_case_id/source_file/case_title/case_content/raw与canonical承办单位/范围/完整性/复杂度/筛选状态",
         "assessment": "项目派生治理结果，不是新历史工单"},
    ]
    hashes = [{"file": str(p), "sha256": sha256(p), "records": file_counts[p.name],
               "legacy_identical": sha256(p) == sha256(legacy / p.name)} for p in sorted(original.glob("*.md"))]
    generic = [x for x in assessments if x["raw_department_name"] == "广州政务"]
    summary = {
        "phase": "Phase 4 data-source assessment", "challenge_v1_frozen": True,
        "challenge_source_ids_count": len(challenge_ids), "raw_case_count": len(assessments),
        "strict_eligible_before_challenge_dedup": len(eligible), "strict_practice_eligible_after_challenge_dedup": len(remaining),
        "new_independent_source_count": 0, "new_baiyun_case_count": 0,
        "generic_guangzhou_government_count": len(generic), "generic_cases_recoverable_from_available_sources": 0,
        "gap_to_500": max(0, 500-len(remaining)), "gap_to_650": max(0, 650-len(remaining)), "gap_to_800": max(0, 800-len(remaining)),
        "file_record_counts": file_counts,
        "upstream_finding": "未发现5143条Markdown的Excel/CSV/JSON/SQL上游；拆分库和legacy均为同源副本。",
        "required_new_data": "至少包含工单编号、完整事项内容、白云区地点/区域和具体最终承办单位的白云区12345原始导出；建议新增432至582条通过严格门禁的候选容量。",
    }
    (args.output / "practice_source_assessment.json").write_text(json.dumps({"summary": summary, "sources": source_rows, "source_hashes": hashes}, ensure_ascii=False, indent=2), encoding="utf-8")
    with (args.output / "practice_source_assessment.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(source_rows[0])); writer.writeheader(); writer.writerows(source_rows)
    (args.output / "challenge_source_ids.json").write_text(json.dumps(sorted(challenge_ids), ensure_ascii=False, indent=2), encoding="utf-8")
    audit_path = args.artifacts / "challenge-v1" / "challenge_questions_v1_audit.json"
    csv_path = args.artifacts / "challenge-v1" / "challenge_questions_v1_approved.csv"
    backup_path = args.artifacts.parent / "dispatch_training.db.pre-phase32.bak"
    manifest = {"version": "challenge-v1", "frozen": True, "question_count": 100,
                "exports": {str(approved_path): sha256(approved_path), str(csv_path): sha256(csv_path), str(audit_path): sha256(audit_path)},
                "database_backup": str(backup_path), "database_backup_sha256": sha256(backup_path)}
    (args.output / "challenge_v1_freeze_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
