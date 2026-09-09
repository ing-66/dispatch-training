"""Finalize names, retrieve traceable duty evidence, and recalibrate challenge candidates.

The output remains review-only. No question is approved or imported.
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

from scripts.challenge_candidate_builder import option_equivalence_key, relatedness, target_family

AUTHORITATIVE_ALIASES = {
    "白云区教育局": "广州市白云区教育局",
    "白云区民政局": "广州市白云区民政局",
    "白云区水务局": "广州市白云区水务局",
    "白云区公安分局": "广州市公安局白云区分局",
    "广州市白云区住房建设和交通局": "广州市白云区住房建设交通局",
    "广州市白云区市场监督局": "广州市白云区市场监督管理局",
    "广州市白云区人力资源社会保障局": "广州市白云区人力资源和社会保障局",
    "广州市白云区科工商信局": "广州市白云区科技工业商务和信息化局",
    "广州市白云区城市管理综合执法局": "广州市白云区城市管理和综合执法局",
}
TITLE_ALIASES = {
    "区教育局": "广州市白云区教育局", "区民政局": "广州市白云区民政局",
    "区水务局": "广州市白云区水务局", "区住房建设交通局": "广州市白云区住房建设交通局",
    "区市场监管局": "广州市白云区市场监督管理局", "区人力资源和社会保障局": "广州市白云区人力资源和社会保障局",
    "区科工信局": "广州市白云区科技工业商务和信息化局",
    "区城市管理综合执法局": "广州市白云区城市管理和综合执法局",
    "区枢纽办": "广州市白云区枢纽办", "广州市白云湖数字科技城管理服务中心": "广州市白云区白云湖数字科技城管理服务中心",
}
TOPICS = (
    "垃圾", "噪声", "停车", "道路", "路灯", "占道", "违建", "违法建设", "物业", "学校", "招生", "培训", "教育",
    "排水", "污水", "供水", "停水", "水浸", "井盖", "河涌", "电力", "停电", "供电", "地铁", "公交", "交通",
    "治安", "诈骗", "户籍", "身份证", "出租屋", "社保", "就业", "工资", "劳动", "市场", "食品", "餐饮", "施工",
    "工地", "住房", "房屋", "燃气", "消防", "绿化", "树木", "环卫", "保洁", "养老", "救助", "婚姻", "企业",
    "科技", "工业", "通信", "数据", "征收", "土地", "规划", "小区", "公园", "卫生", "医疗", "广告", "经营", "行道树",
)


def canonical_name(name: str) -> str:
    return AUTHORITATIVE_ALIASES.get(name, name)


def canonical_code(name: str) -> str:
    return "DEPT-" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:16]


def topics(text: str) -> set[str]:
    return {word for word in TOPICS if word in text}


def clean_excerpt(text: str, limit: int = 360) -> str:
    return re.sub(r"\s+", " ", text).strip()[:limit]


def target_from_heading(heading: str, candidate_targets: set[str]) -> str | None:
    heading = heading.strip().lstrip("#").strip()
    if heading in TITLE_ALIASES: return TITLE_ALIASES[heading]
    if heading.endswith(("街", "镇")):
        value = f"广州市白云区人民政府-{heading}"
        return value if value in candidate_targets else None
    normalized = canonical_name(heading)
    if normalized in candidate_targets: return normalized
    for target in candidate_targets:
        tail = target.split("-")[-1]
        if tail == heading or heading in target or target in heading:
            return target
    return None


def add_document(index: dict[str, list[dict]], target: str, title: str, source_type: str,
                 path: Path, locator: str, text: str) -> None:
    if not text.strip(): return
    index[target].append({"title": title, "source": source_type, "path": str(path),
                          "locator": locator, "text": text.strip(), "topics": topics(text)})


def build_evidence_index(asset_root: Path, candidate_targets: set[str]) -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = defaultdict(list)
    duties = asset_root / "knowledge-source" / "01_机构职责" / "白云区政府部门职责明细.md"
    text = duties.read_text(encoding="utf-8")
    sections = re.findall(r"(?ms)^##\s+(.+?)\s*$\n(.*?)(?=^##\s|\Z)", text)
    for heading, body in sections:
        target = target_from_heading(heading, candidate_targets)
        if not target: continue
        paragraphs = [x.strip() for x in re.split(r"\n\s*\n|(?=（[一二三四五六七八九十]+）)", body) if x.strip()]
        for number, paragraph in enumerate(paragraphs, 1):
            add_document(index, target, "白云区政府部门职责明细", "机构职责", duties, f"{heading}，职责段落{number}", paragraph)

    street_dir = asset_root / "knowledge-source" / "01_机构职责" / "白云区镇街机构职能和机构设置__拆分"
    for path in street_dir.glob("*.md"):
        body = path.read_text(encoding="utf-8")
        match = re.search(r"(?m)^#\s+(.+?)\s*$", body)
        if not match: continue
        actual_unit = re.search(r"([\u4e00-\u9fff]{2,8}?)(街道|街|镇)(?:党工委|党委|办事处|人民政府)", body)
        heading = (actual_unit.group(1) + ("街" if actual_unit.group(2) == "街道" else actual_unit.group(2))) if actual_unit else match.group(1)
        if not target_from_heading(heading, candidate_targets) and "机构职责" in path.name:
            number = int(path.name.split("_", 1)[0])
            paired = next(iter(street_dir.glob(f"{number - 1:05d}_机构设置*.md")), None)
            if paired:
                headings = re.findall(r"(?m)^#\s+(.+?)\s*$", paired.read_text(encoding="utf-8"))
                alternatives = [x for x in headings if target_from_heading(x, candidate_targets)]
                if alternatives: heading = alternatives[-1]
        target = target_from_heading(heading, candidate_targets)
        if not target: continue
        paragraphs = [x.strip() for x in re.split(r"\n\s*\n|(?=（[一二三四五六七八九十]+）)", body) if x.strip() and not x.startswith("#")]
        for number, paragraph in enumerate(paragraphs, 1):
            add_document(index, target, f"{heading}机构职责", "镇街机构职责", path, f"机构职责段落{number}", paragraph)

    rights_root = asset_root / "knowledge-source" / "02_权责清单"
    for path in rights_root.rglob("*.md"):
        body = path.read_text(encoding="utf-8")
        match = re.search(r"(?m)^#\s+(.+?)\s*$", body)
        if not match: continue
        target = target_from_heading(match.group(1), candidate_targets)
        if not target: continue
        blocks = re.split(r"(?m)^---\s*$", body)
        for block_number, block in enumerate(blocks, 1):
            item = re.search(r"(?m)^##\s+权责事项：(.+?)\s*$", block)
            excerpt_match = re.search(r"(?ms)【(?:责任事项|权责事项名称)】\s*\n(.*?)(?=\n【|\Z)", block)
            excerpt = excerpt_match.group(1).strip() if excerpt_match else ""
            if item and excerpt:
                add_document(index, target, f"{match.group(1)}权责清单", "权责清单", path,
                             f"权责事项：{item.group(1).strip()}", f"{item.group(1).strip()}。{excerpt}")
    return index


def retrieve_evidence(case: dict, docs: list[dict]) -> dict:
    focus = case.get("case_title", "") + case.get("core_issue", "")
    case_topics = topics(focus) or topics(case["case_content"][:800])
    ranked = []
    for doc in docs:
        overlap = case_topics & doc["topics"]
        score = len(overlap) * 10 + (3 if doc["source"] == "机构职责" else 2 if doc["source"] == "权责清单" else 1)
        ranked.append((score, len(overlap), doc, overlap))
    ranked.sort(key=lambda x: (-x[0], x[2]["path"], x[2]["locator"]))
    if ranked and ranked[0][1] >= 1:
        _, _, doc, overlap = ranked[0]
        return {"reference_basis_title": doc["title"], "reference_basis_source": doc["source"],
                "reference_basis_excerpt": clean_excerpt(doc["text"]),
                "reference_basis_locator": f"{doc['path']}；{doc['locator']}",
                "reference_basis_reason": f"原文明确列出正确承办单位职责，且与本题事项关键词（{'、'.join(sorted(overlap))}）直接相关。",
                "reference_basis_status": "verified"}
    if docs:
        doc = docs[0]
        return {"reference_basis_title": doc["title"], "reference_basis_source": doc["source"],
                "reference_basis_excerpt": "", "reference_basis_locator": f"{doc['path']}；待定位具体职责段落",
                "reference_basis_reason": "已找到该承办单位的权威职责资料，但未检索到与本题事项直接匹配的原文段落。",
                "reference_basis_status": "needs_review"}
    return {"reference_basis_title": "", "reference_basis_source": "",
            "reference_basis_excerpt": "", "reference_basis_locator": "",
            "reference_basis_reason": "现有机构职责和权责清单中未找到该承办单位可直接支撑本题的职责原文。",
            "reference_basis_status": "insufficient"}


def normalize_candidate(candidate: dict, raw_name: str) -> tuple[dict, dict]:
    old = candidate["correct_department_name"]
    new = canonical_name(old)
    code = canonical_code(new)
    candidate.update({"raw_department_name": raw_name, "correct_department_name": new,
                      "correct_dispatch_target": new, "correct_department_id": code})
    return candidate, {"raw_name": raw_name, "previous_canonical_name": old, "canonical_name": new,
                       "canonical_code": code, "organization_type": "unknown",
                       "alias_status": "corrected" if new != old else "canonical",
                       "review_status": "pending", "review_note": ""}


def normalize_options(candidate: dict, target_pool: list[dict]) -> int:
    replacements = 0
    correct_key = option_equivalence_key(candidate["correct_department_name"])
    used = {correct_key}
    current = []
    for i in range(1, 4):
        name = canonical_name(candidate[f"wrong_department_{i}"])
        key = option_equivalence_key(name)
        if key in used or name not in {x["name"] for x in target_pool}:
            current.append(None)
        else:
            current.append(name); used.add(key)
    correct_meta = {"source_case_id": candidate["source_case_id"], "canonical_dispatch_target": candidate["correct_department_name"],
                    "organization_type": candidate["organization_type"]}
    pool_meta = [{"source_case_id": candidate["source_case_id"], "canonical_dispatch_target": x["name"],
                  "organization_type": x["organization_type"]} for x in target_pool if option_equivalence_key(x["name"]) not in used]
    pool_meta.sort(key=lambda x: relatedness(correct_meta, x), reverse=True)
    for index, name in enumerate(current):
        if name is not None: continue
        while pool_meta and option_equivalence_key(pool_meta[0]["canonical_dispatch_target"]) in used: pool_meta.pop(0)
        replacement = pool_meta.pop(0)["canonical_dispatch_target"]
        current[index] = replacement; used.add(option_equivalence_key(replacement)); replacements += 1
    for i, name in enumerate(current, 1):
        candidate[f"wrong_department_{i}"] = name; candidate[f"wrong_department_{i}_id"] = canonical_code(name)
    return replacements


def recalibrate_levels(candidates: list[dict]) -> int:
    for item in candidates:
        correct = {"source_case_id": item["source_case_id"], "canonical_dispatch_target": item["correct_department_name"], "organization_type": item["organization_type"]}
        related = 0
        for i in range(1, 4):
            wrong = {"source_case_id": item["source_case_id"], "canonical_dispatch_target": item[f"wrong_department_{i}"], "organization_type": item.get(f"wrong_organization_type_{i}", "unknown")}
            related += relatedness(correct, wrong)[0] >= 3
        misleading = sum(word in item["case_content"] for word in ("但是", "实际", "同时", "其中", "是否", "无法", "不属于"))
        fit = item["difficulty_score"] + related * 5 + item["difficulty_dimension_3"] * 0.8 + item["difficulty_dimension_1"] * 0.5 + min(4, misleading * 2)
        item["high_related_distractor_count"] = related
        item["level_fit_score"] = round(fit, 2)
    ordered = sorted(candidates, key=lambda x: (x["level_fit_score"], x["difficulty_score"], x["source_case_id"]))
    values = [x["level_fit_score"] for x in ordered]
    cuts = [values[min(len(values)-1, round(len(values)*p/10)-1)] for p in range(1, 10)]
    adjusted = 0
    for item in candidates:
        level = 1 + sum(item["level_fit_score"] > cut for cut in cuts)
        old = item["suggested_level"]
        item["previous_suggested_level"] = old; item["suggested_level"] = level
        item["level_fit_review"] = f"综合题干理解、诉求隐蔽度、职责边界和{item['high_related_distractor_count']}个高相关干扰项，建议Level {level}。"
        adjusted += level != old
    return adjusted


def write_rows(path: Path, rows: list[dict]) -> None:
    path.with_suffix(".json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    if rows:
        with path.with_suffix(".csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]), extrasaction="ignore"); writer.writeheader(); writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--case-assessments", type=Path, required=True)
    parser.add_argument("--asset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    candidates = json.loads(args.candidates.read_text(encoding="utf-8"))
    assessments = {x["source_case_id"]: x for x in json.loads(args.case_assessments.read_text(encoding="utf-8"))}
    alias_rows = []
    for item in candidates:
        item["organization_type"] = assessments[item["source_case_id"]]["organization_type"]
        normalized, alias = normalize_candidate(item, assessments[item["source_case_id"]]["raw_department_name"])
        alias["organization_type"] = item["organization_type"]; alias_rows.append(alias)
    alias_rows = list({(x["raw_name"], x["canonical_name"]): x for x in alias_rows}.values())

    target_meta = {}
    for item in candidates: target_meta[item["correct_department_name"]] = item["organization_type"]
    target_pool = [{"name": name, "organization_type": org_type} for name, org_type in target_meta.items()]
    option_replacements = sum(normalize_options(item, target_pool) for item in candidates)
    evidence_index = build_evidence_index(args.asset_root, set(target_meta))
    evidence_pool = {}
    for item in candidates:
        evidence = retrieve_evidence(item, evidence_index.get(item["correct_department_name"], []))
        item.update(evidence)
        item["reference_basis"] = "；".join(x for x in (evidence["reference_basis_title"], evidence["reference_basis_excerpt"], evidence["reference_basis_locator"]) if x)
        key = (item["correct_department_name"], evidence["reference_basis_locator"])
        if evidence["reference_basis_locator"]: evidence_pool[key] = {"canonical_dispatch_target": item["correct_department_name"], **evidence}
    adjusted = recalibrate_levels(candidates)

    level_stats = []
    for level in range(1, 11):
        rows = [x for x in candidates if x["suggested_level"] == level]
        level_stats.append({"level": level, "candidate_count": len(rows),
                            "average_difficulty_score": round(sum(x["difficulty_score"] for x in rows)/len(rows), 2) if rows else 0,
                            "average_clarity": round(sum(x["difficulty_dimension_1"] for x in rows)/len(rows), 2) if rows else 0,
                            "average_boundary": round(sum(x["difficulty_dimension_3"] for x in rows)/len(rows), 2) if rows else 0,
                            "average_similarity": round(sum(x["difficulty_dimension_5"] for x in rows)/len(rows), 2) if rows else 0,
                            "average_related_distractors": round(sum(x["high_related_distractor_count"] for x in rows)/len(rows), 2) if rows else 0,
                            "needs_review_count": sum(x["reference_basis_status"] != "verified" for x in rows)})

    target_counts = Counter(x["correct_department_name"] for x in candidates)
    for item in candidates:
        basis_points = {"verified": 35, "needs_review": 18, "insufficient": 0, "conflict": -40}[item["reference_basis_status"]]
        item["final_selection_score"] = round(basis_points + min(20, item["quality_score"]/5) + min(18, item["difficulty_dimension_2"]+5)
                                                     + min(15, item["difficulty_dimension_3"]) + min(12, item["high_related_distractor_count"]*4)
                                                     + (8 if target_counts[item["correct_department_name"]] <= 3 else 4), 2)
        item["final_recommendation"] = "candidate"
    recommended = []
    recommended_target_counts = Counter()
    for level in range(1, 11):
        rows = sorted([x for x in candidates if x["suggested_level"] == level and x["reference_basis_status"] in {"verified", "needs_review"}],
                      key=lambda x: (-x["final_selection_score"], x["source_case_id"]))
        chosen = []
        for item in rows:
            if recommended_target_counts[item["correct_department_name"]] >= 5: continue
            chosen.append(item); recommended_target_counts[item["correct_department_name"]] += 1
            if len(chosen) == 13: break
        # Preserve 12--14 review choices per level. If the cross-level diversity cap
        # leaves a level short, fill from the remaining evidence-usable rows; the
        # source candidate pool already limits every target to seven cases.
        if len(chosen) < min(13, len(rows)):
            chosen_ids = {item["source_case_id"] for item in chosen}
            for item in rows:
                if item["source_case_id"] in chosen_ids: continue
                chosen.append(item); chosen_ids.add(item["source_case_id"])
                recommended_target_counts[item["correct_department_name"]] += 1
                if len(chosen) == min(13, len(rows)): break
        for item in chosen: item["final_recommendation"] = "recommended"
        recommended.extend(chosen)
    reject = [x for x in candidates if x["reference_basis_status"] == "conflict" or x["final_selection_score"] < 35]
    for item in reject: item["final_recommendation"] = "suggest_reject"
    status_counts = Counter(x["reference_basis_status"] for x in candidates)
    summary = {"candidate_count": len(candidates), "canonical_target_count": len(target_meta),
               "alias_record_count": len(alias_rows), "corrected_alias_count": sum(x["alias_status"] == "corrected" for x in alias_rows),
               "reference_basis_status": {k: status_counts.get(k, 0) for k in ("verified", "needs_review", "insufficient", "conflict")},
               "evidence_pool_record_count": len(evidence_pool), "distractor_replacement_count": option_replacements,
               "suggested_level_adjustment_count": adjusted, "recommended_count": len(recommended),
               "suggested_reject_count": len(reject), "level_stats": level_stats,
               "note": "recommended不是approved；正式100题仍需人工确认职责依据、唯一答案和每关10题。"}
    candidates.sort(key=lambda x: (x["suggested_level"], -x["final_selection_score"], x["source_case_id"]))
    write_rows(args.output / "candidates_finalized", candidates)
    write_rows(args.output / "dispatch_target_alias_review", alias_rows)
    write_rows(args.output / "evidence_pool", list(evidence_pool.values()))
    write_rows(args.output / "level_statistics", level_stats)
    write_rows(args.output / "recommended_pool", recommended)
    write_rows(args.output / "suggested_rejections", reject)
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
