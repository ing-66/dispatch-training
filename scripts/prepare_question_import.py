"""Convert reviewed candidate CSV rows into the approved-only API payload."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviewed-csv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.reviewed_csv.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    approved = []
    for row in rows:
        if row.get("review_status") != "approved":
            continue
        if row.get("reference_basis_status") != "verified":
            raise SystemExit(f"{row.get('source_case_id')}: approved题目的reference_basis_status必须为verified")
        dims = [int(row[f"difficulty_dimension_{i}"]) for i in range(1, 6)]
        if any(not 0 <= value <= 20 for value in dims) or sum(dims) != int(row["difficulty_score"]):
            raise SystemExit(f"{row.get('source_case_id')}: 五维评分不合法或与总分不一致")
        question_type = row["question_type"]
        approved.append({
            "source_case_id": row["source_case_id"], "question_type": question_type,
            "level": int(row["suggested_level"]) if question_type == "challenge" else None,
            "case_content": row["case_content"],
            "correct_department_code": row["correct_department_id"],
            "correct_department_name": row["correct_department_name"],
            "wrong_options": [{"department_code": row[f"wrong_department_{i}_id"],
                               "department_name": row[f"wrong_department_{i}"]} for i in range(1, 4)],
            "explanation": row["explanation"], "reference_basis": row["reference_basis"],
            "reference_basis_status": row["reference_basis_status"],
            "difficulty_score": int(row["difficulty_score"]), "review_status": "approved",
            "review_note": row.get("review_note") or None,
            **{f"difficulty_dimension_{i}": dims[i - 1] for i in range(1, 6)},
            **{f"difficulty_dimension_{i}_reason": row[f"difficulty_dimension_{i}_reason"] for i in range(1, 6)},
        })
    challenge_ids = {x["source_case_id"] for x in approved if x["question_type"] == "challenge"}
    practice_ids = {x["source_case_id"] for x in approved if x["question_type"] == "practice"}
    if challenge_ids & practice_ids:
        raise SystemExit("闯关题与自由练习题存在重复source_case_id")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"questions": approved, "replace": False}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"reviewed": len(rows), "approved_for_import": len(approved)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
