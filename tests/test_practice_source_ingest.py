from pathlib import Path
import json
import subprocess
import sys

from scripts.practice_source_ingest import read_source, scope_of, similarity, stable_id, suggest_mapping

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def test_csv_alias_headers_are_detected():
    rows, headers, source = read_source(FIXTURES / "practice_source_aliases.csv")
    mapping = suggest_mapping(headers)
    assert source == "csv" and len(rows) == 2
    assert mapping["source_case_id"]["source_field"] == "流水号"
    assert mapping["case_content"]["source_field"] == "问题描述"
    assert mapping["raw_dispatch_target"]["source_field"] == "处理部门"


def test_json_record_container_and_aliases_are_supported():
    rows, headers, source = read_source(FIXTURES / "practice_source_cases.json")
    mapping = suggest_mapping(headers)
    assert source == "json" and len(rows) == 2
    assert mapping["source_case_id"]["source_field"] == "case_id"
    assert mapping["case_content"]["source_field"] == "诉求内容"


def test_generated_id_is_stable_and_dataset_scoped():
    one = stable_id("dataset-a", "file.csv", "相同内容", "单位", "2026-01-01")
    assert one == stable_id("dataset-a", "file.csv", "相同内容", "单位", "2026-01-01")
    assert one != stable_id("dataset-b", "file.csv", "相同内容", "单位", "2026-01-01")


def test_baiyun_scope_uses_structured_evidence_first():
    assert scope_of("白云区", "", "", "")[0] == "baiyun_confirmed"
    assert scope_of("", "景泰街", "", "")[0] == "baiyun_confirmed"
    assert scope_of("越秀区", "", "越秀区解放路", "")[0] == "non_baiyun"
    assert scope_of("", "", "", "景泰街附近有问题")[0] == "baiyun_probable"
    assert scope_of("", "", "", "地点不详")[0] == "unknown"


def test_near_duplicate_similarity_detects_same_content():
    assert similarity("白云区某道路存在垃圾堆积需要清理", "白云区某道路存在垃圾堆积需要清理") == 1
    assert similarity("完全不同的学校招生咨询事项", "道路路灯损坏需要维修") < 0.2


def test_xlsx_fixture_is_readable():
    rows, headers, source = read_source(FIXTURES / "practice_source_normal.xlsx")
    assert source == "first_sheet" and len(rows) == 6
    assert suggest_mapping(headers)["raw_dispatch_target"]["source_field"] == "最终承办单位"


def test_end_to_end_challenge_and_cross_source_dedup(tmp_path):
    challenge = json.loads((ROOT / "artifacts/challenge-v1/challenge_questions_v1_approved.json").read_text(encoding="utf-8"))[0]
    existing = next(x for x in json.loads((ROOT / "artifacts/department-governance-full/case_assessments.json").read_text(encoding="utf-8"))
                    if x["case_status"] == "eligible" and x["source_case_id"] != challenge["source_case_id"])
    records = [
        {"工单编号": challenge["source_case_id"], "事项内容": challenge["case_content"], "所属区": "白云区", "最终承办单位": challenge["correct_department_name"]},
        {"工单编号": "DIFFERENT-ID", "事项内容": challenge["case_content"], "所属区": "白云区", "最终承办单位": challenge["correct_department_name"]},
        {"工单编号": "EXISTING-COPY", "事项内容": existing["case_content"], "所属区": "白云区", "最终承办单位": existing["raw_department_name"]},
        {"事项内容": "白云区景泰街测试道路旁连续多日堆放废弃纸箱和生活垃圾，请安排清运处理。", "所属区": "白云区", "最终承办单位": "广州市白云区人民政府-景泰街"},
    ]
    source = tmp_path / "dedup.json"; source.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "out"
    subprocess.run([sys.executable, str(ROOT / "scripts/practice_source_ingest.py"), str(source), "--dataset-id", "dedup-test",
                    "--output-root", str(output), "--no-build-workbook"], cwd=ROOT, check=True, capture_output=True)
    result = json.loads((output / "dedup-test/normalized_cases.json").read_text(encoding="utf-8"))
    assert "challenge_source_id_duplicate" in result[0]["exclude_reasons"]
    assert "challenge_content_near_duplicate_review" in result[1]["exclude_reasons"]
    assert "existing_practice_content_near_duplicate_review" in result[2]["exclude_reasons"]
    assert result[3]["source_case_id"].startswith("NEW-")
