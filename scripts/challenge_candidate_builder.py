"""Build a review-only pool of formal challenge-question candidates.

Input is the strict eligible output of department_governance_full.py. The
script does not write the application database and never marks a question as
approved.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict, deque
from pathlib import Path


BOUNDARY_TERMS = ("违建", "施工", "道路", "停车", "噪声", "排水", "物业", "市场", "学校", "医疗", "社保", "规划", "燃气", "供电", "地铁", "公交", "环卫", "占道")
REQUEST_TERMS = ("咨询", "投诉", "举报", "求助", "建议", "反映", "要求", "希望")
GENERIC_TITLE_TERMS = ("其他", "咨询问题", "反映问题", "求助问题")
BUSINESS_FAMILIES = {
    "construction": ("住房", "建设", "规划", "城管", "执法", "交通", "排水", "水务"),
    "public_order": ("公安", "消防", "应急", "市场监督"),
    "public_service": ("供电", "地铁", "自来水", "排水", "公共交通", "公交", "集团", "公司"),
    "livelihood": ("教育", "民政", "人力资源", "医保", "卫生", "农业"),
}


def compact(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def ngrams(value: str, size: int = 3) -> set[str]:
    value = re.sub(r"[\W_]+", "", value)
    return {value[i:i + size] for i in range(max(0, len(value) - size + 1))}


def similarity(left: str, right: str) -> float:
    a, b = ngrams(left), ngrams(right)
    return len(a & b) / len(a | b) if a and b else 0.0


def quality_score(case: dict) -> int:
    text = compact(case["case_content"])
    score = 60
    score += min(18, len(text) // 45)
    score += 6 if any(x in text for x in ("地址", "地点", "白云区")) else 0
    score += 4 if len(case.get("case_title", "")) >= 6 else 0
    score -= 12 if len(text) > 1800 else 6 if len(text) > 1200 else 0
    score -= 6 if any(x == case.get("case_title", "") for x in GENERIC_TITLE_TERMS) else 0
    return max(0, min(100, score))


def target_family(name: str, org_type: str) -> str:
    if org_type in {"subdistrict", "town"}: return "territorial"
    for family, terms in BUSINESS_FAMILIES.items():
        if any(term in name for term in terms): return family
    return "other_department"


def option_equivalence_key(name: str) -> str:
    return compact(name).removeprefix("广州市").replace("人民政府-", "").replace("和", "")


def select_balanced(eligible: list[dict], count: int, per_target_cap: int) -> tuple[list[dict], list[dict]]:
    ranked = sorted(eligible, key=lambda x: (-quality_score(x), x["source_case_id"]))
    deduped, duplicate_rows = [], []
    by_target_texts: dict[str, list[str]] = defaultdict(list)
    for case in ranked:
        text = case["case_title"] + case["case_content"]
        prior = by_target_texts[case["canonical_dispatch_target"]]
        max_similarity = max((similarity(text, old) for old in prior), default=0.0)
        if max_similarity >= 0.86:
            duplicate_rows.append({"source_case_id": case["source_case_id"], "canonical_dispatch_target": case["canonical_dispatch_target"], "duplicate_similarity": round(max_similarity, 3)})
            continue
        prior.append(text); deduped.append(case)
    groups: dict[str, deque] = defaultdict(deque)
    for case in deduped: groups[case["canonical_dispatch_target"]].append(case)
    selected = []
    targets = sorted(groups, key=lambda x: (-len(groups[x]), x))
    used = Counter()
    while len(selected) < count:
        progressed = False
        for target in targets:
            if groups[target] and used[target] < per_target_cap and len(selected) < count:
                selected.append(groups[target].popleft()); used[target] += 1; progressed = True
        if not progressed: break
    if len(selected) < count:
        raise SystemExit(f"平衡及去重后只能选出{len(selected)}题，少于要求的{count}题")
    return selected, duplicate_rows


def dimension_scores(case: dict) -> tuple[list[int], list[str]]:
    text = compact(case["case_content"])
    title = case.get("case_title", "")
    org_type = case["organization_type"]
    boundary_hits = [term for term in BOUNDARY_TERMS if term in text]
    field_count = len(re.findall(r"(?:时间|地点|地址|诉求|问题|对象|联系电话)[:：]", case["case_content"]))
    clarity = min(20, 7 + (5 if len(text) > 500 else 3 if len(text) > 250 else 1) + (4 if title in GENERIC_TITLE_TERMS else 0) + min(5, text.count("，") // 4))
    uniqueness = 7 if org_type in {"subdistrict", "town"} and case["canonical_dispatch_target"].split("-")[-1] in text else 13
    uniqueness += min(7, max(0, len(boundary_hits) - 1) * 2)
    boundary = min(20, 7 + len(boundary_hits) * 3 + (3 if org_type == "district_department" else 1))
    information = min(20, 7 + min(7, field_count) + min(8, len(text) // 160))
    similarity_score = 16 if org_type in {"subdistrict", "town"} else 18 if target_family(case["canonical_dispatch_target"], org_type) != "other_department" else 13
    scores = [clarity, min(20, uniqueness), boundary, information, similarity_score]
    reasons = [
        f"题面长度约{len(text)}字，核心诉求{'需从较长描述中提取' if clarity >= 11 else '相对直接'}。",
        f"历史记录为单一承办单位；{'属地名称可直接辅助判断' if uniqueness <= 8 else '仍需区分相近职责或事项属性'}。",
        f"识别到{len(boundary_hits)}个职责交叉信号" + (f"：{'、'.join(boundary_hits[:4])}。" if boundary_hits else "，职责边界信号较少。"),
        f"题面包含约{field_count}个显式信息字段，需结合事项主体、地点和行为判断。",
        "同类镇街容易混淆，需依赖属地信息排除。" if org_type in {"subdistrict", "town"} else "正确单位与同业务领域承办单位存在职责相似性。" if similarity_score >= 15 else "可选单位间职责相似度相对有限。",
    ]
    return scores, reasons


def relatedness(correct: dict, candidate: dict) -> tuple[int, str]:
    if correct["canonical_dispatch_target"] == candidate["canonical_dispatch_target"]: return (-99, "same")
    same_type = correct["organization_type"] == candidate["organization_type"]
    same_family = target_family(correct["canonical_dispatch_target"], correct["organization_type"]) == target_family(candidate["canonical_dispatch_target"], candidate["organization_type"])
    score = (4 if same_family else 0) + (3 if same_type else 0)
    seed = hashlib.sha256((correct["source_case_id"] + candidate["canonical_dispatch_target"]).encode()).hexdigest()
    return score, seed


def choose_distractors(case: dict, targets: list[dict], tier: int) -> tuple[list[dict], str]:
    correct_key = option_equivalence_key(case["canonical_dispatch_target"])
    candidates = sorted([x for x in targets if option_equivalence_key(x["canonical_dispatch_target"]) != correct_key],
                        key=lambda x: relatedness(case, x), reverse=True)
    related = [x for x in candidates if relatedness(case, x)[0] >= 3]
    unrelated = sorted([x for x in candidates if relatedness(case, x)[0] < 3], key=lambda x: relatedness(case, x)[1])
    if tier <= 3:
        pool, label = unrelated, "基础排除型"
    elif tier <= 6:
        pool, label = related[:2] + unrelated + related[2:], "关联辨析型"
    else:
        pool, label = related + unrelated, "高相似混淆型"
    chosen, keys = [], set()
    for item in pool:
        key = option_equivalence_key(item["canonical_dispatch_target"])
        if key not in keys:
            chosen.append(item); keys.add(key)
        if len(chosen) == 3: break
    return chosen, label


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eligible", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=180)
    parser.add_argument("--per-target-cap", type=int, default=7)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    eligible = json.loads(args.eligible.read_text(encoding="utf-8"))
    eligible = [x for x in eligible if x["case_status"] == "eligible"]
    selected, duplicates = select_balanced(eligible, args.count, args.per_target_cap)
    target_by_name = {}
    for case in eligible:
        target_by_name[case["canonical_dispatch_target"]] = {
            "source_case_id": case["source_case_id"], "canonical_dispatch_target": case["canonical_dispatch_target"],
            "dispatch_target_code": case["dispatch_target_code"], "organization_type": case["organization_type"],
        }
    targets = list(target_by_name.values())
    scored = []
    for case in selected:
        scores, reasons = dimension_scores(case)
        scored.append((sum(scores), quality_score(case), case, scores, reasons))
    scored.sort(key=lambda x: (x[0], x[1], x[2]["source_case_id"]))
    candidates = []
    per_level = math.ceil(len(scored) / 10)
    for index, (total, quality, case, scores, reasons) in enumerate(scored):
        level = min(10, index // per_level + 1)
        wrong, distractor_label = choose_distractors(case, targets, level)
        if len(wrong) != 3: raise SystemExit(f"{case['source_case_id']}: 干扰项不足3个")
        if len({option_equivalence_key(x["canonical_dispatch_target"]) for x in wrong}) != 3:
            raise SystemExit(f"{case['source_case_id']}: 干扰项存在等价名称")
        core_issue = case["case_title"].strip() or compact(case["case_content"])[:60]
        correct = case["canonical_dispatch_target"]
        responsibility = f"该案例地点明确属于白云区，历史记录的单一实际承办单位规范化为{correct}；具体职责边界仍需业务人员结合权威职责材料复核。"
        explanation = f"核心诉求：{core_issue}\n\n责任判断：{responsibility}\n\n正确承办单位：{correct}\n\n参考依据：历史工单实际承办记录；具体职责依据待人工核验。"
        record = {
            "source_case_id": case["source_case_id"], "source_file": case["source_file"],
            "case_title": case["case_title"], "case_content": case["case_content"],
            "correct_department_id": case["dispatch_target_code"], "correct_department_name": correct,
            "wrong_department_1_id": wrong[0]["dispatch_target_code"], "wrong_department_1": wrong[0]["canonical_dispatch_target"],
            "wrong_department_2_id": wrong[1]["dispatch_target_code"], "wrong_department_2": wrong[1]["canonical_dispatch_target"],
            "wrong_department_3_id": wrong[2]["dispatch_target_code"], "wrong_department_3": wrong[2]["canonical_dispatch_target"],
            "core_issue": core_issue, "responsibility_reasoning": responsibility,
            "correct_dispatch_target": correct, "explanation": explanation,
            "reference_basis": "历史工单实际承办记录；具体职责依据待结合机构职责或权责清单人工核验。",
            "reference_basis_status": "needs_review", "difficulty_score": total,
            "distractor_difficulty": distractor_label, "suggested_level": level,
            "question_type": "challenge", "quality_score": quality,
            "issue_status": "difficult_review" if total >= 68 or level >= 9 else "normal",
            "review_status": "pending", "review_note": "",
        }
        for number, (value, reason) in enumerate(zip(scores, reasons), 1):
            record[f"difficulty_dimension_{number}"] = value
            record[f"difficulty_dimension_{number}_reason"] = reason
        candidates.append(record)
    candidates.sort(key=lambda x: (x["suggested_level"], x["difficulty_score"], x["source_case_id"]))
    distribution = Counter(x["correct_department_name"] for x in candidates)
    level_counts = Counter(x["suggested_level"] for x in candidates)
    difficulty_bands = Counter("基础(0-39)" if x["difficulty_score"] < 40 else "中等(40-59)" if x["difficulty_score"] < 60 else "较难(60-74)" if x["difficulty_score"] < 75 else "高难(75-100)" for x in candidates)
    summary = {
        "strict_eligible_input": len(eligible), "candidate_count": len(candidates),
        "per_target_cap": args.per_target_cap, "duplicate_excluded_count": len(duplicates),
        "candidate_target_count": len(distribution), "target_distribution": dict(distribution.most_common()),
        "difficulty_band_distribution": dict(difficulty_bands), "suggested_level_distribution": {str(i): level_counts[i] for i in range(1, 11)},
        "difficulty_summary": {
            **{f"dimension_{i}": {"min": min(x[f"difficulty_dimension_{i}"] for x in candidates),
                                  "average": round(sum(x[f"difficulty_dimension_{i}"] for x in candidates) / len(candidates), 2),
                                  "max": max(x[f"difficulty_dimension_{i}"] for x in candidates)} for i in range(1, 6)},
            "total": {"min": min(x["difficulty_score"] for x in candidates),
                      "average": round(sum(x["difficulty_score"] for x in candidates) / len(candidates), 2),
                      "max": max(x["difficulty_score"] for x in candidates)},
        },
        "reference_basis_needs_review_count": sum(x["reference_basis_status"] == "needs_review" for x in candidates),
        "difficult_review_count": sum(x["issue_status"] == "difficult_review" for x in candidates),
        "selection_note": "按承办单位轮转、单单位最多7题，并在同单位内剔除三字片段相似度>=0.86的近重复案例。",
    }
    distribution_rows, running = [], 0
    for target, count in distribution.most_common():
        running += count
        distribution_rows.append({"canonical_dispatch_target": target, "candidate_count": count,
                                  "share": count / len(candidates), "cumulative_share": running / len(candidates)})
    outputs = {"candidates": candidates, "target_distribution": distribution_rows, "duplicate_exclusions": duplicates}
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, rows in outputs.items():
        (args.output / f"{name}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        if rows:
            with (args.output / f"{name}.csv").open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
