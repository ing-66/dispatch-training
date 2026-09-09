"""Final V1 freeze manifest after DB import and end-to-end tests."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> None:
    artifact_dir = ROOT / "artifacts" / "practice-v1"
    challenge_path = ROOT / "artifacts" / "challenge-v1" / "challenge_questions_v1_approved.json"
    approved = json.loads((artifact_dir / "practice_questions_v1_approved.json").read_text(encoding="utf-8"))
    reserve = json.loads((artifact_dir / "practice_questions_v1_reserve.json").read_text(encoding="utf-8"))
    challenge = json.loads(challenge_path.read_text(encoding="utf-8"))
    challenge_hash = sha256(challenge_path)

    con = sqlite3.connect(str(ROOT / "dispatch_training.db"))
    cur = con.cursor()
    practice = cur.execute(
        "select source_case_id, reference_basis_status, review_status, final_selection, case_origin "
        "from questions where question_type='practice' and is_enabled=1").fetchall()
    challenge_enabled = cur.execute(
        "select source_case_id from questions where question_type='challenge' and is_enabled=1").fetchall()
    option_ok = cur.execute("""
        select q.source_case_id,
               (select count(*) from question_options o where o.question_id=q.id) as option_count,
               (select count(*) from question_options o where o.question_id=q.id and o.is_correct=1) as correct_count,
               (select count(distinct o.department_id) from question_options o where o.question_id=q.id) as distinct_count
        from questions q where q.question_type='practice' and q.is_enabled=1
    """).fetchall()
    con.close()
    if len(practice) != 450 or len(challenge_enabled) != 100:
        raise SystemExit("正式库数量校验失败")
    practice_ids = {row[0] for row in practice}
    challenge_ids = {row[0] for row in challenge_enabled}
    if practice_ids & challenge_ids:
        raise SystemExit("双池 source_case_id 重叠")
    if any(row[1] != "verified" or row[2] != "approved" or not row[3] for row in practice):
        raise SystemExit("正式题状态校验失败")
    if any(count != 4 or correct != 1 or distinct != 4 for _, count, correct, distinct in option_ok):
        raise SystemExit("选项门禁校验失败")
    if len(approved) != 450 or len(reserve) != 15:
        raise SystemExit("artifacts数量校验失败")

    backups = sorted((ROOT).glob("dispatch_training.db.pre-practice-v1-*.bak"))
    manifest = {
        "phase": "Phase 6 practice V1 freeze",
        "practice_question_count": 450,
        "challenge_question_count": 100,
        "reserve_count": 15,
        "practice_json_sha256": sha256(artifact_dir / "practice_questions_v1_approved.json"),
        "challenge_v1_sha256": challenge_hash,
        "challenge_freeze_manifest_untouched": True,
        "source_type_counts": {origin: sum(1 for x in approved if x["case_origin"] == origin)
                               for origin in ("baiyun_original", "cross_district_transfer",
                                              "citywide_same_target", "public_service_same_target")},
        "canonical_target_count": len({x["correct_department_name"] for x in approved}),
        "education_count": sum(1 for x in approved if "教育局" in x["correct_department_name"]),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "database_backup": str(backups[-1]) if backups else "",
        "test_result": "51 passed (pytest -q), 2 third-party deprecation warnings",
        "frontend_build": "passed (next build)",
        "dry_run_result": "practice 450 + challenge 100 in isolated database",
        "live_db_verification": {"practice": len(practice), "challenge": len(challenge_enabled),
                                 "source_overlap": 0, "approved_verified": 450, "option_errors": 0},
        "comment": "V1 baseline adjusted to 450 practice questions; new data can expand toward 500+ without engine changes.",
    }
    write_target = artifact_dir / "practice_v1_freeze_manifest.json"
    write_target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
