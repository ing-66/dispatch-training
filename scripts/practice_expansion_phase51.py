"""Phase 5.1: citywide/public-service same-target + stable Baiyun department expansion."""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT))

from scripts.cross_district_transfer_assessment import (
    DutyIndex,
    LOCAL_ONLY_TOPIC_KEYS,
    detect_topic,
    set_similarity,
    target_pool,
    trigrams,
    write_csv,
    write_json,
)

# Pool A: municipality-level same-target rules. A rule exists only when a citywide function is
# exercised by the same municipal body regardless of the source district and Baiyun has no
# different first-line master body for that exact service/policy function.
CITYWIDE_RULES: dict[str, dict[str, Any]] = {
    "medical_insurance": {
        "source_targets": ("市医保局", "广州市医疗保障局"),
        "mapped_name": "广州市医疗保障局",
        "mapped_id": "DEPT-196df1736f27012d",
        "doc_section": "广州市社会医疗保险规定",
        "evidence_files": (
            "06_广州政府规章/广州市社会医疗保险规定__a48b0906.md",
            "07_广州行政规范性文件/广州市人民政府办公厅关于印发广州市城乡居民社会医疗保险办法的通知.md",
            "07_广州行政规范性文件/广州市人民政府办公厅关于印发广州市城乡居民大病医疗保险办法的通知.md",
        ),
        "evidence_probes": ("市医疗保障行政管理部门主管", "医疗保障经办机构负责社会医疗保险", "市医疗保障局"),
        "topic_terms": ("医保", "医疗保险", "参保", "生育津贴", "生育保险", "定点医院", "医保定点", "报销", "医保卡"),
        "conflict_baiyun_key": "",  # no Baiyun district medical-insurance bureau in the master
        "basis_source": "广州市社会医疗保险规定/广州市城乡居民社会医疗保险办法",
    },
    "government_data": {
        "source_targets": ("市政务服务数据管理局", "市政务办"),
        "mapped_name": "广州市政务服务数据管理局",
        "mapped_id": "DEPT-1696085c937bc64e",
        "doc_section": "广州市政务服务数据管理局",
        "evidence_files": ("05_广州地方性法规/广州市数据条例__bfabe592.md",),
        "evidence_probes": ("政务数据", "政务服务", "一网通办", "穗好办"),
        "topic_terms": ("穗好办", "一网通办", "政务服务中心", "自助服务区", "政务服务"),
        "conflict_baiyun_key": "",
        "basis_source": "广州市数据条例",
    },
}

# Pool B: citywide public-service enterprises. Their service obligations are established by
# citywide regulations and confirmed for Baiyun by existing Baiyun-eligible受理记录.
PUBLIC_RULES: dict[str, dict[str, Any]] = {
    "power": {
        "canonical_names": ("广东电网有限责任公司广州供电局",),
        "mapped_name": "广东电网有限责任公司广州供电局",
        "mapped_id": "DEPT-9cd02e4514d41839",
        "approved_in_db": True,
        "evidence_files": ("05_广州地方性法规/广州市供用电条例__a97b973f.md",),
        "evidence_probes": ("供电企业应当依法向用户提供电力普遍服务", "供电企业应当依法履行供电设施的管理", "供电企业应当建立用电投诉处理制度"),
        "topic_terms": ("停电", "供电", "电线", "变压器", "电表", "电压", "电缆", "电力井盖", "变电站", "配电", "电房", "裸露电线", "用电"),
        "basis_source": "广州市供用电条例",
    },
    "drainage": {
        "canonical_names": ("广州市城市排水有限公司",),
        "mapped_name": "广州市城市排水有限公司",
        "mapped_id": "DEPT-6bd42762aeaed006",
        "approved_in_db": True,
        "evidence_files": ("06_广州政府规章/广州市井盖设施管理办法__e61304ae.md",),
        "evidence_probes": ("井盖设施维护管理责任人", "排水设施维护运营单位"),
        "topic_terms": ("井盖", "沙井", "下水道", "污水", "排水", "积水", "水浸", "内涝", "化粪池", "雨水篦子"),
        "basis_source": "广州市井盖设施管理办法/城市排水服务职责",
    },
    "metro": {
        "canonical_names": ("广州地铁集团有限公司",),
        "mapped_name": "广州地铁集团有限公司",
        "mapped_id": "DEPT-c3e338c3d99f66a9",
        "approved_in_db": True,
        "evidence_files": ("05_广州地方性法规/广州市城市轨道交通管理条例__eb412f3f.md",),
        "evidence_probes": ("城市轨道交通经营单位由市人民政府", "城市轨道交通经营单位应当履行"),
        "topic_terms": ("地铁站内", "站场服务", "报站", "车票", "票务", "安检", "列车", "延误", "停运", "恢复运营", "首末班", "站务", "地铁站", "导乘", "客服"),
        "exclude_terms": ("规划", "建设", "建成", "开通", "东延", "北延", "延长段", "公示", "社会稳定", "进度", "什么时候", "C出口", "A2出口", "新设站点", "增设站点"),
        "basis_source": "广州市城市轨道交通管理条例",
    },
    "bus": {
        "canonical_names": ("广州市公共交通集团有限公司",),
        "mapped_name": "广州市公共交通集团有限公司",
        "mapped_id": "DEPT-b2c960d44a42e488",
        "approved_in_db": True,
        "strict_allowed": False,
        "evidence_files": ("05_广州地方性法规/广州市公共汽车电车客运管理条例__cef10d10.md",),
        "evidence_probes": ("公共汽车电车线路经营者", "市交通行政主管部门是本市公共汽车电车客运的行"),
        "topic_terms": ("公交车", "公交线路", "公交站", "公共汽车", "电车", "候乘", "营运", "首末班", "站台", "线路调整"),
        "basis_source": "广州市公共汽车电车客运管理条例",
    },
}


def load_rows(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def content_text(row: dict[str, Any]) -> str:
    return (row.get("case_content") or "") + "\n" + (row.get("case_title") or "")


def evidence_hit(doc_path: Path, probes: tuple[str, ...]) -> tuple[bool, str, int, str]:
    if not doc_path.is_file():
        return False, "", 0, ""
    lines = doc_path.read_text(encoding="utf-8-sig").splitlines()
    for idx, line in enumerate(lines, 1):
        compact = re.sub(r"\s+", "", line)
        for probe in probes:
            if probe and probe in compact:
                return True, line.strip(), idx, doc_path.name
    return False, "", 0, ""


def classify_citywide(row: dict[str, Any], rules: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    raw = row.get("canonical_dispatch_target") or row.get("raw_department_name") or ""
    for key, rule in rules.items():
        if not any(name and name in raw for name in rule["source_targets"]):
            continue
        text = content_text(row)
        matched = [term for term in rule["topic_terms"] if term in text]
        if not matched:
            continue
        return key, {"matched_terms": tuple(matched), **rule}
    return None, {}


def classify_public(row: dict[str, Any], rules: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    raw = row.get("canonical_dispatch_target") or ""
    for key, rule in rules.items():
        if not any(raw == name for name in rule["canonical_names"]):
            continue
        text = content_text(row)
        matched = [term for term in rule["topic_terms"] if term in text]
        if not matched:
            continue
        if any(ex in text for ex in rule.get("exclude_terms", ())):
            continue
        return key, {"matched_terms": tuple(matched), **rule}
    return None, {}


def extract_evidence_snippet(doc_path: Path, probes: tuple[str, ...]) -> dict[str, str]:
    ok, excerpt, line_no, filename = evidence_hit(doc_path, probes)
    return {"basis_status": "verified" if ok else "needs_review", "basis_excerpt": excerpt[:300],
            "basis_locator": f"{doc_path}；第{line_no}行" if ok else str(doc_path), "basis_title": filename}


def phase51_assess(
    assessments: list[dict[str, Any]],
    challenge: list[dict[str, Any]],
    phase5_strict: list[dict[str, Any]],
    phase5_assessed: list[dict[str, Any]],
    existing_eligible: list[dict[str, Any]],
    knowledge_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    challenge_ids = {x["source_case_id"] for x in challenge}
    challenge_sets = [(x["source_case_id"], trigrams(x.get("case_content", ""))) for x in challenge]
    existing_ids = {x["source_case_id"] for x in existing_eligible}
    existing_sets = [(x["source_case_id"], trigrams(x.get("case_content", ""))) for x in existing_eligible]
    phase5_strict_ids = {x["source_case_id"] for x in phase5_strict}
    phase5_strict_sets = [(x["source_case_id"], trigrams(x.get("case_content", ""))) for x in phase5_strict]

    new_candidates: list[dict[str, Any]] = []
    stats: dict[str, Any] = {"needs_review": 0, "insufficient": 0, "conflict": 0, "verified": 0,
                              "skipped_challenge": 0, "skipped_existing_practice": 0, "skipped_phase5": 0,
                              "skipped_seen": 0}
    seen: set[str] = set()

    def add_row(row: dict[str, Any]) -> None:
        sid = row["source_case_id"]
        if sid in seen:
            stats["skipped_seen"] += 1
            return
        if sid in challenge_ids:
            stats["skipped_challenge"] += 1
            return
        if sid in existing_ids:
            stats["skipped_existing_practice"] += 1
            return
        if sid in phase5_strict_ids:
            stats["skipped_phase5"] += 1
            return
        seen.add(sid)
        new_candidates.append(row)
        stats[row["basis_status"]] = stats.get(row["basis_status"], 0) + 1

    # ---------- Pool C: Phase 5 potential candidates whose Baiyun target is pending ----------
    pending_pool = target_pool()
    verified_pending_keys = {key for key, value in pending_pool.items()
                             if value.get("approved") == "pending" and value.get("doc_section")}
    pool_name_to_key = {value["name"]: key for key, value in pending_pool.items()}
    phase5_by_id = {x["source_case_id"]: x for x in phase5_assessed}
    for source_id in phase5_strict_ids:
        phase5_by_id.pop(source_id, None)
    pool_c_rows: list[dict[str, Any]] = []
    for row in phase5_by_id.values():
        if not row.get("potential_cross_district_candidate"):
            continue
        # Only pending Baiyun department keys can enter Pool C (education etc. not added again).
        target_key = pool_name_to_key.get(row.get("mapped_dispatch_target") or "", "")
        if target_key not in verified_pending_keys:
            continue
        if row.get("mapping_basis_status") != "verified":
            row["basis_status"] = "needs_review"
            pool_c_rows.append({**row, "case_origin": "cross_district_transfer", "strict_eligible": False})
            continue
        # The Phase-5 pending target now becomes a verified canonical candidate.
        base = row.get("case_content", "")
        base_set = trigrams(base)
        near = False
        for cid, cs in (*challenge_sets, *existing_sets, *phase5_strict_sets):
            if set_similarity(base_set, cs) >= 0.86:
                near = True
                break
        if near:
            row["basis_status"] = "needs_review"
            row["review_note"] = "与既有池内容近重复，先标记簇，不进入strict"
            pool_c_rows.append({**row, "case_origin": "cross_district_transfer", "strict_eligible": False})
            continue
        row["basis_status"] = "verified"
        pool_c_rows.append({**row, "case_origin": "cross_district_transfer",
                            "canonical_target_status": "verified_candidate", "strict_eligible": True})
    for row in pool_c_rows:
        if row["basis_status"] == "verified":
            add_row(row)

    # ---------- Pool A: municipal same-citywide rules ----------
    municipal = [r for r in assessments if r.get("organization_type") == "municipal_department"]
    citywide_rule_metrics: Counter[tuple[str, str]] = Counter()
    for row in municipal:
        raw = row.get("canonical_dispatch_target") or ""
        rule_key, rule = classify_citywide(row, CITYWIDE_RULES)
        if not rule_key:
            continue
        citywide_rule_metrics[(rule_key, "classified")] += 1
        evidence = {"basis_status": "needs_review", "basis_excerpt": "", "basis_locator": "", "basis_title": ""}
        for rel in rule["evidence_files"]:
            doc = knowledge_root / rel
            ev = extract_evidence_snippet(doc, rule["evidence_probes"])
            if ev["basis_status"] == "verified":
                evidence = {**ev, "basis_status": "verified"}
                break
        content_ok = len(row.get("case_content") or "") >= 20 and bool(row.get("unique_handler", True))
        conflict_note = ""
        basis_status = evidence["basis_status"]
        if rule_key == "government_data" and basis_status == "verified":
            # 广州市数据条例 does not by itself prove that the app complaint is answered by 市政数局;
            # 穗好办 cases still require human confirmation of the city/区 service boundary.
            basis_status = "needs_review"
            conflict_note = "穗好办市级系统事项存在区级网点协同，需人工复核市/区边界"
        if not content_ok:
            basis_status = "needs_review"
        if basis_status == "verified":
            citywide_rule_metrics[(rule_key, "verified")] += 1
        add_row({
            "source_case_id": row["source_case_id"],
            "source_file": row.get("source_file", ""),
            "source_district": row.get("location_scope", ""),
            "case_origin": "citywide_same_target",
            "case_title": row.get("case_title", ""),
            "case_content": row.get("case_content", ""),
            "source_target_name": raw,
            "source_target_category": "municipal_department",
            "mapped_dispatch_target": rule["mapped_name"],
            "mapped_dispatch_target_id": rule["mapped_id"],
            "topic_key": rule_key,
            "basis_title": evidence.get("basis_title", ""),
            "basis_source": rule.get("basis_source", ""),
            "basis_excerpt": evidence.get("basis_excerpt", ""),
            "basis_locator": evidence.get("basis_locator", ""),
            "basis_status": basis_status,
            "basis_reason": conflict_note or "市级统一承办事项，同类事项在白云区仍由该市级单位承办",
            "exclude_reasons": [] if basis_status == "verified" else ([conflict_note] if conflict_note else ["municipal_district_boundary_needs_review"]),
            "strict_eligible": basis_status == "verified",
            "canonical_target_status": "verified_candidate" if basis_status == "verified" else "needs_review",
            "review_note": conflict_note or "",
            "review_status": "pending",
        })

    # ---------- Pool B: public service same-company ----------
    public_rows = [r for r in assessments if r.get("organization_type") == "public_service"]
    public_precedent = defaultdict(list)
    for r in existing_eligible:
        public_precedent[r.get("canonical_dispatch_target") or r.get("mapped_dispatch_target") or ""].append(r)
    public_rule_metrics: Counter[tuple[str, str]] = Counter()
    for row in public_rows:
        rule_key, rule = classify_public(row, PUBLIC_RULES)
        if not rule_key:
            continue
        public_rule_metrics[(rule_key, "classified")] += 1
        evidence = {"basis_status": "needs_review", "basis_excerpt": "", "basis_locator": "", "basis_title": ""}
        for rel in rule["evidence_files"]:
            doc = knowledge_root / rel
            ev = extract_evidence_snippet(doc, rule["evidence_probes"])
            if ev["basis_status"] == "verified":
                evidence = {**ev, "basis_status": "verified"}
                break
        precedent = public_precedent.get(rule["mapped_name"], [])
        precedent_evidence = ""
        if precedent:
            precedent_evidence = f"白云区已有同类受理记录：{precedent[0]['source_case_id']}"
        content_ok = len(row.get("case_content") or "") >= 20 and bool(row.get("unique_handler", True))
        basis_status = evidence["basis_status"]
        if basis_status == "verified" and content_ok and precedent and rule.get("strict_allowed", True):
            public_rule_metrics[(rule_key, "verified")] += 1
        else:
            basis_status = "needs_review" if content_ok else "needs_review"
            if rule_key == "drainage" and not precedent:
                basis_status = "needs_review"
        add_row({
            "source_case_id": row["source_case_id"],
            "source_file": row.get("source_file", ""),
            "source_district": row.get("location_scope", ""),
            "case_origin": "public_service_same_target",
            "case_title": row.get("case_title", ""),
            "case_content": row.get("case_content", ""),
            "source_target_name": row.get("canonical_dispatch_target") or row.get("raw_department_name", ""),
            "source_target_category": "public_service",
            "mapped_dispatch_target": rule["mapped_name"],
            "mapped_dispatch_target_id": rule["mapped_id"],
            "topic_key": rule_key,
            "basis_title": evidence.get("basis_title", ""),
            "basis_source": rule.get("basis_source", ""),
            "basis_excerpt": evidence.get("basis_excerpt", ""),
            "basis_locator": evidence.get("basis_locator", ""),
            "basis_status": basis_status,
            "basis_reason": (precedent_evidence + ("；" + precedent_evidence if precedent_evidence else "")) or "企业服务范围覆盖全市各区，白云区仍由同一企业承办",
            "exclude_reasons": [] if basis_status == "verified" else ["public_service_boundary_needs_review"],
            "strict_eligible": basis_status == "verified",
            "canonical_target_status": "approved" if rule.get("approved_in_db") else "verified_candidate",
            "review_note": "",
            "review_status": "pending",
        })

    # Only strict rows are retained as new candidates; needs_review rows stay in the audit JSON.
    audited = new_candidates
    new_strict = [x for x in audited if x["strict_eligible"]]
    stats.update({"new_pool_total": len(audited), "new_strict": len(new_strict),
                  "citywide_rule_metrics": {f"{k[0]}.{k[1]}": v for k, v in citywide_rule_metrics.items()},
                  "public_rule_metrics": {f"{k[0]}.{k[1]}": v for k, v in public_rule_metrics.items()}})
    return new_strict, {"all_rows": audited, "stats": stats}


def assess_rows_with_rules(rows: list[dict[str, Any]], pool_type: str) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        raw = row.get("canonical_dispatch_target") or row.get("raw_department_name") or ""
        if pool_type == "municipal":
            rule_key, rule = classify_citywide(row, CITYWIDE_RULES)
        else:
            rule_key, rule = classify_public(row, PUBLIC_RULES)
        out.append({
            "source_case_id": row["source_case_id"],
            "canonical_dispatch_target": raw,
            "raw_department_name": row.get("raw_department_name", ""),
            "case_title": row.get("case_title", ""),
            "location_scope": row.get("location_scope", ""),
            "rule_key": rule_key or "not_mapped",
            "rule_matched_terms": list(rule.get("matched_terms", ())) if rule_key else [],
            "mapped_same_target_name": rule.get("mapped_name", "") if rule_key else "",
            "status": "candidate" if rule_key else "not_applicable",
        })
    return out


def near_duplicate_groups(rows: list[dict[str, Any]], threshold: float = 0.86) -> list[dict[str, Any]]:
    precomputed = [(x, trigrams(x.get("case_content", ""))) for x in rows]
    parent = list(range(len(precomputed)))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    pairs = []
    for i in range(len(precomputed)):
        for j in range(i + 1, len(precomputed)):
            score = set_similarity(precomputed[i][1], precomputed[j][1])
            if score >= threshold:
                pairs.append((i, j, round(score, 3)))
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri
    group_map: dict[int, list[int]] = defaultdict(list)
    for i in range(len(precomputed)):
        group_map[find(i)].append(i)
    clusters = []
    for members in group_map.values():
        if len(members) < 2:
            continue
        clusters.append({
            "cluster_size": len(members),
            "source_case_ids": [precomputed[i][0]["source_case_id"] for i in members],
            "mapped_dispatch_target": members and precomputed[members[0]][0].get("mapped_dispatch_target", ""),
            "similar_pairs": [{"a": precomputed[i][0]["source_case_id"], "b": precomputed[j][0]["source_case_id"],
                               "score": score} for i, j, score in pairs if find(i) == find(members[0])],
        })
    return clusters


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 5.1 practice expansion assessment")
    parser.add_argument("--case-assessments", type=Path, default=ROOT / "artifacts/department-governance-full/case_assessments.json")
    parser.add_argument("--challenge-questions", type=Path, default=ROOT / "artifacts/challenge-v1/challenge_questions_v1_approved.json")
    parser.add_argument("--challenge-ids", type=Path, default=ROOT / "artifacts/practice-source-assessment/challenge_source_ids.json")
    parser.add_argument("--phase5-dir", type=Path, default=ROOT / "artifacts/cross-district-transfer-assessment")
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts/practice-expansion-phase51")
    parser.add_argument("--asset-root", type=Path, default=Path(r"D:\热线派单系统V2\assets\knowledge-source"))
    parser.add_argument("--build-workbook", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    out = args.output_root
    out.mkdir(parents=True, exist_ok=True)

    assessments = load_rows(args.case_assessments)
    challenge = load_rows(args.challenge_questions)
    phase5_strict = load_rows(args.phase5_dir / "strict_cross_district_candidates.json")
    phase5_assessed = load_rows(args.phase5_dir / "cross_district_case_assessment.json")
    challenge_ids = set(json.loads(args.challenge_ids.read_text(encoding="utf-8")))
    existing_eligible = [x for x in assessments if x["case_status"] == "eligible" and x["source_case_id"] not in challenge_ids]

    new_strict, assessed_payload = phase51_assess(
        assessments=assessments,
        challenge=challenge,
        phase5_strict=phase5_strict,
        phase5_assessed=phase5_assessed,
        existing_eligible=existing_eligible,
        knowledge_root=args.asset_root,
    )

    # Pool-specific audit files (all evaluated rows, including not-applicable).
    municipal_rows = [r for r in assessments if r.get("organization_type") == "municipal_department"]
    public_rows = [r for r in assessments if r.get("organization_type") == "public_service"]
    citywide_assessment = assess_rows_with_rules(municipal_rows, "municipal")
    public_assessment = assess_rows_with_rules(public_rows, "public")
    write_json(out / "citywide_case_assessment.json", citywide_assessment)
    write_csv(out / "citywide_case_assessment.csv", citywide_assessment,
              ["source_case_id", "canonical_dispatch_target", "raw_department_name", "case_title", "location_scope",
               "rule_key", "rule_matched_terms", "mapped_same_target_name", "status"])
    write_json(out / "public_service_case_assessment.json", public_assessment)
    write_csv(out / "public_service_case_assessment.csv", public_assessment,
              ["source_case_id", "canonical_dispatch_target", "raw_department_name", "case_title", "location_scope",
               "rule_key", "rule_matched_terms", "mapped_same_target_name", "status"])

    # Pending Baiyun canonical target assessment.
    pool = target_pool()
    pending_rows = []
    for key, value in sorted(pool.items()):
        if value.get("approved") != "pending":
            continue
        pending_rows.append({
            "canonical_target_key": key,
            "canonical_target_name": value.get("name", ""),
            "doc_section": value.get("doc_section", ""),
            "has_authoritative_doc": bool(value.get("doc_section")),
            "has_02_folder": bool(value.get("folder")),
            "status": "verified_candidate" if value.get("doc_section") else "needs_review",
            "review_note": "机构职责/权责清单有权威资料，未写入正式departments主表",
        })
    write_json(out / "pending_target_assessment.json", pending_rows)
    write_csv(out / "pending_target_assessment.csv", pending_rows,
              ["canonical_target_key", "canonical_target_name", "doc_section", "has_authoritative_doc", "has_02_folder", "status", "review_note"])

    # Combined pool.
    def origin_of(row: dict[str, Any], base_origin: str) -> dict[str, Any]:
        return {**row, "case_origin": base_origin,
                "mapped_dispatch_target": row.get("canonical_dispatch_target") or row.get("mapped_dispatch_target") or row.get("correct_department_name") or ""}

    combined = []
    NORMALIZE_NAME = [
        ("白云区教育局", "广州市白云区教育局"),
        ("白云区人力资源社会保障局", "广州市白云区人力资源和社会保障局"),
        ("白云区人力资源和社会保障局", "广州市白云区人力资源和社会保障局"),
        ("广州市白云区人力资源社会保障局", "广州市白云区人力资源和社会保障局"),
        ("白云区市场监督局", "广州市白云区市场监督管理局"),
        ("广州市白云区市场监督局", "广州市白云区市场监督管理局"),
        ("白云区民政局", "广州市白云区民政局"),
        ("白云区水务局", "广州市白云区水务局"),
        ("白云区公安分局", "广州市公安局白云区分局"),
        ("广州市白云区城市管理综合执法局", "广州市白云区城市管理和综合执法局"),
        ("白云区城市管理综合执法局", "广州市白云区城市管理和综合执法局"),
        ("广州市白云区科工商信局", "广州市白云区科技工业商务和信息化局"),
        ("白云区科工商信局", "广州市白云区科技工业商务和信息化局"),
        ("广州市白云区住房建设交通局", "广州市白云区住房建设交通局"),
        ("广州市白云区住房建设和交通局", "广州市白云区住房建设交通局"),
        ("广州市白云区来穗局", "广州市白云区来穗局"),
    ]

    def normalize_name(name: str) -> str:
        for alias, formal in NORMALIZE_NAME:
            if alias == name or (alias and name and alias in name):
                return formal
        return name

    for row in existing_eligible:
        topic_key, _, _, _ = detect_topic(row.get("case_title", ""), row.get("case_content", ""))
        combined.append({**origin_of(row, "baiyun_original"),
                         "mapped_dispatch_target": normalize_name(row.get("canonical_dispatch_target") or ""),
                         "source_district": "白云区", "topic_key": topic_key})
    for row in phase5_strict:
        combined.append({**origin_of(row, "cross_district_transfer"),
                         "mapped_dispatch_target": normalize_name(row.get("mapped_dispatch_target") or ""),
                         "topic_key": row.get("topic_key", "other")})
    for row in new_strict:
        combined.append({**origin_of(row, row.get("case_origin", "cross_district_transfer")),
                         "mapped_dispatch_target": normalize_name(row.get("mapped_dispatch_target") or "")})

    combined_ids = [x["source_case_id"] for x in combined]
    combined_ids_set = set(combined_ids)
    assert len(combined_ids) == len(combined_ids_set), "combined pool contains duplicate source_case_id"
    duplicate_groups = near_duplicate_groups(combined)
    origin_counts = Counter(x["case_origin"] for x in combined)
    target_dist = Counter(x.get("mapped_dispatch_target", "") for x in combined)
    target_rows = [{"canonical_target": name, "candidate_count": n,
                    "percentage": round(n / len(combined) * 100, 2) if combined else 0,
                    "share_flag": ">30%" if n / len(combined) > 0.30 else (">20%" if n / len(combined) > 0.20 else (">10%" if n / len(combined) > 0.10 else ""))}
                   for name, n in target_dist.most_common()]
    topic_rows = [{"topic_key": key, "case_count": n} for key, n in Counter(x.get("topic_key", "unknown") for x in combined).most_common()]

    strict_new_by_origin = Counter(x.get("case_origin") for x in new_strict)
    education_total = sum(1 for x in combined if "教育局" in (x.get("mapped_dispatch_target") or ""))
    merged_capacity = len(combined)
    summary = {
        "phase": "Phase 5.1 practice expansion assessment",
        "challenge_v1_frozen": True,
        "existing_baiyun_strict": len(existing_eligible),
        "phase5_cross_district_strict": len(phase5_strict),
        "phase51_new_strict_total": len(new_strict),
        "phase51_new_by_origin": dict(strict_new_by_origin),
        "same_citywide_target_strict": strict_new_by_origin.get("citywide_same_target", 0),
        "public_service_same_target_strict": strict_new_by_origin.get("public_service_same_target", 0),
        "verified_pending_target_count": sum(1 for p in pending_rows if p["status"] == "verified_candidate"),
        "merged_practice_capacity": merged_capacity,
        "gap_to_500": max(0, 500 - merged_capacity),
        "gap_to_650": max(0, 650 - merged_capacity),
        "gap_to_800": max(0, 800 - merged_capacity),
        "origin_counts": dict(origin_counts),
        "education_share_percent": round(education_total / merged_capacity * 100, 2) if merged_capacity else 0.0,
        "education_count": education_total,
        "phase51_stats": assessed_payload["stats"],
        "duplicate_cluster_count": len(duplicate_groups),
        "needs_review_total": assessed_payload["stats"].get("needs_review", 0),
        "insufficient_total": assessed_payload["stats"].get("insufficient", 0),
        "conflict_total": assessed_payload["stats"].get("conflict", 0),
    }
    write_json(out / "summary.json", summary)
    write_json(out / "new_strict_practice_candidates.json", new_strict)
    strict_fields = ["source_case_id", "source_district", "source_target_name", "mapped_dispatch_target", "case_origin",
                     "topic_key", "basis_status", "basis_title", "basis_source", "basis_excerpt", "basis_locator", "strict_eligible", "review_status"]
    write_csv(out / "new_strict_practice_candidates.csv", new_strict, strict_fields)
    write_json(out / "combined_practice_candidates.json", combined)
    write_json(out / "department_distribution.json", target_rows)
    write_csv(out / "department_distribution.csv", target_rows, ["canonical_target", "candidate_count", "percentage", "share_flag"])
    write_json(out / "topic_clusters.json", topic_rows)
    write_csv(out / "topic_clusters.csv", topic_rows, ["topic_key", "case_count"])
    write_json(out / "duplicate_clusters.json", duplicate_groups)
    write_json(out / "audit_all_new_rows.json", assessed_payload["all_rows"])
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.build_workbook:
        runtime = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies"
        node, modules = runtime / "node" / "bin" / "node.exe", runtime / "node" / "node_modules"
        if not node.exists() or not modules.exists():
            raise SystemExit("审核Excel生成环境不可用；JSON/CSV结果已保留")
        temp = out / ".workbook-runtime"
        temp.mkdir(exist_ok=True)
        link = temp / "node_modules"
        if not link.exists():
            subprocess.run(["powershell", "-NoProfile", "-Command",
                            f"New-Item -ItemType Junction -Path '{link.absolute()}' -Target '{modules}' | Out-Null"], check=True)
        builder = Path(__file__).with_name("build_practice_expansion_phase51_workbook.mjs")
        temp_builder = temp / builder.name
        shutil.copy2(builder, temp_builder)
        subprocess.run([node, temp_builder, str(out), str(out / "practice_expansion_phase51.xlsx")], check=True)
        if not link.is_junction():
            raise RuntimeError("临时node_modules不是预期的目录联接")
        os.rmdir(link)
        temp_builder.unlink(missing_ok=True)
        temp.rmdir()


if __name__ == "__main__":
    main()
