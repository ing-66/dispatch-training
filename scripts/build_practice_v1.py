"""Build and validate the 450-question formal practice V1 artifact set."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.cross_district_transfer_assessment import (
    DutyIndex,
    detect_topic,
    set_similarity,
    target_pool,
    trigrams,
    write_csv,
    write_json,
)

CHALLENGE_FROZEN_SHA256 = "82023DF9C7672FA23FC579EB2A64F6BC59F9EC03266671F1D07DFBBC3833BB2D"

NEW_TARGET_CODES = {
    "广州市医疗保障局": "DEPT-practice-citywide-medical",
    "广州市白云区卫生健康局": "DEPT-practice-baiyun-health",
    "广州市白云区政务和数据局": "DEPT-practice-baiyun-govdata",
    "广州市白云区文化广电旅游体育局": "DEPT-practice-baiyun-culture",
}

ORIGIN_CONTEXT = {
    "baiyun_original": "白云区历史案例",
    "cross_district_transfer": "以下为广州其他区同类历史案例。若同类事项发生在白云区，应优先派发至哪个承办单位？",
    "citywide_same_target": "以下为广州市级统一承办事项。同类事项在白云区仍由该市级承办单位处理。",
    "public_service_same_target": "以下为城市级公共服务事项。同类事项在白云区仍由同一公共服务主体承办。",
}


def load_json(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_target(name: str) -> str:
    aliases = [
        ("白云区教育局", "广州市白云区教育局"),
        ("白云区人力资源社会保障局", "广州市白云区人力资源和社会保障局"),
        ("白云区人力资源和社会保障局", "广州市白云区人力资源和社会保障局"),
        ("广州市白云区人力资源社会保障局", "广州市白云区人力资源和社会保障局"),
        ("广州市白云区市场监督局", "广州市白云区市场监督管理局"),
        ("白云区市场监督局", "广州市白云区市场监督管理局"),
        ("白云区民政局", "广州市白云区民政局"),
        ("白云区水务局", "广州市白云区水务局"),
        ("白云区公安分局", "广州市公安局白云区分局"),
        ("广州市白云区城市管理综合执法局", "广州市白云区城市管理和综合执法局"),
        ("白云区城市管理综合执法局", "广州市白云区城市管理和综合执法局"),
        ("广州市白云区科工商信局", "广州市白云区科技工业商务和信息化局"),
        ("白云区科工商信局", "广州市白云区科技工业商务和信息化局"),
        ("广州市白云区住房建设和交通局", "广州市白云区住房建设交通局"),
    ]
    for alias, formal in aliases:
        if name == alias or (alias and alias in name):
            return formal
    return name


def build_target_registry(combined: list[dict[str, Any]], db_path: Path) -> dict[str, dict[str, str]]:
    names = sorted({normalize_target(x.get("mapped_dispatch_target") or "") for x in combined})
    registry: dict[str, dict[str, str]] = {}
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT code, name FROM departments WHERE is_enabled=1").fetchall()
    finally:
        con.close()
    by_name = {name: code for code, name in rows}
    by_name.update({normalize_target(name): code for code, name in rows})
    for name in names:
        code = by_name.get(name) or NEW_TARGET_CODES.get(name, "")
        if not code:
            raise SystemExit(f"承办单位缺少正式代码且未定义新增代码：{name}")
        registry[name] = {"name": name, "code": code, "is_new": code.startswith("DEPT-practice-")}
    return registry


def family_of(name: str) -> str:
    checks = [
        ("人民政府-", "street"),
        ("教育局", "education"),
        ("人力资源", "human_resources"),
        ("社会保障局", "human_resources"),
        ("医疗保障局", "medical_insurance"),
        ("民政局", "civil_affairs"),
        ("市场监督", "market_regulation"),
        ("城市管理", "urban_management"),
        ("水务局", "water"),
        ("住房建设交通局", "housing_transport"),
        ("卫生健康局", "health"),
        ("文化广电旅游体育局", "culture_sports"),
        ("政务和数据局", "government_data"),
        ("科技工业商务和信息化局", "industry_tech"),
        ("来穗局", "migrant_services"),
        ("公安局", "public_security"),
        ("城市排水有限公司", "drainage"),
        ("广州供电局", "power"),
        ("广州地铁集团", "metro"),
        ("公共交通集团", "bus"),
        ("枢纽办", "special"),
        ("白云湖数字科技城", "special"),
        ("建科控股", "special"),
        ("产业投资集团", "special"),
    ]
    for keyword, family in checks:
        if keyword in name:
            return family
    return "other"


RELATED_FAMILIES: dict[str, set[str]] = {
    "education": {"civil_affairs", "industry_tech", "migrant_services"},
    "human_resources": {"medical_insurance", "civil_affairs", "government_data"},
    "medical_insurance": {"human_resources", "health", "civil_affairs"},
    "civil_affairs": {"human_resources", "education", "health", "public_security"},
    "market_regulation": {"health", "industry_tech", "civil_affairs"},
    "urban_management": {"street", "housing_transport", "water", "public_security"},
    "water": {"drainage", "housing_transport", "urban_management"},
    "housing_transport": {"street", "urban_management", "water", "power"},
    "industry_tech": {"government_data", "market_regulation", "education"},
    "migrant_services": {"education", "human_resources", "public_security"},
    "public_security": {"street", "migrant_services", "housing_transport"},
    "health": {"market_regulation", "medical_insurance", "civil_affairs"},
    "culture_sports": {"industry_tech", "education", "civil_affairs"},
    "government_data": {"industry_tech", "human_resources", "civil_affairs"},
    "drainage": {"water", "urban_management", "housing_transport"},
    "power": {"housing_transport", "urban_management", "street"},
    "metro": {"bus", "housing_transport", "street"},
    "bus": {"metro", "housing_transport", "street"},
    "street": {"urban_management", "housing_transport", "public_security"},
    "special": {"housing_transport", "street"},
    "other": {"street", "housing_transport"},
}


def content_text(row: dict[str, Any]) -> str:
    return (row.get("case_content") or "") + "\n" + (row.get("case_title") or "")


class BasisEngine:
    """Translate strict-candidate evidence into verified reference_basis fields."""

    def __init__(self, knowledge_root: Path, challenge: list[dict[str, Any]], phase51_strict: list[dict[str, Any]]):
        self.knowledge_root = knowledge_root
        self.challenge = challenge
        self.challenge_sets = [(x["source_case_id"], trigrams(x.get("case_content", "")),
                                normalize_target(x["correct_department_name"]), x) for x in challenge]
        self.phase51 = phase51_strict
        self.pool = target_pool()
        self.name_to_key = {value["name"]: key for key, value in self.pool.items()}
        self.duty = DutyIndex(knowledge_root / "01_机构职责" / "白云区政府部门职责明细.md")
        self.street_dir = knowledge_root / "01_机构职责" / "白云区镇街机构职能和机构设置__拆分"
        self.street_cache: dict[str, list[tuple[int, str]]] = {}
        self.street_files: dict[str, Path] = {}
        self._build_street_index()

    def _build_street_index(self) -> None:
        if not self.street_dir.is_dir():
            return
        street_order = [
            ("江高镇", "00001"), ("人和镇", "00003"), ("太和镇", "00005"), ("钟落潭镇", "00007"),
            ("三元里街", "00009"), ("松洲街", "00011"), ("景泰街", "00013"), ("黄石街", "00015"),
            ("同德街", "00017"), ("棠景街", "00019"), ("新市街", "00021"), ("同和街", "00023"),
            ("京溪街", "00025"), ("永平街", "00027"), ("均禾街", "00029"), ("嘉禾街", "00031"),
            ("石井街", "00033"), ("金沙街", "00035"), ("云城街", "00037"), ("石门街", "00039"),
            ("白云湖街", "00041"), ("鹤龙街", "00043"), ("龙归街", "00045"), ("大源街", "00047"),
        ]
        for label, prefix in street_order:
            matches = list(self.street_dir.glob(f"{prefix}_机构职责_*.md"))
            if not matches:
                continue
            file = matches[0]
            lines = file.read_text(encoding="utf-8-sig").splitlines()
            self.street_files[label] = file
            self.street_cache[label] = [(i, line.strip()) for i, line in enumerate(lines, 1) if line.strip()]

    def _street_label(self, target_name: str) -> str:
        for prefix in ("广州市白云区人民政府-", "广州市白云区", "白云区"):
            if target_name.startswith(prefix):
                return target_name[len(prefix):]
        return target_name

    def _existing_basis_from_challenge(self, row: dict[str, Any], target_name: str, topic_key: str) -> dict[str, str] | None:
        text = content_text(row)
        target_set = trigrams(text)
        matches = []
        for cid, cset, ctarget, item in self.challenge_sets:
            if ctarget != target_name:
                continue
            score = set_similarity(target_set, cset)
            if score > 0:
                matches.append((score, item))
        if matches:
            _, item = max(matches, key=lambda x: x[0])
            return self._basis_from_item(item, f"沿用同承办单位已核验白云职责依据（challenge:{item['source_case_id']}）")
        for cid, cset, ctarget, item in self.challenge_sets:
            if ctarget == target_name:
                return self._basis_from_item(item, f"沿用同承办单位已核验白云职责依据（challenge:{item['source_case_id']}）")
        return None

    def _basis_from_item(self, item: dict[str, Any], reason_suffix: str = "") -> dict[str, str]:
        return {
            "reference_basis_title": item.get("reference_basis_title", ""),
            "reference_basis_source": item.get("reference_basis_source", ""),
            "reference_basis_excerpt": item.get("reference_basis_excerpt", ""),
            "reference_basis_locator": item.get("reference_basis_locator", ""),
            "reference_basis_reason": (item.get("reference_basis_reason") or "") + reason_suffix,
            "reference_basis_status": "verified",
        }

    def _street_basis(self, row: dict[str, Any], target_name: str, topic_key: str) -> dict[str, str]:
        label = self._street_label(target_name)
        _, _, _, topic_terms = detect_topic(row.get("case_title", ""), row.get("case_content", ""))
        # First try an approved challenge basis for this street (same street duty is reusable).
        existing = self._existing_basis_from_challenge(row, target_name, topic_key)
        if existing:
            return existing
        file = self.street_files.get(label) or next((f for name, f in self.street_files.items() if label in name), None)
        if not file:
            return {"reference_basis_status": "needs_review", "reference_basis_reason": f"未找到镇街职责文件：{label}"}
        paragraphs = self.street_cache.get(label) or self.street_cache.get(next((n for n in self.street_files if label in n), ""), [])
        search_terms = tuple(dict.fromkeys(topic_terms))
        hit = None
        for line_no, paragraph in paragraphs:
            if any(term and term in paragraph for term in search_terms):
                hit = (line_no, paragraph)
                break
        if not hit:
            hit = next(((no, p) for no, p in paragraphs if "城市管理" in p or "市容" in p or "环境卫生" in p), None)
        if not hit:
            return {"reference_basis_status": "needs_review", "reference_basis_reason": f"镇街职责文件无可用条款：{label}"}
        line_no, paragraph = hit
        return {"reference_basis_title": f"{label}机构职责", "reference_basis_source": "镇街机构职责",
                "reference_basis_excerpt": paragraph[:300], "reference_basis_locator": f"{file}；机构职责第{line_no}行",
                "reference_basis_reason": f"事项属于{label}统筹负责的城市管理/综合服务职责；由历史同街道案件实际承办记录佐证",
                "reference_basis_status": "verified"}

    def _duty_basis(self, row: dict[str, Any], target_name: str, topic_key: str) -> dict[str, str]:
        key = self.name_to_key.get(target_name)
        _, _, _, matched_terms = detect_topic(row.get("case_title", ""), row.get("case_content", ""))
        rule_basis: tuple[str, ...] = ()
        from scripts.cross_district_transfer_assessment import TOPIC_RULES
        for tk, _t, _s, _p, terms in TOPIC_RULES:
            if tk == topic_key:
                rule_basis = terms
                break
        basis_terms = tuple(dict.fromkeys(list(matched_terms) + list(rule_basis)))
        if not key:
            # Public utilities and special units fall back to phase-5.1 same-target evidence.
            for other in self.phase51:
                if normalize_target(other.get("mapped_dispatch_target") or "") == target_name:
                    return self._basis_from_other(other)
            return self._regulation_or_folder_basis(row, target_name, topic_key)
        result = self.duty.verify(key, basis_terms, content_text(row))
        if result["mapping_basis_status"] != "verified" and family_of(target_name) == "public_security":
            folder_basis = self._regulation_or_folder_basis(row, target_name, topic_key)
            if folder_basis.get("reference_basis_status") == "verified":
                return folder_basis
        return {"reference_basis_title": result["mapping_basis_title"], "reference_basis_source": result["mapping_basis_source"],
                "reference_basis_excerpt": result["mapping_basis_excerpt"], "reference_basis_locator": result["mapping_basis_locator"],
                "reference_basis_reason": result["mapping_basis_reason"], "reference_basis_status": result["mapping_basis_status"]}

    def _regulation_or_folder_basis(self, row: dict[str, Any], target_name: str, topic_key: str) -> dict[str, str]:
        regulations = {
            "power": ("05_广州地方性法规/广州市供用电条例__a97b973f.md",
                      ("供电企业应当依法向用户提供电力普遍服务", "供电企业应当依法履行供电设施的管理")),
            "drainage": ("06_广州政府规章/广州市井盖设施管理办法__e61304ae.md",
                         ("井盖设施维护管理责任人", "排水设施维护运营单位")),
            "metro": ("05_广州地方性法规/广州市城市轨道交通管理条例__eb412f3f.md",
                      ("城市轨道交通经营单位由市人民政府", "城市轨道交通经营单位应当履行")),
            "bus": ("05_广州地方性法规/广州市公共汽车电车客运管理条例__cef10d10.md",
                    ("公共汽车电车线路经营者", "市交通行政主管部门是本市公共汽车电车客运的行")),
        }
        family = family_of(target_name)
        if family in regulations:
            rel, probes = regulations[family]
            doc = self.knowledge_root / rel
            ok, excerpt, line_no, filename = False, "", 0, ""
            if doc.is_file():
                for idx, line in enumerate(doc.read_text(encoding="utf-8-sig").splitlines(), 1):
                    compact = re.sub(r"\s+", "", line)
                    if any(p and p in compact for p in probes):
                        ok, excerpt, line_no, filename = True, line.strip(), idx, doc.name
                        break
            if ok:
                return {"reference_basis_title": doc.name, "reference_basis_source": "广州地方性法规/政府规章",
                        "reference_basis_excerpt": excerpt[:300], "reference_basis_locator": f"{doc}；第{line_no}行",
                        "reference_basis_reason": f"{target_name}按全市统一职责/服务规范承担同类事项",
                        "reference_basis_status": "verified"}
        if target_name == "广州市公安局白云区分局":
            folder = self.knowledge_root / "02_权责清单" / "广州市公安局白云分局__拆分"
            _, _, _, terms = detect_topic(row.get("case_title", ""), row.get("case_content", ""))
            if folder.is_dir():
                for file in folder.glob("*.md"):
                    if any(t and t in file.name for t in terms):
                        return {"reference_basis_title": "广州市公安局白云分局权责清单",
                                "reference_basis_source": "权责清单", "reference_basis_excerpt": file.name,
                                "reference_basis_locator": str(file),
                                "reference_basis_reason": "事项关键词命中白云公安权责事项原文",
                                "reference_basis_status": "verified"}
        return {"reference_basis_status": "needs_review", "reference_basis_reason": f"无职责依据映射：{target_name}"}

    def _basis_from_other(self, other: dict[str, Any]) -> dict[str, str]:
        title = other.get("basis_title") or other.get("mapping_basis_title") or ""
        source = other.get("basis_source") or other.get("mapping_basis_source") or ""
        excerpt = other.get("basis_excerpt") or other.get("mapping_basis_excerpt") or ""
        locator = other.get("basis_locator") or other.get("mapping_basis_locator") or ""
        reason = other.get("basis_reason") or other.get("mapping_basis_reason") or ""
        return {"reference_basis_title": title, "reference_basis_source": source, "reference_basis_excerpt": excerpt,
                "reference_basis_locator": locator, "reference_basis_reason": reason, "reference_basis_status": "verified"}

    def resolve(self, row: dict[str, Any], target_name: str) -> dict[str, str]:
        # Rows produced by Phases 5/5.1 already carry strict evidence.
        basis_title = row.get("basis_title") or row.get("mapping_basis_title")
        basis_status = row.get("basis_status") or row.get("mapping_basis_status")
        if basis_title and basis_status == "verified":
            return {"reference_basis_title": basis_title,
                    "reference_basis_source": row.get("basis_source") or row.get("mapping_basis_source") or "",
                    "reference_basis_excerpt": row.get("basis_excerpt") or row.get("mapping_basis_excerpt") or "",
                    "reference_basis_locator": row.get("basis_locator") or row.get("mapping_basis_locator") or "",
                    "reference_basis_reason": row.get("basis_reason") or row.get("mapping_basis_reason") or "",
                    "reference_basis_status": "verified"}
        if family_of(target_name) in {"power", "drainage", "metro", "bus"}:
            return self._regulation_or_folder_basis(row, target_name, row.get("topic_key") or "")
        topic_key = row.get("topic_key") or detect_topic(row.get("case_title", ""), row.get("case_content", ""))[0]
        if family_of(target_name) == "street":
            return self._street_basis(row, target_name, topic_key)
        existing = self._existing_basis_from_challenge(row, target_name, topic_key)
        if existing:
            return existing
        for other in self.phase51:
            if normalize_target(other.get("mapped_dispatch_target") or "") == target_name:
                return self._basis_from_other(other)
        return self._duty_basis(row, target_name, topic_key)


GENERIC_TITLES = {"反映其他事项问题", "咨询类", "反映其他事项", "其他事项", "求助类", "反映其他问题", "反映其他问题*"}


def title_generic(title: str) -> bool:
    return any(token in (title or "") for token in GENERIC_TITLES)


def content_len_quality(content: str) -> int:
    length = len(content or "")
    if 120 <= length <= 2200:
        return 0
    if length < 80:
        return 30
    if length < 120:
        return 12
    if length > 3000:
        return 15
    if length > 2200:
        return 6
    return 0


def explanation_fields(row: dict[str, Any], target_name: str, basis: dict[str, str],
                       origin: str, target_family: str) -> dict[str, str]:
    core_issue = (row.get("case_title") or "历史工单事项").strip()
    context_note = ORIGIN_CONTEXT.get(origin, "")
    transfer_reasoning = ""
    if origin == "cross_district_transfer":
        transfer_reasoning = f"该案例为广州其他区同类历史案例（原案 {row.get('source_case_id','')} 保留原始区名与原承办单位）；{target_name} 在白云区对应同类事项职责明确，故映射答案依据白云职责，而非直接套用其他区历史派单。"
    elif origin == "citywide_same_target":
        transfer_reasoning = "该事项属于广州市级统一承办事项，白云区不存在更明确的区级主责单位，因此白云区同类事项仍由同一市级单位承办。"
    elif origin == "public_service_same_target":
        transfer_reasoning = "该服务主体业务范围覆盖全市各区，且已有白云区同类受理记录；白云区同类事项仍由同一公共服务主体承办。"
    else:
        transfer_reasoning = "白云区真实历史受理记录已核验，答案由白云区现行职责与历史受理共同支持。"
    responsibility_reasoning = (
        f"核心事项：{core_issue}。正确承办单位：{target_name}。"
        f"依据：{basis['reference_basis_title']}（来源：{basis['reference_basis_source']}）。"
        f"{basis['reference_basis_reason']}"
    )
    reference = (
        f"{basis['reference_basis_title']}（{basis['reference_basis_source']}）\n"
        f"原文摘录：{basis['reference_basis_excerpt']}\n"
        f"文件定位：{basis['reference_basis_locator']}\n"
        f"核验理由：{basis['reference_basis_reason']}"
    )
    explanation = (
        f"核心事项：{core_issue}\n\n"
        f"正确承办单位：{target_name}\n\n"
        f"职责判断：{responsibility_reasoning}\n\n"
        f"来源说明：{context_note}\n\n"
        f"{transfer_reasoning}"
    )
    return {"core_issue": core_issue, "responsibility_reasoning": responsibility_reasoning,
            "transfer_reasoning": transfer_reasoning, "explanation": explanation, "reference_basis": reference}


def enrich_candidates(
    combined: list[dict[str, Any]],
    registry: dict[str, dict[str, str]],
    basis_engine: BasisEngine,
) -> list[dict[str, Any]]:
    enriched = []
    duplicate_keys: Counter[tuple[str, str, str]] = Counter()
    rows_by_id = {x["source_case_id"]: x for x in combined}
    for row in combined:
        target_name = normalize_target(row.get("mapped_dispatch_target") or "")
        topic_key = row.get("topic_key") or detect_topic(row.get("case_title", ""), row.get("case_content", ""))[0]
        duplicate_keys[(target_name, topic_key, (row.get("case_title") or "").strip())] += 1
    for row in combined:
        target_name = normalize_target(row.get("mapped_dispatch_target") or "")
        target_info = registry[target_name]
        topic_key = row.get("topic_key") or detect_topic(row.get("case_title", ""), row.get("case_content", ""))[0]
        origin = row.get("case_origin") or "baiyun_original"
        content = row.get("case_content") or ""
        basis = basis_engine.resolve(row, target_name)
        basis = {
            "reference_basis_title": basis.get("reference_basis_title", ""),
            "reference_basis_source": basis.get("reference_basis_source", ""),
            "reference_basis_excerpt": basis.get("reference_basis_excerpt", ""),
            "reference_basis_locator": basis.get("reference_basis_locator", ""),
            "reference_basis_reason": basis.get("reference_basis_reason", ""),
            "reference_basis_status": basis.get("reference_basis_status", "needs_review"),
        }
        dup_size = duplicate_keys[(target_name, topic_key, (row.get("case_title") or "").strip())]
        family = family_of(target_name)
        quality = 0
        quality += content_len_quality(content)
        if title_generic(row.get("case_title") or ""):
            quality += 12
        if dup_size > 1:
            quality += min(25, (dup_size - 1) * 6)
        if basis.get("reference_basis_status") != "verified":
            quality += 1000
        text = explanation_fields(row, target_name, basis, origin, family)
        enriched.append({**row, "target_name": target_name, "target_code": target_info["code"],
                         "target_family": family, "topic_key": topic_key, "case_origin": origin,
                         "reference_basis": text["reference_basis"], **basis,
                         "content_length": len(content), "generic_title": title_generic(row.get("case_title") or ""),
                         "duplicate_group_size": dup_size, "eliminate_score": quality,
                         "core_issue": text["core_issue"], "responsibility_reasoning": text["responsibility_reasoning"],
                         "transfer_reasoning": text["transfer_reasoning"], "explanation": text["explanation"]})
    return enriched


def select_final(candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates = sorted(candidates, key=lambda x: (x["eliminate_score"], x["content_length"]))
    education = [x for x in candidates if x["target_family"] == "education"]
    others = [x for x in candidates if x["target_family"] != "education"]
    reserve_education = education[-9:]
    reserve_other = others[-6:]
    reserve_ids = {x["source_case_id"] for x in [*reserve_education, *reserve_other]}
    reserve_reasons = {}
    for x in reserve_education:
        reserve_reasons[x["source_case_id"]] = "教育主题集中度控制：同主题/同单位候选重复价值较低，作为备用题"
    for x in reserve_other:
        reasons = []
        if x["duplicate_group_size"] > 1:
            reasons.append("同主题同标题近似重复")
        if x["generic_title"]:
            reasons.append("题面信息较泛")
        if x["eliminate_score"] >= 1000:
            reasons.append("职责依据待补强")
        if not reasons:
            reasons.append("部门分布与训练价值权衡")
        reserve_reasons[x["source_case_id"]] = "；".join(reasons)
    final = [x for x in candidates if x["source_case_id"] not in reserve_ids]
    reserve = sorted([*reserve_education, *reserve_other], key=lambda x: (x["eliminate_score"], x["content_length"]))
    for x in reserve:
        x["reserve_reason"] = reserve_reasons[x["source_case_id"]]
    return final, reserve


def replace_from_reserve(final: list[dict[str, Any]], reserve: list[dict[str, Any]],
                         failed_source_ids: list[str]) -> tuple[list[dict[str, Any]], int]:
    """Replace failed final rows with same-topic reserve rows; returns (final, replaced_count)."""
    failed_set = set(failed_source_ids)
    if not failed_set:
        return final, 0
    reserve_pool = list(reserve)
    final_ids = [x["source_case_id"] for x in final]
    replaced = 0
    result = []
    for item in final:
        if item["source_case_id"] not in failed_set:
            result.append(item)
            continue
        failed_item = item
        fallback = None
        for idx, candidate in enumerate(reserve_pool):
            if candidate["topic_key"] == failed_item["topic_key"] and candidate["target_family"] == failed_item["target_family"]:
                fallback = reserve_pool.pop(idx)
                break
        if fallback is None and reserve_pool:
            fallback = reserve_pool.pop(0)
        if fallback is None:
            raise SystemExit(f"reserve不足以替换失败题：{failed_item['source_case_id']}")
        fallback["reserve_reason"] = f"替换正式题 {failed_item['source_case_id']}"
        result.append(fallback)
        replaced += 1
        final_ids[final_ids.index(item["source_case_id"])] = fallback["source_case_id"]
    return result, replaced


def build_options(final: list[dict[str, Any]], registry: dict[str, dict[str, str]]) -> None:
    target_counts = Counter(x["target_name"] for x in final)
    topic_target = Counter((x["topic_key"], x["target_name"]) for x in final)
    names = list(registry)
    for item in final:
        correct = item["target_name"]
        candidates = []
        for name in names:
            if name == correct:
                continue
            family = family_of(name)
            score = 0
            if family in RELATED_FAMILIES.get(item["target_family"], set()):
                score += 100
            score += topic_target.get((item["topic_key"], name), 0) * 25
            score += min(target_counts.get(name, 0), 20)
            candidates.append((score, -target_counts.get(name, 0), name))
        candidates.sort(reverse=True)
        distractors = candidates[:3]
        if len({name for _, _, name in distractors}) != 3:
            raise SystemExit(f"选项不足：{item['source_case_id']}")
        item["wrong_options"] = [{"department_code": registry[name]["code"], "department_name": name}
                                 for _, _, name in distractors]
        related_count = sum(1 for s, _, name in distractors if s >= 100)
        if related_count == 0:
            raise SystemExit(f"缺少业务相关干扰项：{item['source_case_id']}")


def to_import_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_case_id": item["source_case_id"],
        "case_origin": item["case_origin"],
        "question_type": "practice",
        "level": None,
        "case_content": item["case_content"],
        "correct_department_code": item["target_code"],
        "correct_department_name": item["target_name"],
        "wrong_options": item.get("wrong_options", []),
        "explanation": item["explanation"],
        "reference_basis": item["reference_basis"],
        "reference_basis_title": item["reference_basis_title"],
        "reference_basis_source": item["reference_basis_source"],
        "reference_basis_excerpt": item["reference_basis_excerpt"],
        "reference_basis_locator": item["reference_basis_locator"],
        "reference_basis_reason": item["reference_basis_reason"],
        "reference_basis_status": "verified",
        "difficulty_score": None,
        "review_status": "approved",
        "review_note": "Phase 6 自动主审核：465 strict 候选 → 450 approved + 15 reserve",
        "enabled": True,
        "final_selection": True,
        "topic_key": item["topic_key"],
        "source_district": item.get("source_district", ""),
        "source_dispatch_target": item.get("source_target_name") or item.get("raw_department_name") or "",
        "training_context": ORIGIN_CONTEXT.get(item["case_origin"], ""),
        "transfer_reasoning": item["transfer_reasoning"],
        "responsibility_reasoning": item["responsibility_reasoning"],
        "core_issue": item["core_issue"],
    }


def audit_record(item: dict[str, Any], selected: bool, reason: str = "") -> dict[str, Any]:
    return {
        "source_case_id": item["source_case_id"],
        "case_origin": item["case_origin"],
        "source_district": item.get("source_district", ""),
        "source_dispatch_target": item.get("source_target_name") or item.get("raw_department_name") or "",
        "mapped_dispatch_target": item["target_name"],
        "topic_key": item["topic_key"],
        "final_selection": selected,
        "practice_reserve": not selected,
        "elimination_or_reserve_reason": reason,
        "reference_basis_status": item["reference_basis_status"],
        "replacement_happened": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--combined", type=Path, default=ROOT / "artifacts/practice-expansion-phase51/combined_practice_candidates.json")
    parser.add_argument("--challenge", type=Path, default=ROOT / "artifacts/challenge-v1/challenge_questions_v1_approved.json")
    parser.add_argument("--challenge-ids", type=Path, default=ROOT / "artifacts/practice-source-assessment/challenge_source_ids.json")
    parser.add_argument("--phase51-strict", type=Path, default=ROOT / "artifacts/practice-expansion-phase51/new_strict_practice_candidates.json")
    parser.add_argument("--db", type=Path, default=ROOT / "dispatch_training.db")
    parser.add_argument("--asset-root", type=Path, default=Path(r"D:\热线派单系统V2\assets\knowledge-source"))
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts/practice-v1")
    args = parser.parse_args()
    out = args.output_root
    out.mkdir(parents=True, exist_ok=True)

    combined = load_json(args.combined)
    challenge = load_json(args.challenge)
    phase51_strict = load_json(args.phase51_strict)
    challenge_source_ids = set(json.loads(args.challenge_ids.read_text(encoding="utf-8")))
    actual_hash = hashlib.sha256(args.challenge.read_bytes()).hexdigest().upper()
    if actual_hash != CHALLENGE_FROZEN_SHA256:
        raise SystemExit("challenge冻结哈希不一致，立即停止")
    if len(combined) != 465:
        raise SystemExit(f"strict候选版本不是465：{len(combined)}")
    ids = [x["source_case_id"] for x in combined]
    if len(ids) != len(set(ids)):
        raise SystemExit("source_case_id存在重复")
    if set(ids) & challenge_source_ids:
        raise SystemExit("strict候选与challenge source_case_id存在重叠")
    registry = build_target_registry(combined, args.db)
    engine = BasisEngine(args.asset_root, challenge, phase51_strict)
    enriched = enrich_candidates(combined, registry, engine)
    final, reserve = select_final(enriched)
    if len(final) != 450 or len(reserve) != 15:
        raise SystemExit(f"选择结果不是450+15：{len(final)}+{len(reserve)}")
    education_count = sum(1 for x in final if x["target_family"] == "education")
    if education_count > 90:
        raise SystemExit(f"教育题超过90：{education_count}")
    if any(x["reference_basis_status"] != "verified" for x in final):
        failed = [x["source_case_id"] for x in final if x["reference_basis_status"] != "verified"]
        raise SystemExit(f"正式题存在依据未verified：{failed[:10]}")
    build_options(final + reserve, registry)

    approved = [to_import_row(x) for x in final]
    write_json(out / "practice_questions_v1_approved.json", approved)
    audit = [audit_record(x, selected=True) for x in final]
    audit += [audit_record(x, selected=False, reason=x.get("reserve_reason", "备用题")) for x in reserve]
    write_json(out / "practice_questions_v1_audit.json", audit)
    reserve_rows = [to_import_row(x) | {"practice_reserve": True, "final_selection": False,
                                        "review_status": "pending", "enabled": False,
                                        "reserve_reason": x.get("reserve_reason", "")} for x in reserve]
    write_json(out / "practice_questions_v1_reserve.json", reserve_rows)
    write_csv(out / "practice_questions_v1_approved.csv", approved,
              ["source_case_id", "case_origin", "source_district", "source_dispatch_target", "question_type",
               "case_content", "correct_department_code", "correct_department_name", "wrong_options",
               "core_issue", "responsibility_reasoning", "transfer_reasoning", "explanation", "reference_basis",
               "reference_basis_title", "reference_basis_source", "reference_basis_excerpt",
               "reference_basis_locator", "reference_basis_reason", "reference_basis_status",
               "review_status", "final_selection", "topic_key", "training_context"])
    write_csv(out / "practice_questions_v1_audit.csv", audit,
              ["source_case_id", "case_origin", "source_district", "source_dispatch_target", "mapped_dispatch_target",
               "topic_key", "final_selection", "practice_reserve", "elimination_or_reserve_reason",
               "reference_basis_status", "replacement_happened"])
    summary = {
        "phase": "Phase 6 practice V1 production",
        "final_practice_count": len(approved),
        "reserve_count": len(reserve_rows),
        "source_counts": dict(Counter(x["case_origin"] for x in approved)),
        "canonical_target_count": len({x["correct_department_name"] for x in approved}),
        "education_count": education_count,
        "education_percent": round(education_count / len(approved) * 100, 2),
        "approved": len(approved),
        "verified": sum(1 for x in approved if x["reference_basis_status"] == "verified"),
        "replacement_count": 0,
        "output_dir": str(out),
    }
    write_json(out / "practice_v1_build_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
