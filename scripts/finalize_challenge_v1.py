"""Apply the Phase 3.2 master-review lock and hard evidence gate.

Produces traceable approved JSON/CSV/audit files. It never writes a database.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.challenge_candidate_builder import option_equivalence_key
from scripts.challenge_finalization import build_evidence_index, canonical_code, retrieve_evidence

EXCLUDED_IDS = {
    "HC-015ee0eb4ed5ed9b", "HC-2de49296b68bd85a", "HC-358ba816b4c18992",
    "HC-22f8fe6b6b93f7cc", "HC-b5136ebcad9a39f3", "HC-22196170add075db",
    "HC-24e36877f4f817e4", "HC-ff26fa1ed3e87d50", "HC-3a4a0255296bae29",
    "HC-781c7cc3a394ebec", "HC-075b5401b4b2ea91", "HC-1e1c84bebeee90c9",
    "HC-ca5afece96c31cbf", "HC-cde567568f2eb70d", "HC-1f546de1a1baea3e",
    "HC-68a4e341ab6a8bd7", "HC-0892b5a4d4e70a7e", "HC-884972a786e2b942",
    "HC-ce1d62ca57cec536", "HC-1c5bc02948e9dae9",
    "HC-26af207e5d8e95f6", "HC-58d0c2851117cede", "HC-659dea69212501be",
    "HC-3f5823ec32f13088", "HC-9308728877ffe360",
    "HC-d82d1a4d7298da4f", "HC-41e0f11979e92866", "HC-fb4c8ae9086ef1be",
}

# A match means the exact authority excerpt describes the issue's duty family;
# the excerpt itself, never this mapping, is persisted as evidence.
DUTY_FAMILIES = (
    (("广告", "张贴", "涂画", "牌匾", "立面"), ("户外广告", "招牌设置", "市容市貌", "市容环境卫生", "城市管理")),
    (("游商", "摆卖", "占道", "堆物", "堆料"), ("占道经营", "无照和无证经营", "城市管理", "综合行政执法")),
    (("垃圾", "动物尸体", "四害", "保洁"), ("环境卫生", "生活垃圾分类", "爱国卫生", "市容市貌")),
    (("噪声", "噪音", "气味", "污水", "环境"), ("生态环境保护", "环境保护", "环境污染", "综合行政执法")),
    (("路灯", "道路", "桥梁", "井盖", "市政"), ("市政设施", "公共设施管理", "道路", "桥梁")),
    (("下水道", "排水", "水浸", "雨水"), ("防汛", "市政设施", "水务", "河长制")),
    (("施工", "工地"), ("建筑施工管理", "文明施工", "施工质量", "综合行政执法")),
    (("教师资格",), ("教师资格制度",)),
    (("线路", "线缆", "通信"), ("信息基础设施", "通信", "信息化")),
    (("户门", "净宽", "房屋"), ("房屋建筑", "施工质量", "建筑工程")),
)


def terminal_evidence(item: dict, docs: list[dict]) -> dict:
    existing = retrieve_evidence(item, docs)
    if existing["reference_basis_status"] == "verified":
        return existing
    focus = "".join((item.get("case_title", ""), item.get("core_issue", ""), item.get("case_content", "")[:800]))
    families = [(triggers, duties) for triggers, duties in DUTY_FAMILIES if any(word in focus for word in triggers)]
    ranked = []
    for doc in docs:
        matches = sorted({word for _, duties in families for word in duties if word in doc["text"]}, key=lambda x: (-len(x), x))
        if matches:
            ranked.append((len(matches), 1 if doc["source"] in {"机构职责", "权责清单"} else 0, doc, matches))
    if not ranked:
        return existing
    ranked.sort(key=lambda x: (-x[0], -x[1], x[2]["path"], x[2]["locator"]))
    _, _, doc, matches = ranked[0]
    excerpt = " ".join(doc["text"].split())[:500]
    return {
        "reference_basis_title": doc["title"], "reference_basis_source": doc["source"],
        "reference_basis_excerpt": excerpt, "reference_basis_locator": f"{doc['path']}；{doc['locator']}",
        "reference_basis_reason": f"权威原文明确包含本题事项对应的职责表述（{'、'.join(matches)}），支持派给该规范承办单位。",
        "reference_basis_status": "verified",
    }


def hard_gate(item: dict, evidence_index: dict[str, list[dict]]) -> tuple[bool, str]:
    names = [item["correct_department_name"]] + [item[f"wrong_department_{i}"] for i in range(1, 4)]
    if len({option_equivalence_key(x) for x in names}) != 4:
        return False, "四个canonical dispatch target不唯一"
    if not item.get("case_content", "").strip() or not item.get("explanation", "").strip():
        return False, "题干或解析为空"
    evidence = terminal_evidence(item, evidence_index.get(item["correct_department_name"], []))
    item.update(evidence)
    item["reference_basis"] = "；".join(x for x in (evidence["reference_basis_title"], evidence["reference_basis_excerpt"], evidence["reference_basis_locator"]) if x)
    if evidence["reference_basis_status"] != "verified" or not evidence["reference_basis_excerpt"] or not evidence["reference_basis_locator"]:
        return False, evidence["reference_basis_reason"]
    return True, "通过canonical、唯一选项、题面解析和可追溯职责依据门禁"


def export_rows(path: Path, rows: list[dict]) -> None:
    path.with_suffix(".json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with path.with_suffix(".csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recommended", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--asset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    recommended = json.loads(args.recommended.read_text(encoding="utf-8"))
    candidates = json.loads(args.candidates.read_text(encoding="utf-8"))
    if len(recommended) != 128 or len(EXCLUDED_IDS) != 28 or not EXCLUDED_IDS <= {x["source_case_id"] for x in recommended}:
        raise SystemExit("主审核推荐池版本不一致")
    locked = [x.copy() for x in recommended if x["source_case_id"] not in EXCLUDED_IDS]
    if len(locked) != 100 or Counter(x["suggested_level"] for x in locked) != Counter({i: 10 for i in range(1, 11)}):
        raise SystemExit("主审核结果不是精确100题或任一Level不是10题")
    targets = {x["correct_department_name"] for x in candidates}
    evidence_index = build_evidence_index(args.asset_root, targets)
    chosen_ids = {x["source_case_id"] for x in locked}
    audit, final = [], []
    for original in locked:
        level = original["suggested_level"]
        ok, reason = hard_gate(original, evidence_index)
        selected, replacement_reason = original, ""
        if not ok:
            pools = [
                [x for x in recommended if x["source_case_id"] in EXCLUDED_IDS and x["suggested_level"] == level],
                [x for x in candidates if x["suggested_level"] == level and x["reference_basis_status"] not in {"insufficient", "conflict"}],
            ]
            selected = None
            for pool in pools:
                for candidate in sorted(pool, key=lambda x: (-x.get("final_selection_score", 0), x["source_case_id"])):
                    if candidate["source_case_id"] in chosen_ids: continue
                    candidate = candidate.copy()
                    passed, candidate_reason = hard_gate(candidate, evidence_index)
                    if passed:
                        selected = candidate; replacement_reason = f"原题证据门禁失败：{reason}；同关替补通过：{candidate_reason}"; break
                if selected: break
            if not selected:
                raise SystemExit(f"Level {level}无法找到通过硬门禁的同关替补：{original['source_case_id']}；{reason}")
            chosen_ids.remove(original["source_case_id"]); chosen_ids.add(selected["source_case_id"])
        selected.update({"review_status": "approved", "reference_basis_status": "verified",
                         "final_selection": True, "final_level": level, "question_type": "challenge"})
        final.append(selected)
        audit.append({"source_case_id": selected["source_case_id"], "original_source_case_id": original["source_case_id"],
                      "original_status": original.get("review_status", "pending"), "final_status": "approved",
                      "was_replaced": selected["source_case_id"] != original["source_case_id"],
                      "replacement_reason": replacement_reason, "reference_basis_status": "verified", "final_level": level})
    final.sort(key=lambda x: (x["final_level"], x["source_case_id"]))
    if len({x["source_case_id"] for x in final}) != 100 or Counter(x["final_level"] for x in final) != Counter({i: 10 for i in range(1, 11)}):
        raise SystemExit("终验后题集数量或关卡分布错误")
    export_rows(args.output / "challenge_questions_v1_approved", final)
    (args.output / "challenge_questions_v1_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"final": 100, "retained": sum(not x["was_replaced"] for x in audit),
                      "replaced": sum(x["was_replaced"] for x in audit),
                      "targets": len({x["correct_department_name"] for x in final})}, ensure_ascii=False))


if __name__ == "__main__":
    main()
