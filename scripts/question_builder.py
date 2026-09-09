"""Build reviewable dispatch-training question candidates from historical cases.

This command never writes the training database. It produces JSON/CSV artifacts
that must be reviewed before the approved-only import step.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path


BLOCK_PATTERN = re.compile(r"(?m)^##\s+(.+?)\s*$\n(.*?)(?=^---\s*$|\Z)", re.S)
FIELD_PATTERN = re.compile(r"【([^】]+)】\s*\n(.*?)(?=\n\s*【|\Z)", re.S)
MULTI_DEPARTMENT_PATTERN = re.compile(r"[、,，;/；]|\n")
DISPUTE_TERMS = ("多次退单", "反复退单", "责任不明", "无法确定责任", "主办", "协办")
DIMENSION_NAMES = (
    "诉求明确度", "承办部门唯一性判断难度", "职责边界复杂度", "信息判断难度", "易错部门相似度"
)


@dataclass
class RawCase:
    source_case_id: str
    source_file: str
    title: str
    request_type: str
    message_time: str
    case_content: str
    actual_department_raw: str


def normalize(value: str) -> str:
    return re.sub(r"\s+", "", value or "").strip()


def clean_field(value: str) -> str:
    lines = [line.strip() for line in value.strip().splitlines()]
    while lines and re.fullmatch(r"[-—–_]+", lines[-1]):
        lines.pop()
    return "\n".join(lines).strip()


def parse_original_files(source_dir: Path) -> list[RawCase]:
    records: list[RawCase] = []
    for path in sorted(source_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for title, body in BLOCK_PATTERN.findall(text):
            fields = {key.strip(): clean_field(value) for key, value in FIELD_PATTERN.findall(body)}
            stable = hashlib.sha256((path.name + "\n" + title + "\n" + body).encode()).hexdigest()[:16]
            records.append(RawCase(
                source_case_id=f"HC-{stable}", source_file=path.name, title=title.strip(),
                request_type=fields.get("诉求类型", "").strip(),
                message_time=fields.get("留言时间", "").strip(),
                case_content=fields.get("事项内容", "").strip(),
                actual_department_raw=fields.get("实际承办单位", "").strip(),
            ))
    return records


def clean_asset_name(name: str) -> str:
    suffixes = ("__拆分", "_行政处罚", "_行政许可", "_行政强制", "_行政检查", "_行政确认", "_行政裁决", "_其他行政权力")
    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
                changed = True
                break
    return name


def collect_department_master(asset_root: Path) -> list[dict]:
    names: dict[str, set[str]] = defaultdict(set)
    responsibilities = asset_root / "knowledge-source" / "02_权责清单"
    if responsibilities.is_dir():
        for child in sorted(responsibilities.iterdir()):
            name = normalize(clean_asset_name(child.stem if child.suffix == ".md" else child.name))
            if name and "白云区" in name and name not in {"疑似数据异常", "白云区政府部门职责明细"}:
                names[name].add(str(child))
    street_dir = asset_root / "knowledge-source" / "01_机构职责" / "白云区镇街机构职能和机构设置__拆分"
    if street_dir.is_dir():
        for path in sorted(street_dir.glob("*.md")):
            first = path.read_text(encoding="utf-8").splitlines()
            match = re.match(r"^#\s+(.+)$", first[0]) if first else None
            if match and len(match.group(1).strip()) <= 30:
                names[f"广州市白云区人民政府-{normalize(match.group(1))}"].add(str(street_dir))
    return [{
        "department_code": "DEPT-" + hashlib.sha1(name.encode()).hexdigest()[:16],
        "department_name": name,
        "source_paths": sorted(paths),
        "department_kind": "street" if "人民政府-" in name else "bureau",
    } for name, paths in sorted(names.items())]


def map_department(raw: str, master: list[dict]) -> tuple[dict | None, str]:
    normalized = normalize(raw)
    if not normalized:
        return None, "missing_department"
    if MULTI_DEPARTMENT_PATTERN.search(normalized):
        return None, "multiple_departments"
    exact = [item for item in master if normalize(item["department_name"]) == normalized]
    if len(exact) == 1:
        return exact[0], "exact"
    contained = [item for item in master if normalize(item["department_name"]) in normalized or normalized in normalize(item["department_name"])]
    if len(contained) == 1:
        return contained[0], "contained_unique"
    return None, "ambiguous_department_mapping" if len(contained) > 1 else "department_not_in_master"


def filter_case(case: RawCase, master: list[dict]) -> tuple[dict | None, str | None]:
    if not case.case_content or len(normalize(case.case_content)) < 30:
        return None, "case_content_missing_or_too_short"
    if not case.actual_department_raw:
        return None, "missing_final_department"
    if any(term in case.case_content or term in case.title for term in DISPUTE_TERMS):
        return None, "possible_dispute_or_complex_collaboration"
    department, method = map_department(case.actual_department_raw, master)
    if not department:
        return None, method
    return {**asdict(case), **department, "department_match_method": method}, None


def difficulty(item: dict) -> tuple[list[int], list[str]]:
    content = item["case_content"]
    field_count = sum(1 for line in content.splitlines() if ":" in line or "：" in line)
    implicit = 14 if not any(x in content for x in ("希望相关部门", "诉求内容", "具体问题")) else 8
    uniqueness = 12 if item["department_match_method"] == "contained_unique" else 7
    boundary = 14 if any(x in content for x in ("道路", "小区", "施工", "经营", "噪声", "违建")) else 8
    information = min(20, 6 + min(field_count, 7) * 2)
    similarity = 15 if item["department_kind"] == "bureau" else 13
    scores = [implicit, uniqueness, boundary, information, similarity]
    reasons = [
        "题面需从多字段中识别核心诉求" if implicit >= 12 else "题面直接描述了具体问题或处理诉求",
        "承办单位需经过唯一包含映射确认" if uniqueness >= 10 else "历史承办单位与主数据精确匹配",
        "涉及道路、小区、施工、经营、噪声或违建等常见职责交叉场景" if boundary >= 12 else "事项职责交叉信号较少",
        f"需综合判断的结构化事项字段约{field_count}项",
        "同层级部门较多，存在相近职责干扰项" if similarity >= 15 else "镇街之间职责相似但属地信息可辅助判断",
    ]
    return scores, reasons


def choose_distractors(item: dict, master: list[dict], score: int) -> list[dict]:
    candidates = [x for x in master if x["department_code"] != item["department_code"]]
    same_kind = [x for x in candidates if x["department_kind"] == item["department_kind"]]
    other = [x for x in candidates if x["department_kind"] != item["department_kind"]]
    seed = int(hashlib.sha256(item["source_case_id"].encode()).hexdigest()[:8], 16)
    same_kind.sort(key=lambda x: hashlib.sha256(f"{seed}:{x['department_code']}".encode()).hexdigest())
    other.sort(key=lambda x: hashlib.sha256(f"{seed}:{x['department_code']}".encode()).hexdigest())
    preferred = (same_kind + other) if score >= 40 else (other + same_kind)
    return preferred[:3]


def build_candidates(eligible: list[dict], master: list[dict], count: int) -> list[dict]:
    by_type: dict[str, list[dict]] = defaultdict(list)
    for item in eligible:
        by_type[item["request_type"] or "未知"].append(item)
    selected: list[dict] = []
    keys = sorted(by_type)
    while len(selected) < count and any(by_type.values()):
        for key in keys:
            if by_type[key] and len(selected) < count:
                selected.append(by_type[key].pop(0))
    output = []
    for index, item in enumerate(selected):
        scores, reasons = difficulty(item)
        total = sum(scores)
        wrong = choose_distractors(item, master, total)
        if len(wrong) != 3:
            continue
        suggested_level = max(1, min(10, (total - 1) // 10 + 1))
        record = {
            "source_case_id": item["source_case_id"], "source_file": item["source_file"],
            "case_title": item["title"], "case_content": item["case_content"],
            "correct_department_id": item["department_code"],
            "correct_department_name": item["department_name"],
            "wrong_department_1": wrong[0]["department_name"], "wrong_department_1_id": wrong[0]["department_code"],
            "wrong_department_2": wrong[1]["department_name"], "wrong_department_2_id": wrong[1]["department_code"],
            "wrong_department_3": wrong[2]["department_name"], "wrong_department_3_id": wrong[2]["department_code"],
            "explanation": f"核心诉求：{item['title']}\n\n责任判断：该历史案例记录的唯一实际承办单位为{item['department_name']}。\n\n正确承办部门：{item['department_name']}\n\n参考依据：具体职责条款待人工复核。",
            "reference_basis": "历史工单实际承办记录；具体职责依据待结合权责清单人工复核。",
            "reference_basis_status": "needs_review", "difficulty_score": total,
            "suggested_level": suggested_level,
            "question_type": "challenge" if index < 10 else "practice",
            "review_status": "pending", "review_note": "",
        }
        for number, (value, reason) in enumerate(zip(scores, reasons), 1):
            record[f"difficulty_dimension_{number}"] = value
            record[f"difficulty_dimension_{number}_reason"] = reason
        output.append(record)
    return output


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    fields = fields or sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--asset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample-size", type=int, default=25)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    raw = parse_original_files(args.source)
    master = collect_department_master(args.asset_root)
    eligible, excluded = [], []
    for item in raw:
        accepted, reason = filter_case(item, master)
        if accepted:
            eligible.append(accepted)
        else:
            excluded.append({"source_case_id": item.source_case_id, "source_file": item.source_file,
                             "case_title": item.title, "actual_department_raw": item.actual_department_raw,
                             "exclude_reason": reason})
    candidates = build_candidates(eligible, master, args.sample_size)
    summary = {
        "source_files": len(list(args.source.glob("*.md"))), "raw_case_count": len(raw),
        "eligible_count": len(eligible), "excluded_count": len(excluded),
        "test_candidate_count": len(candidates),
        "exclude_reasons": dict(Counter(x["exclude_reason"] for x in excluded)),
        "eligible_departments": dict(Counter(x["department_name"] for x in eligible)),
    }
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output / "candidates.json").write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output / "departments.json").write_text(json.dumps(master, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(args.output / "candidates.csv", candidates)
    write_csv(args.output / "excluded.csv", excluded)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
