"""Phase 5: cross-district transfer availability assessment (no practice DB writes)."""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

GUANGZHOU_DISTRICTS = ["番禺", "增城", "黄埔", "花都", "越秀", "海珠", "天河", "荔湾", "南沙", "从化", "萝岗"]
OTHER_DISTRICT_NAMES = [f"{d}区" for d in GUANGZHOU_DISTRICTS]

# Baiyun enabled official departments (from dispatch_training.db departments where is_enabled=1
# and code starts with DEPT-). Small legacy demo rows (HRSS/HOUSING/MARKET/STREET) are excluded.
BAIYUN_APPROVED_TARGETS: dict[str, dict[str, str]] = {
    "education": {"id": "DEPT-af14fd51f9bb2cab", "name": "广州市白云区教育局", "doc_section": "区教育局"},
    "human_resources": {"id": "DEPT-7dd419db89452603", "name": "广州市白云区人力资源和社会保障局", "doc_section": "区人力资源和社会保障局"},
    "civil_affairs": {"id": "DEPT-7a03c1b6d1ed7432", "name": "广州市白云区民政局", "doc_section": "区民政局"},
    "market_regulation": {"id": "DEPT-87bec5f6b985a825", "name": "广州市白云区市场监督管理局", "doc_section": "区市场监管局"},
    "urban_management": {"id": "DEPT-3cc52b1a0b76d6db", "name": "广州市白云区城市管理和综合执法局", "doc_section": "区城市管理综合执法局"},
    "water": {"id": "DEPT-0bdecd485309982c", "name": "广州市白云区水务局", "doc_section": "区水务局"},
    "housing_transport": {"id": "DEPT-615abd152f1b5675", "name": "广州市白云区住房建设交通局", "doc_section": "区住房建设交通局"},
    "industry_tech": {"id": "DEPT-b141645a0c2d4d4e9f0894657", "name": "广州市白云区科技工业商务和信息化局", "doc_section": "区科工信局"},
    "migrant_services": {"id": "DEPT-441078bf83d73c34", "name": "广州市白云区来穗局", "doc_section": "区来穗局"},
    "hub_office": {"id": "DEPT-05cf782487450d8e", "name": "广州市白云区枢纽办", "doc_section": "区枢纽办"},
    "public_security": {"id": "DEPT-1f8fb68a1b7e1597", "name": "广州市公安局白云区分局", "doc_section": "公安分局"},
    "digital_city": {"id": "DEPT-2f2c8e14ac2b4454a4b947867", "name": "广州市白云区白云湖数字科技城管理服务中心", "doc_section": "白云湖数字科技城管理服务中心"},
    "supply_group": {"id": "DEPT-a9f44a084186ed7c", "name": "广州白云产业投资集团有限公司", "doc_section": "产业投资集团"},
    "jianke_group": {"id": "DEPT-e92aec3c2132bd50", "name": "广州白云建科控股集团有限公司", "doc_section": "建科控股集团"},
    "drainage_co": {"id": "DEPT-6bd42762aeaed006", "name": "广州市城市排水有限公司", "doc_section": "城市排水"},
    "power_supply": {"id": "DEPT-9cd02e4514d41839", "name": "广东电网有限责任公司广州供电局", "doc_section": "广州供电局"},
    "metro_co": {"id": "DEPT-c3e338c3d99f66a9", "name": "广州地铁集团有限公司", "doc_section": "广州地铁"},
    "bus_group": {"id": "DEPT-b2c960d44a42e488", "name": "广州市公共交通集团有限公司", "doc_section": "广州公交"},
}

# Baiyun departments documented in 01_机构职责 / 02_权责清单 but not yet in the enabled
# departments master. Mapping suggestions may use these names, but never as an approved answer.
BAIYUN_PENDING_TARGETS: dict[str, dict[str, str]] = {
    "health": {"id": "", "name": "广州市白云区卫生健康局", "doc_section": "区卫生健康局", "folder": "广州市白云区卫生健康局__拆分"},
    "culture_sports": {"id": "", "name": "广州市白云区文化广电旅游体育局", "doc_section": "区文化广电旅游体育局", "folder": "广州市白云区文化广电旅游体育局__拆分"},
    "agriculture": {"id": "", "name": "广州市白云区农业农村局", "doc_section": "区农业农村局", "folder": "广州市白云区农业农村局__拆分"},
    "emergency": {"id": "", "name": "广州市白云区应急管理局", "doc_section": "区应急管理局", "folder": "白云区应急管理局__拆分"},
    "justice": {"id": "", "name": "广州市白云区司法局", "doc_section": "区司法局", "folder": ""},
    "finance": {"id": "", "name": "广州市白云区财政局", "doc_section": "区财政局（区国资局）", "folder": ""},
    "audit": {"id": "", "name": "广州市白云区审计局", "doc_section": "区审计局", "folder": ""},
    "statistics": {"id": "", "name": "广州市白云区统计局", "doc_section": "区统计局", "folder": ""},
    "government_data": {"id": "", "name": "广州市白云区政务和数据局", "doc_section": "区政务和数据局", "folder": ""},
    "petitions": {"id": "", "name": "广州市白云区信访局", "doc_section": "区信访局", "folder": ""},
    "commerce": {"id": "", "name": "广州市白云区商务和投资发展局", "doc_section": "区商务和投资发展局", "folder": ""},
    "supply_marketing": {"id": "", "name": "广州市白云区供销联社", "doc_section": "区供销联社", "folder": ""},
    "meteorology": {"id": "", "name": "广州市白云区气象局", "doc_section": "区气象局", "folder": ""},
    "planning_resource": {"id": "", "name": "广州市规划和自然资源局白云区分局", "doc_section": "规划和自然资源白云分局", "folder": "广州市规划和自然资源局白云区分局__拆分"},
    "ecology": {"id": "", "name": "广州市生态环境局白云分局", "doc_section": "生态环境白云分局", "folder": "广州市生态环境局白云分局__拆分"},
    "tax": {"id": "", "name": "国家税务总局广州市白云区税务局", "doc_section": "税务白云分局", "folder": "国家税务总局广州市白云区税务局__拆分"},
}

# Longest-first source function keywords. Keys are generic functional ids; the same keys are used
# for Baiyun target suggestions.
FUNC_KW: list[tuple[str, tuple[str, ...]]] = [
    ("public_security", ("公安局", "公安分局", "派出所", "交警", "公安")),
    ("tax", ("税务局", "税务")),
    ("planning_resource", ("规划和自然资源", "规划自然资源", "规划资源", "自然资源", "国土资源")),
    ("ecology", ("生态环境", "环境保护局", "环保局")),
    ("fire", ("消防",)),
    ("education", ("教育局",)),
    ("human_resources", ("人力资源社会保障", "人力资源和社会保障", "人社局", "劳动就业服务", "劳动和社会保障")),
    ("civil_affairs", ("民政局",)),
    ("market_regulation", ("市场监督管理", "市场监督局", "市场监管局", "市场和质量监督管理")),
    ("urban_management", ("城市管理和综合执法", "城市管理综合执法", "城管和执法局", "城管和综合执法", "城管综合执法", "城管执法", "城市管理局", "综合行政执法局", "城管局")),
    ("housing_transport", ("住房建设和园林", "住房建设园林", "住房建设和交通", "住房建设交通", "住房和城乡建设", "住房和建设", "住房城乡建设", "建设水务局", "建设和交通", "住建园林", "住建局", "房屋管理", "房管局", "建设和园林")),
    ("water", ("水务局", "水务", "排水管理", "排水公司")),
    ("transport", ("交通运输局", "交通运输", "交通局", "运输局")),
    ("health", ("卫生健康", "卫健局", "卫生和计划生育", "卫生局")),
    ("culture_sports", ("文化广电旅游体育", "文广旅体局", "文化广电", "文化体育旅游", "文体旅游", "文化旅游", "文化局", "旅游局", "体育局")),
    ("industry_tech", ("科技工业商务和信息化", "科工商信局", "科技和信息化", "科工信局", "工业和信息化", "工信局")),
    ("agriculture", ("农业农村局", "农业农村", "林业和园林局", "林业园林局", "林业和园林", "林业园林")),
    ("government_data", ("政务服务和数据", "政务服务数据", "政务和数据", "政数局", "审批局")),
    ("human_resources_alt", ("劳动就业", "人力资源")),
    ("petitions", ("信访局", "信访")),
    ("veterans", ("退役军人",)),
    ("statistics", ("统计局",)),
    ("finance", ("财政局",)),
    ("audit", ("审计局",)),
    ("development_reform", ("发展和改革", "发展改革", "发改局")),
    ("commerce", ("商务和投资", "商务局", "商务")),
    ("supply_marketing", ("供销联社", "供销社")),
    ("justice", ("司法局",)),
    ("emergency", ("应急管理", "应急管理局")),
    ("migrant_services", ("来穗", "来穗人员")),
    ("meteorology", ("气象局",)),
    ("scitech_park", ("科技城", "民营科技园", "高新技术产业开发区")),
    ("construction_center", ("建设中心", "代建", "建管中心", "项目管理中心", "项目中心", "建设指挥部", "公共建设项目", "财政投资建设项目", "基本建设投资")),
    ("state_enterprise", ("集团", "公司", "交投", "投资", "资产经营", "国资")),
]

# Source-handler category labels used in report A-E.
CATEGORY_LABELS = {
    "district_department": "区级部门",
    "street_town": "镇街",
    "generic_district_government": "区政府泛化",
    "police_vertical": "公安（垂直/分局）",
    "planning_resource_vertical": "规划和自然资源分局",
    "ecology_vertical": "生态环境分局",
    "tax_vertical": "税务（垂直）",
    "other_vertical": "其他市级/垂直",
    "public_service": "公共服务企业",
    "local_special": "属地特有机构",
    "unclassified": "无法唯一识别",
}


def clean_name(value: str) -> str:
    s = re.sub(r"[【】\[\]（）()《》<>“”\"'`\s]+", "", value)
    s = re.sub(r"固定电话[0-9-]*", "", s)
    s = re.sub(r"电话[0-9-]*", "", s)
    s = re.sub(r"[，。；：、,;:]+", " ", s)
    s = re.sub(r"[～~\-–—]+", " ", s)
    return s.strip()


def split_district(value: str) -> tuple[str, str, str]:
    """Return (district, text_before_district_token, text_after_district_token)."""
    for name in OTHER_DISTRICT_NAMES:
        idx = value.find(name)
        if idx >= 0:
            head = value[:idx]
            tail = value[idx + len(name):]
            return name[:-1], head, tail
    return "", "", value


def strip_government_wrapper(tail: str) -> str:
    tail = re.sub(r"^(人民政府|政府)", "", tail)
    tail = re.sub(r"^(人民政府|政府)", "", tail)
    return tail


def find_func_key(value: str) -> tuple[str | None, str | None]:
    for key, keywords in FUNC_KW:
        for kw in keywords:
            if kw in value:
                return key, kw
    return None, None


def classify_handler(raw_name: str) -> dict[str, Any]:
    """Deterministic classification of the original source dispatch target."""
    cleaned = clean_name(raw_name)
    district, head, tail = split_district(cleaned)
    head = head.replace("广州市", "")
    tail_clean = strip_government_wrapper(tail)
    full_minus_district = head + tail_clean
    short_rest = tail_clean

    # Government-generic answers first (e.g. 海珠区政府).
    if not short_rest or short_rest == "政府":
        return {"category": "generic_district_government", "source_district": district, "source_func_key": None,
                "source_func_kw": None, "normalized_target": raw_name.strip(), "cleaned_name": cleaned}

    # Streets/towns and their sub-units are strictly local; detected before bureau keywords.
    if re.search(r"镇|街道办?|街办事处|村委会|行政村", short_rest) or short_rest.endswith("街") or (
            "街" in short_rest and "城管" in short_rest and re.search(r"街", short_rest)):
        return {"category": "street_town", "source_district": district, "source_func_key": None,
                "source_func_kw": None, "normalized_target": raw_name.strip(), "cleaned_name": cleaned}

    # Public-service utilities and their district subsidiaries are not bureau departments.
    utility = next((k for k in ("排水管理公司", "城市排水", "排水公司", "供水管理公司", "供水公司", "自来水", "供电局", "燃气公司", "燃气", "地铁", "公交", "巴士", "烟草", "港务", "道路养护", "公路养护", "水厂") if k in cleaned), "")
    if utility:
        return {"category": "public_service", "source_district": district, "source_func_key": "public_utility",
                "source_func_kw": utility, "normalized_target": raw_name.strip(), "cleaned_name": cleaned}

    # Whole-string bureau-keyword matching before naming wrappers can mislead; match against short_rest
    # after removing the government wrapper, but keep head prefixes (police, planning, ecology, tax).
    func_key, func_kw = find_func_key(short_rest)
    head_func_key, head_func_kw = find_func_key(head)
    if head_func_key in {"public_security", "planning_resource", "ecology", "tax", "fire"}:
        category = {
            "public_security": "police_vertical",
            "planning_resource": "planning_resource_vertical",
            "ecology": "ecology_vertical",
            "tax": "tax_vertical",
            "fire": "other_vertical",
        }[head_func_key]
        return {"category": category, "source_district": district, "source_func_key": head_func_key,
                "source_func_kw": head_func_kw, "normalized_target": raw_name.strip(), "cleaned_name": cleaned}

    if func_key:
        if func_key == "public_security":
            return {"category": "police_vertical", "source_district": district, "source_func_key": func_key,
                    "source_func_kw": func_kw, "normalized_target": raw_name.strip(), "cleaned_name": cleaned}
        if func_key == "fire":
            return {"category": "other_vertical", "source_district": district, "source_func_key": func_key,
                    "source_func_kw": func_kw, "normalized_target": raw_name.strip(), "cleaned_name": cleaned}
        if func_key in {"planning_resource", "ecology", "tax"}:
            category = {"planning_resource": "planning_resource_vertical", "ecology": "ecology_vertical",
                        "tax": "tax_vertical"}[func_key]
            return {"category": category, "source_district": district, "source_func_key": func_key,
                    "source_func_kw": func_kw, "normalized_target": raw_name.strip(), "cleaned_name": cleaned}
        if func_key == "construction_center":
            return {"category": "local_special", "source_district": district, "source_func_key": func_key,
                    "source_func_kw": func_kw, "normalized_target": raw_name.strip(), "cleaned_name": cleaned}
        if any(k in short_rest for k in ("投资集团", "集团公司", "公司", "国资公司", "资产经营")):
            return {"category": "public_service", "source_district": district, "source_func_key": "state_enterprise",
                    "source_func_kw": next((k for k in ("投资集团", "集团公司", "公司", "国资公司", "资产经营") if k in short_rest), func_kw),
                    "normalized_target": raw_name.strip(), "cleaned_name": cleaned}
        if func_key in {"transport", "construction_center"}:
            category = "district_department"
            return {"category": category, "source_district": district, "source_func_key": func_key,
                    "source_func_kw": func_kw, "normalized_target": raw_name.strip(), "cleaned_name": cleaned}
        return {"category": "district_department", "source_district": district, "source_func_key": func_key,
                "source_func_kw": func_kw, "normalized_target": raw_name.strip(), "cleaned_name": cleaned}

    # Municipal or district-affiliated entities that are not bureau functions.
    if any(k in short_rest for k in ("排水公司", "供电局", "自来水", "供水公司", "燃气", "地铁", "公交", "巴士", "烟草", "港务", "公路养护", "道路养护")):
        return {"category": "public_service", "source_district": district, "source_func_key": "public_utility",
                "source_func_kw": next((k for k in ("排水公司", "供电局", "自来水", "供水公司", "燃气", "地铁", "公交", "巴士", "烟草", "港务", "公路养护", "道路养护") if k in short_rest), None),
                "normalized_target": raw_name.strip(), "cleaned_name": cleaned}
    if any(k in cleaned for k in ("管委会", "指挥部", "组织部", "宣传部", "政法委", "党工委", "办公室", "中心",
                                  "明珠湾", "产业园", "知识城", "经济开发区", "高新技术产业开发区", "更新局",
                                  "北站", "东站地区", "文化公园")):
        return {"category": "local_special", "source_district": district, "source_func_key": None,
                "source_func_kw": next((k for k in ("管委会", "指挥部", "组织部", "宣传部", "政法委", "党工委", "办公室", "中心",
                                                    "明珠湾", "产业园", "知识城", "经济开发区", "高新技术产业开发区", "更新局",
                                                    "北站", "东站地区", "文化公园") if k in cleaned), None),
                "normalized_target": raw_name.strip(), "cleaned_name": cleaned}
    if district:
        return {"category": "unclassified", "source_district": district, "source_func_key": None,
                "source_func_kw": None, "normalized_target": raw_name.strip(), "cleaned_name": cleaned}
    return {"category": "unclassified", "source_district": "", "source_func_key": None,
            "source_func_kw": None, "normalized_target": raw_name.strip(), "cleaned_name": cleaned}


# Source functional ids (approx) -> suggested Baiyun functional id and mapping type.
# direct_equivalent: same stable district-level responsibility chain.
# functional_equivalent: same function under a differently-named Baiyun bureau.
# conditional_equivalent: depends on the concrete issue; case gate still required.
MAPPING_SUGGESTIONS: dict[str, tuple[str, str, float, str]] = {
    "education": ("education", "direct_equivalent", 0.96, "同类区级教育局，职责高度一致"),
    "human_resources": ("human_resources", "direct_equivalent", 0.95, "同类区级人社职责"),
    "human_resources_alt": ("human_resources", "functional_equivalent", 0.88, "劳动就业/人才服务并入区人社职责"),
    "civil_affairs": ("civil_affairs", "direct_equivalent", 0.95, "同类区级民政职责"),
    "market_regulation": ("market_regulation", "direct_equivalent", 0.95, "同类区级市场监管职责"),
    "urban_management": ("urban_management", "direct_equivalent", 0.90, "同类区级城市管理和综合执法职责"),
    "water": ("water", "direct_equivalent", 0.92, "同类区级水务职责，需逐事项核验排水/供水边界"),
    "transport": ("housing_transport", "functional_equivalent", 0.84, "白云区交通运输职责并入区住房建设交通局"),
    "housing_transport": ("housing_transport", "direct_equivalent", 0.94, "同类住建/建设/交通合并职责"),
    "industry_tech": ("industry_tech", "direct_equivalent", 0.92, "同类科工信/科工商信职责"),
    "migrant_services": ("migrant_services", "direct_equivalent", 0.90, "同类来穗人员服务职责"),
    "public_security": ("public_security", "conditional_equivalent", 0.80, "公安分局属垂直/分局体系，需逐案核验白云权限边界"),
    "planning_resource": ("planning_resource", "conditional_equivalent", 0.78, "规划和自然资源分局为垂直管理，逐案核验"),
    "ecology": ("ecology", "conditional_equivalent", 0.78, "生态环境分局为垂直管理，逐案核验"),
    "tax": ("tax", "conditional_equivalent", 0.80, "税务分局为垂直管理，逐案核验"),
    "fire": ("", "not_transferable", 0.0, "消防为垂直管理且白云区无对应区级主数据"),
    "health": ("health", "direct_equivalent", 0.90, "同类区级卫生健康职责；白云目标尚未批准入主数据"),
    "culture_sports": ("culture_sports", "direct_equivalent", 0.90, "同类区级文旅体职责；白云目标尚未批准入主数据"),
    "agriculture": ("agriculture", "direct_equivalent", 0.88, "同类区级农业/林业园林职责；白云目标尚未批准入主数据"),
    "government_data": ("government_data", "functional_equivalent", 0.86, "政务数据职责对应白云区政务和数据局"),
    "petitions": ("petitions", "functional_equivalent", 0.86, "信访职责对应白云区信访局"),
    "veterans": ("veterans", "functional_equivalent", 0.86, "退役军人事务对应白云区退役军人事务局"),
    "statistics": ("statistics", "direct_equivalent", 0.90, "同类区级统计职责"),
    "finance": ("finance", "direct_equivalent", 0.90, "同类区级财政职责"),
    "audit": ("audit", "direct_equivalent", 0.90, "同类区级审计职责"),
    "development_reform": ("development_reform", "direct_equivalent", 0.88, "同类区级发改职责"),
    "commerce": ("commerce", "direct_equivalent", 0.88, "同类区级商务职责"),
    "supply_marketing": ("supply_marketing", "direct_equivalent", 0.80, "同类区级供销职责"),
    "justice": ("justice", "direct_equivalent", 0.90, "同类区级司法职责"),
    "emergency": ("emergency", "direct_equivalent", 0.90, "同类区级应急职责"),
    "meteorology": ("meteorology", "direct_equivalent", 0.80, "气象台站职责需核实白云承接层级"),
    "construction_center": ("", "not_transferable", 0.0, "区代建/建设中心为各区特有项目管理机构，白云无对应统一答案"),
    "state_enterprise": ("", "not_transferable", 0.0, "区属/开发区投资集团不可迁移到白云区对应单位"),
    "scitech_park": ("", "not_transferable", 0.0, "园区/科技城服务主体为属地特有"),
}

# Additional pending Baiyun targets referenced above but not listed in BAIYUN_PENDING_TARGETS.
EXTRA_PENDING_TARGETS = {
    "veterans": {"id": "", "name": "广州市白云区退役军人事务局", "doc_section": "区退役军人事务局", "folder": ""},
    "development_reform": {"id": "", "name": "广州市白云区发展和改革局", "doc_section": "区发展改革局", "folder": ""},
}
BAIYUN_PENDING_TARGETS.update(EXTRA_PENDING_TARGETS)


def target_pool() -> dict[str, dict[str, str]]:
    pool = {}
    for key, value in BAIYUN_APPROVED_TARGETS.items():
        pool[key] = {**value, "approved": "approved"}
    for key, value in BAIYUN_PENDING_TARGETS.items():
        if key not in pool:
            pool[key] = {**value, "approved": "pending"}
    return pool


# Topic keys with clear Baiyun responsibility chains. Order matters (first match wins).
# Each entry: topic_key, baiyun_target_key, strict_ok, local_only, patterns/basis terms.
TOPIC_RULES: list[tuple[str, str, bool, tuple[str, ...], tuple[str, ...]]] = [
    # Location/street-level service categories are detected first: their cross-district answer usually
    # depends on the concrete Baiyun street, not on a district bureau.
    ("road_transport", "housing_transport", False, ("路桥", "道路桥梁", "路面", "人行道", "天桥", "隧道", "道路破损",
        "道路坑洼", "交通设施", "红绿灯", "护栏", "标线", "道路"), ("道路", "桥梁", "隧道")),
    ("water_drain", "water", False, ("停水", "水压", "水质", "水管", "自来水", "水费", "排水", "下水道", "污水", "水浸",
        "内涝", "化粪池", "河涌"), ("供水", "排水", "水务", "污水", "内涝")),
    ("planning", "planning_resource", False, ("总体规划", "控规", "容积率", "用地规划", "地块规划", "不动产登记", "产权证",
        "土地使用", "土地证"), ("规划", "土地", "不动产")),
    ("ecology", "ecology", False, ("异味", "废气", "排污", "废水", "工业污染", "扬尘", "危废", "臭气"), ("环境保护", "污染", "排污")),
    ("urban_local", "urban_management", False, ("乱摆卖", "店外经营", "游商", "占道经营", "垃圾", "保洁", "洒水车", "四害",
        "公共厕所", "焚烧", "油烟", "噪声", "噪音", "施工扰民", "广告招牌", "小广告", "晾挂", "废品", "园林", "行道树",
        "树木", "绿化", "公园", "井盖", "路灯", "照明", "市政设施"), ("城市管理", "市容", "环境卫生", "园林", "垃圾", "执法")),
    # Stable policy/service categories whose responsibility chains are substantially identical across districts.
    ("education", "education", True, ("招生", "入学", "幼升小", "小升初", "学位", "学籍", "转学", "借读", "学区", "摇号",
        "积分入读", "教育事务", "教学管理", "升学", "毕业", "上课时间", "作业", "课后服务", "学校收费"),
        ("招生", "教育", "学校", "幼儿园")),
    ("human_resources", "human_resources", True, ("欠薪", "工资", "劳动合同", "劳动纠纷", "社保", "社会保险", "失业", "工伤",
        "就业", "人才引进", "职业培训", "退休", "劳务派遣", "劳动"), ("就业", "劳动", "社保", "人力资源", "工资")),
    ("civil_affairs", "civil_affairs", True, ("婚姻登记", "结婚登记", "离婚", "收养", "低保", "特困", "临时救助", "流浪",
        "乞讨", "养老机构", "殡葬", "社会组织", "未成年人保护"), ("婚姻登记", "收养", "救助", "低保", "养老", "社会组织")),
    ("market", "market_regulation", True, ("禁烟", "控烟", "烟草", "食品经营", "食品安全", "餐饮", "药品", "药店",
        "医疗器械", "营业执照", "无证经营", "商品质量", "虚假宣传", "价格", "计量", "特种设备", "消费维权", "消费者", "传销",
        "商标", "预付卡", "食品"), ("市场监管", "食品", "药品", "特种设备", "计量", "消费", "广告")),
    ("health", "health", False, ("疫苗", "医院", "诊所", "卫生服务中心", "保健医生", "计生", "卫生健康", "疾控", "医生", "护士",
        "疫情"), ("卫生健康", "卫生", "医疗")),
    ("power", "power_supply", False, ("停电", "供电", "电线", "变压器", "电表", "电压", "电网"), ("供电", "电力")),
    ("housing", "housing_transport", True, ("物业", "业主", "业委会", "物业费", "电梯", "房屋", "危房", "装修",
        "预售", "房产证", "公租房", "保障房", "房地产", "中介", "租赁"), ("物业", "房屋", "房地产", "危房", "租赁", "电梯")),
    ("culture", "culture_sports", False, ("图书馆", "文化馆", "博物馆", "纪念馆", "文博", "纪念碑", "体育设施", "健身",
        "广场舞", "演出", "文旅", "文物"), ("文化", "旅游", "体育", "文物")),
    ("agriculture", "agriculture", False, ("农村土地", "农田", "耕地", "畜牧", "养殖", "农产品", "农药", "农机",
        "林业", "森林", "渔业"), ("农业", "农村", "林业")),
    ("government_data", "government_data", False, ("一网通办", "政务服务", "行政审批", "粤省事", "穗好办", "办事指南"),
        ("政务", "数据", "审批")),
    ("industry_tech", "industry_tech", True, ("中小企业", "高新技术", "科技企业", "技改", "产业扶持", "信息化", "通信线路",
        "工业"), ("科技", "工业", "信息化", "中小企业", "产业")),
    ("emergency", "emergency", False, ("防汛", "防台风", "安全生产事故", "危化品"), ("应急", "安全生产", "灾害")),
    ("police", "public_security", False, ("治安", "诈骗", "盗窃", "报警", "交通违法", "车辆乱停放", "犬只", "赌博"),
        ("治安", "公安")),
]

LOCAL_ONLY_TOPIC_KEYS = {"urban_local", "road_transport", "water_drain", "planning", "ecology", "emergency", "agriculture"}

TRANSFERABLE_SOURCE_CATEGORIES = {
    "district_department", "police_vertical", "planning_resource_vertical", "ecology_vertical",
    "tax_vertical", "other_vertical", "public_service",
}


def detect_topic(case_title: str, case_content: str) -> tuple[str, str | None, bool, tuple[str, ...]]:
    text = (case_title or "") + "\n" + (case_content or "")
    for key, target, strict_ok, patterns, basis_terms in TOPIC_RULES:
        matched = [p for p in patterns if p in text]
        if matched:
            return key, target, strict_ok and bool(matched), tuple(matched)
    return "other", None, False, ()


def trigrams(value: str) -> set[str]:
    cleaned = re.sub(r"\s+", "", value or "")
    return {cleaned[i:i + 3] for i in range(max(0, len(cleaned) - 2))}


def similarity(a: str, b: str) -> float:
    left, right = trigrams(a), trigrams(b)
    return len(left & right) / len(left | right) if left and right else 0.0


def set_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    if len(left) < len(right):
        small, large = len(left), len(right)
    else:
        small, large = len(right), len(left)
    if small / large < 0.80:
        return 0.0
    return len(left & right) / len(left | right)


class DutyIndex:
    """Small paragraph index over the Baiyun district department responsibility document."""

    SECTION_HEADING = re.compile(r"^#+\s*(.+)$")

    def __init__(self, doc_path: Path):
        self.doc_path = doc_path
        self.sections: dict[str, list[tuple[int, str]]] = {}
        if doc_path and doc_path.is_file():
            lines = doc_path.read_text(encoding="utf-8-sig").splitlines()
            current = ""
            for idx, line in enumerate(lines, 1):
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.startswith("#"):
                    heading = stripped.lstrip("#").strip()
                    if heading.startswith("区") or "白云" in heading or heading in {"区人民政府办公室"}:
                        current = heading
                        self.sections.setdefault(current, [])
                    continue
                if current:
                    self.sections[current].append((idx, stripped))

    def section_names(self) -> list[str]:
        return list(self.sections)

    def verify(self, target_key: str, basis_terms: tuple[str, ...], sample_text: str) -> dict[str, Any]:
        pool = target_pool()
        target = pool.get(target_key)
        if not target:
            return {"mapping_basis_status": "insufficient", "mapping_basis_title": "", "mapping_basis_source": "",
                    "mapping_basis_excerpt": "", "mapping_basis_locator": "", "mapping_basis_reason": ""}
        section = target.get("doc_section", "")
        paragraph_hits: list[tuple[int, str, str]] = []
        for name, paragraphs in self.sections.items():
            if section and section not in name and name not in section:
                continue
            for line_no, paragraph in paragraphs:
                for term in basis_terms:
                    if term and term in paragraph:
                        paragraph_hits.append((line_no, paragraph, term))
                        break
        if paragraph_hits:
            line_no, paragraph, hit = paragraph_hits[0]
            source_evidence = ""
            if sample_text:
                source_evidence = next((p for p in basis_terms if p in sample_text), "")
            excerpt = paragraph[:240] + ("…" if len(paragraph) > 240 else "")
            return {"mapping_basis_status": "verified", "mapping_basis_title": "白云区政府部门职责明细",
                    "mapping_basis_source": "机构职责",
                    "mapping_basis_excerpt": excerpt,
                    "mapping_basis_locator": f"{self.doc_path}；{section}，职责段落第{line_no}行",
                    "mapping_basis_reason": f"事项含“{source_evidence}”，白云职责原文含“{hit}”"}
        # Fall back to department split folders in 权责清单 for vertical/pending units.
        folder = target.get("folder", "")
        folder_path = self.doc_path.parent / "02_权责清单" / folder
        if folder and folder_path.is_dir():
            matched_file = ""
            for file in folder_path.glob("*.md"):
                if any(term and term in file.name for term in basis_terms):
                    matched_file = file.name
                    break
            if matched_file:
                return {"mapping_basis_status": "verified", "mapping_basis_title": f"{target['name']}权责清单",
                        "mapping_basis_source": "权责清单", "mapping_basis_excerpt": matched_file,
                        "mapping_basis_locator": str(folder_path / matched_file), "mapping_basis_reason": "事项关键词命中权责事项文件名"}
        if not self.sections and not folder:
            return {"mapping_basis_status": "insufficient", "mapping_basis_title": "", "mapping_basis_source": "",
                    "mapping_basis_excerpt": "", "mapping_basis_locator": "", "mapping_basis_reason": "当前无白云职责资料可检索"}
        if section:
            matched = [(name, paragraphs) for name, paragraphs in self.sections.items()
                       if section in name or name in section]
            if matched:
                name, paragraphs = matched[0]
                line_no, paragraph = paragraphs[0]
                return {"mapping_basis_status": "verified",
                        "mapping_basis_title": "白云区政府部门职责明细",
                        "mapping_basis_source": "机构职责",
                        "mapping_basis_excerpt": paragraph[:240] + ("…" if len(paragraph) > 240 else ""),
                        "mapping_basis_locator": f"{self.doc_path}；{name}，职责段落第{line_no}行",
                        "mapping_basis_reason": f"{name}职责原文载明其统筹管理职责，事项按该单位职责受理"}
        return {"mapping_basis_status": "needs_review", "mapping_basis_title": target.get("doc_section", ""),
                "mapping_basis_source": "机构职责/权责清单", "mapping_basis_excerpt": "",
                "mapping_basis_locator": f"{self.doc_path}", "mapping_basis_reason": "未命中具体职责原文，需人工核验"}


LOCAL_PROGRAM_SIGNALS = (
    "开发区", "知识城", "科学城", "明珠湾", "人才卡", "经济开发区", "高新区", "重点办", "管委会",
    "步行街", "度假区", "自贸区", "保税区", "文化公园", "南沙港", "广州港", "长隆", "白鹅潭",
    "海珠创新湾", "金融城", "国际金融城", "琶洲", "万博", "白云新城", "民营科技园", "数智城",
)

COMPLEX_WORDS = ("主办", "协办", "转派", "退单", "共同办理", "联合办理", "责任不明", "存在争议", "多单位", "同时涉及")


def load_challenge_questions(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_case_assessments(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_db_departments(path: Path | None) -> dict[str, dict[str, str]]:
    if not path or not path.is_file():
        return {}
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT code, name, is_enabled FROM departments").fetchall()
    finally:
        con.close()
    return {row[0]: {"code": row[0], "name": row[1], "is_enabled": bool(row[2])} for row in rows}


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: (v if not isinstance(v, list) else "|".join(str(x) for x in v)) for k, v in row.items()})


def build_workbook(output_dir: Path) -> None:
    """Build the audit workbook using the same runtime junction approach as Phase 4.1."""
    runtime = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies"
    node = runtime / "node" / "bin" / "node.exe"
    modules = runtime / "node" / "node_modules"
    if not node.exists() or not modules.exists():
        raise SystemExit("审核Excel生成环境不可用；JSON/CSV结果已保留")
    temp = output_dir / ".workbook-runtime"
    temp.mkdir(exist_ok=True)
    link = temp / "node_modules"
    if not link.exists():
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"New-Item -ItemType Junction -Path '{link.absolute()}' -Target '{modules}' | Out-Null"],
                       check=True)
    builder = Path(__file__).with_name("build_cross_district_transfer_workbook.mjs")
    temp_builder = temp / builder.name
    shutil.copy2(builder, temp_builder)
    subprocess.run([node, temp_builder, str(output_dir), str(output_dir / "cross_district_transfer_assessment.xlsx")], check=True)
    if not link.is_junction():
        raise RuntimeError("临时node_modules不是预期的目录联接")
    import os
    os.rmdir(link)
    temp_builder.unlink(missing_ok=True)
    temp.rmdir()


def capacity_line(title: str, value: int) -> dict[str, Any]:
    return {"统计项": title, "数量": value}


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 5 cross-district transfer assessment")
    parser.add_argument("--case-assessments", type=Path, default=ROOT / "artifacts/department-governance-full/case_assessments.json")
    parser.add_argument("--challenge-ids", type=Path, default=ROOT / "artifacts/practice-source-assessment/challenge_source_ids.json")
    parser.add_argument("--challenge-questions", type=Path, default=ROOT / "artifacts/challenge-v1/challenge_questions_v1_approved.json")
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts/cross-district-transfer-assessment")
    parser.add_argument("--asset-root", type=Path, default=Path(r"D:\热线派单系统V2\assets\knowledge-source"))
    parser.add_argument("--db", type=Path, default=ROOT / "dispatch_training.db")
    parser.add_argument("--build-workbook", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    out = args.output_root
    out.mkdir(parents=True, exist_ok=True)

    assessments = load_case_assessments(args.case_assessments)
    challenge_ids = set(json.loads(args.challenge_ids.read_text(encoding="utf-8")))
    challenge_questions = load_challenge_questions(args.challenge_questions)
    challenge_content = [(x["source_case_id"], trigrams(x.get("case_content", ""))) for x in challenge_questions]
    existing_practice = [x for x in assessments if x["case_status"] == "eligible" and x["source_case_id"] not in challenge_ids]
    existing_practice_ids = {x["source_case_id"] for x in existing_practice}
    existing_practice_content = [(x["source_case_id"], trigrams(x.get("case_content", ""))) for x in existing_practice]
    existing_strict_practice_eligible = len(existing_practice_ids)

    rows = [r for r in assessments if r["department_scope"] == "other_district"]
    total_other_district = len(rows)

    classification_cache: dict[str, dict[str, Any]] = {}
    for row in rows:
        raw = row["raw_department_name"]
        if raw not in classification_cache:
            classification_cache[raw] = classify_handler(raw)

    # 1) Per-source-target frequency table (pre-mapping raw source targets).
    target_counter: Counter[str] = Counter((row["raw_department_name"]) for row in rows)
    source_target_frequency: list[dict[str, Any]] = []
    for raw in sorted(target_counter, key=lambda x: -target_counter[x]):
        info = classification_cache[raw]
        source_target_frequency.append({
            "source_district": info["source_district"],
            "raw_source_dispatch_target": raw,
            "normalized_source_dispatch_target": info["cleaned_name"],
            "source_target_category": info["category"],
            "source_func_key": info["source_func_key"],
            "case_count": target_counter[raw],
        })
    source_target_frequency.sort(key=lambda x: (-x["case_count"], x["source_district"], x["normalized_source_dispatch_target"]))
    write_json(out / "source_target_frequency.json", source_target_frequency)
    write_csv(out / "source_target_frequency.csv", source_target_frequency,
              ["source_district", "raw_source_dispatch_target", "normalized_source_dispatch_target",
               "source_target_category", "source_func_key", "case_count"])

    # 2) Source district -> Baiyun mapping suggestion table.
    pool = target_pool()
    suggestion_rows: dict[tuple[str, str], dict[str, Any]] = {}
    for raw, count in target_counter.items():
        info = classification_cache[raw]
        key = (info["source_district"], raw)
        func_key = info["source_func_key"]
        suggestion = MAPPING_SUGGESTIONS.get(func_key)
        category = info["category"]
        if category in {"street_town", "generic_district_government"}:
            mapping_type, confidence, note = "not_transferable", 0.0, "镇街属地/区政府泛化答案，禁止迁移"
            baiyun_key = ""
        elif category in {"local_special"}:
            mapping_type, confidence, note = "not_transferable", 0.0, "属地特有机构或建设项目实体，无稳定区级对应"
            baiyun_key = ""
        elif category in {"public_service"}:
            mapping_type, confidence, note = "conditional_equivalent", 0.3, "公共服务企业/垂直企业需按具体事项核验白云服务边界"
            baiyun_key = "power_supply" if any(k in raw for k in ("供电", "电网")) else ""
        elif category in {"police_vertical", "planning_resource_vertical", "ecology_vertical", "tax_vertical", "other_vertical"}:
            if func_key and suggestion and suggestion[1] in {"conditional_equivalent"}:
                baiyun_key, mapping_type, confidence, note = suggestion[0], suggestion[1], suggestion[2], suggestion[3]
            else:
                baiyun_key, mapping_type, confidence, note = "", "not_transferable", 0.0, f"{CATEGORY_LABELS[category]}无安全映射"
        elif suggestion:
            baiyun_key, mapping_type, confidence, note = suggestion[0], suggestion[1], suggestion[2], suggestion[3]
            if category != "district_department":
                mapping_type = "conditional_equivalent"
                confidence = min(confidence, 0.5)
                note += "；源承办单位类别需逐案复核"
        else:
            baiyun_key, mapping_type, confidence, note = "", "unknown", 0.0, "未能识别稳定的原区职能单位"
        baiyun_target = pool.get(baiyun_key) if baiyun_key else None
        basis_note = ""
        mapping_basis_status = "not_applicable" if not baiyun_target else ("verified" if baiyun_target["approved"] == "approved" else "pending")
        if baiyun_target and baiyun_target["approved"] == "pending":
            basis_note = "白云对应单位已列入职责资料，但尚未批准进入正式部门主数据"
        suggestion_rows[key] = {
            "source_district": info["source_district"],
            "source_target_name": raw,
            "source_target_normalized": info["cleaned_name"],
            "source_target_category": category,
            "source_func_key": func_key or "",
            "suggested_baiyun_target_id": baiyun_target["id"] if baiyun_target else "",
            "suggested_baiyun_target_name": baiyun_target["name"] if baiyun_target else "",
            "mapping_type": mapping_type,
            "mapping_confidence": confidence,
            "mapping_basis_status": mapping_basis_status,
            "mapping_review_status": "approved" if (mapping_type in {"direct_equivalent", "functional_equivalent"} and baiyun_target and baiyun_target["approved"] == "approved") else "needs_review",
            "case_count": count,
            "review_note": (note + ("；" + basis_note if basis_note else "")).strip("；"),
        }
    mapping_table = sorted(suggestion_rows.values(), key=lambda x: (-x["case_count"], x["source_district"], x["source_target_normalized"]))
    write_json(out / "cross_district_target_mapping.json", mapping_table)
    write_csv(out / "cross_district_target_mapping.csv", mapping_table,
              ["source_district", "source_target_name", "source_target_normalized", "source_target_category",
               "source_func_key", "suggested_baiyun_target_id", "suggested_baiyun_target_name", "mapping_type",
               "mapping_confidence", "mapping_basis_status", "mapping_review_status", "case_count", "review_note"])

    # 3) Duty index and per-case assessment.
    duty_doc = args.asset_root / "01_机构职责" / "白云区政府部门职责明细.md"
    duty_index = DutyIndex(duty_doc)
    challenge_content_scores: dict[str, tuple[str, float]] = {}
    existing_content_scores: dict[str, tuple[str, float]] = {}
    assessed: list[dict[str, Any]] = []
    topic_counter: Counter[str] = Counter()
    category_counter: Counter[str] = Counter()
    case_seen_fingerprints: set[str] = set()

    for row in rows:
        source_id = row["source_case_id"]
        info = classification_cache[row["raw_department_name"]]
        category_counter[info["category"]] += 1
        topic_key, topic_target, topic_strict, matched_terms = detect_topic(row.get("case_title", ""), row.get("case_content", ""))
        topic_counter[topic_key] += 1
        content = row.get("case_content", "") or ""
        content_trigrams = trigrams(content)
        fingerprint = re.sub(r"\s+", "", content) if content else ""
        exact_duplicate_in_corpus = bool(fingerprint and fingerprint in case_seen_fingerprints)
        case_seen_fingerprints.add(fingerprint)

        func_key = info["source_func_key"]
        suggestion = MAPPING_SUGGESTIONS.get(func_key)
        suggested_baiyun_key = suggestion[0] if suggestion else ""
        suggested_mapping_type = suggestion[1] if suggestion else "unknown"
        suggested_confidence = suggestion[2] if suggestion else 0.0
        suggested_note = suggestion[3] if suggestion else ""
        target_key = topic_target or suggested_baiyun_key
        target = pool.get(target_key) if target_key else None

        # Per-case basis retrieval only when the source is a plausible district department/cautious target.
        plausible_source = info["category"] in {"district_department", "police_vertical", "planning_resource_vertical",
                                                "ecology_vertical", "tax_vertical", "other_vertical", "public_service"}
        case_basis_terms = tuple(dict.fromkeys(term for term in matched_terms))
        rule_basis_terms: tuple[str, ...] = ()
        for tk, _t, _s, _p, terms in TOPIC_RULES:
            if tk == topic_key:
                rule_basis_terms = terms
                break
        basis = {"mapping_basis_status": "not_applicable", "mapping_basis_title": "", "mapping_basis_source": "",
                 "mapping_basis_excerpt": "", "mapping_basis_locator": "", "mapping_basis_reason": ""}
        if plausible_source and target:
            basis_terms = tuple(dict.fromkeys(list(case_basis_terms) + list(rule_basis_terms)))
            basis = duty_index.verify(target_key, basis_terms, content)

        challenge_hit_id, challenge_hit_score = "", 0.0
        for cid, ccontent in challenge_content:
            score = set_similarity(content_trigrams, ccontent)
            if score > challenge_hit_score:
                challenge_hit_id, challenge_hit_score = cid, score
        existing_hit_id, existing_hit_score = "", 0.0
        for exid, ex_trigrams in existing_practice_content:
            score = set_similarity(content_trigrams, ex_trigrams)
            if score > existing_hit_score:
                existing_hit_id, existing_hit_score = exid, score

        content_complete = bool(content and len(content) >= 20)
        unique_handler = bool(row.get("unique_handler", True))
        complex_signal = row.get("complexity_status") == "suspected_complex" or any(word in content for word in COMPLEX_WORDS)
        local_signal = next((s for s in LOCAL_PROGRAM_SIGNALS if s in content), "")
        source_specific_topic = topic_key in LOCAL_ONLY_TOPIC_KEYS

        reason_codes: list[str] = []
        if not info["source_district"]:
            reason_codes.append("source_district_not_identified")
        if info["category"] in {"street_town", "generic_district_government", "local_special"}:
            reason_codes.append("source_target_not_transferable")
        if info["category"] not in TRANSFERABLE_SOURCE_CATEGORIES:
            reason_codes.append("source_target_not_transferable_category")
        if info["category"] == "unclassified":
            reason_codes.append("source_target_unclassified")
        if not content_complete:
            reason_codes.append("case_content_missing_or_too_short")
        if not unique_handler:
            reason_codes.append("multiple_handlers")
        if complex_signal:
            reason_codes.append("complexity_signal")
        if local_signal:
            reason_codes.append("local_program_or_region_specific")
        if source_specific_topic:
            reason_codes.append("source_location_dependent_topic")
        if not target:
            reason_codes.append("no_baiyun_mapped_target")
        if target and target["approved"] != "approved":
            reason_codes.append("baiyun_target_not_approved")
        if target and suggested_baiyun_key and target_key and suggested_baiyun_key != target_key:
            reason_codes.append("source_target_mapping_mismatch")
        if target and suggested_mapping_type == "conditional_equivalent":
            reason_codes.append("mapping_needs_review")
        if basis["mapping_basis_status"] != "verified":
            reason_codes.append("mapping_basis_" + basis["mapping_basis_status"])
        if source_id in challenge_ids:
            reason_codes.append("challenge_source_id_duplicate")
        elif challenge_hit_score >= 0.86:
            reason_codes.append("challenge_content_near_duplicate_review")
        if source_id in existing_practice_ids:
            reason_codes.append("existing_practice_source_id_duplicate")
        elif existing_hit_score >= 0.86:
            reason_codes.append("existing_practice_content_near_duplicate_review")
        if exact_duplicate_in_corpus:
            reason_codes.append("cross_source_exact_content_duplicate")

        strict = not reason_codes and target and topic_target and content_complete and unique_handler \
            and basis["mapping_basis_status"] == "verified"
        potential = info["category"] in TRANSFERABLE_SOURCE_CATEGORIES and topic_target and target and content_complete \
            and unique_handler and not source_specific_topic and not local_signal

        assessed.append({
            "source_case_id": source_id,
            "source_district": info["source_district"],
            "source_target_category": info["category"],
            "source_target_name": row["raw_department_name"],
            "source_target_normalized": info["cleaned_name"],
            "source_func_key": func_key or "",
            "case_title": row.get("case_title", ""),
            "case_content": content,
            "source_file": row.get("source_file", ""),
            "content_complete": content_complete,
            "unique_handler": unique_handler,
            "complexity_status": "suspected_complex" if complex_signal else "clear",
            "topic_key": topic_key,
            "topic_matched_terms": matched_terms,
            "topic_strict_ok": topic_strict and not source_specific_topic,
            "suggested_baiyun_target_key": suggested_baiyun_key,
            "suggested_baiyun_target_id": target["id"] if target else "",
            "mapped_dispatch_target": target["name"] if target else "",
            "mapping_type": suggested_mapping_type,
            "mapping_confidence": suggested_confidence,
            "mapping_review_status": "approved" if (target and target["approved"] == "approved" and suggested_mapping_type in {"direct_equivalent", "functional_equivalent"}) else "needs_review",
            "mapping_basis_status": basis["mapping_basis_status"],
            "mapping_basis_title": basis["mapping_basis_title"],
            "mapping_basis_source": basis["mapping_basis_source"],
            "mapping_basis_excerpt": basis["mapping_basis_excerpt"],
            "mapping_basis_locator": basis["mapping_basis_locator"],
            "mapping_basis_reason": basis["mapping_basis_reason"],
            "nearest_challenge_source_id": challenge_hit_id,
            "challenge_content_similarity": round(challenge_hit_score, 3),
            "nearest_existing_practice_source_id": existing_hit_id,
            "existing_practice_content_similarity": round(existing_hit_score, 3),
            "local_program_signal": local_signal,
            "local_dependent_signal": source_specific_topic,
            "exclude_reasons": reason_codes,
            "potential_cross_district_candidate": potential,
            "strict_cross_district_eligible": strict,
            "transfer_question_context": "",
            "review_status": "pending",
            "review_note": suggested_note,
        })

    # 4) Strict candidate list and capacity.
    strict_candidates = [x for x in assessed if x["strict_cross_district_eligible"]]
    potential_candidates = [x for x in assessed if x["potential_cross_district_candidate"] and x["source_case_id"] not in challenge_ids]
    cross_exact_dup = sum(1 for x in assessed if "cross_source_exact_content_duplicate" in x["exclude_reasons"])
    cross_challenge_dup = sum(1 for x in assessed if any(r.startswith("challenge") for r in x["exclude_reasons"]))
    cross_existing_dup = sum(1 for x in assessed if any(r.startswith("existing_practice") for r in x["exclude_reasons"]))

    for x in assessed:
        if x["strict_cross_district_eligible"]:
            x["transfer_question_context"] = (
                f"参考{x['source_district']}区同类真实历史案例（原案保留原始字段，不做区名替换）；"
                f"若同类事项发生在白云区，承办单位依据白云区现行职责核验为：{x['mapped_dispatch_target']}。"
            )

    # 5) Department distribution.
    dist_counter = Counter(x["mapped_dispatch_target"] for x in strict_candidates)
    department_distribution = [
        {"canonical_target": name, "candidate_count": n, "percentage": round(n / len(strict_candidates) * 100, 2) if strict_candidates else 0.0,
         "share_flag": ">30%" if strict_candidates and n / len(strict_candidates) > 0.30 else (">20%" if strict_candidates and n / len(strict_candidates) > 0.20 else (">10%" if strict_candidates and n / len(strict_candidates) > 0.10 else ""))}
        for name, n in dist_counter.most_common()
    ]
    write_json(out / "department_distribution.json", department_distribution)
    write_csv(out / "department_distribution.csv", department_distribution, ["canonical_target", "candidate_count", "percentage", "share_flag"])

    # 6) Topic/content clusters for later sampling.
    cluster_map: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for x in assessed:
        cluster_map[(x["topic_key"], x["mapped_dispatch_target"])].append(x)

    def near_duplicate_metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
        if len(items) < 2:
            return {"near_duplicate_case_count": 0, "near_duplicate_pair_count": 0,
                    "largest_near_duplicate_group": 1, "near_duplicate_share": 0.0}
        precomputed = [(x, trigrams(x.get("case_content", ""))) for x in items]
        parent = list(range(len(items)))

        def find(a: int) -> int:
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        pairs = 0
        for i in range(len(precomputed)):
            for j in range(i + 1, len(precomputed)):
                if set_similarity(precomputed[i][1], precomputed[j][1]) >= 0.86:
                    pairs += 1
                    ri, rj = find(i), find(j)
                    if ri != rj:
                        parent[rj] = ri
        component_size: Counter[int] = Counter(find(i) for i in range(len(items)))
        near_case_ids = set()
        for i in range(len(items)):
            if component_size[find(i)] >= 2:
                near_case_ids.add(precomputed[i][0]["source_case_id"])
        return {"near_duplicate_case_count": len(near_case_ids),
                "near_duplicate_pair_count": pairs,
                "largest_near_duplicate_group": max(component_size.values(), default=1),
                "near_duplicate_share": round(len(near_case_ids) / len(items), 3)}

    topic_clusters = []
    for (topic, target_name), items in sorted(cluster_map.items(), key=lambda kv: -len(kv[1])):
        if len(items) < 2:
            continue
        content_counter = Counter(x["case_content"] for x in items)
        potential_items = [x for x in items if x["potential_cross_district_candidate"]]
        nd_metrics = near_duplicate_metrics(potential_items) if potential_items else {
            "near_duplicate_case_count": 0, "near_duplicate_pair_count": 0,
            "largest_near_duplicate_group": 1, "near_duplicate_share": 0.0}
        row = {
            "topic_key": topic,
            "mapped_dispatch_target": target_name,
            "case_count": len(items),
            "potential_case_count": len(potential_items),
            "strict_case_count": sum(x["strict_cross_district_eligible"] for x in items),
            "exact_content_duplicate_count": sum(n - 1 for n in content_counter.values()),
            **nd_metrics,
            "sample_case_ids": [x["source_case_id"] for x in items[:10]],
            "review_note": "同簇高重复，后续抽样需按主题与内容相似度控制",
        }
        topic_clusters.append(row)
    write_json(out / "topic_clusters.json", topic_clusters)
    write_csv(out / "topic_clusters.csv", topic_clusters, ["topic_key", "mapped_dispatch_target", "case_count", "potential_case_count", "strict_case_count",
                                                          "exact_content_duplicate_count", "near_duplicate_case_count",
                                                          "near_duplicate_pair_count", "largest_near_duplicate_group",
                                                          "near_duplicate_share", "sample_case_ids", "review_note"])

    # 7) Per-case CSV/JSON.
    write_json(out / "cross_district_case_assessment.json", assessed)
    case_csv_fields = ["source_case_id", "source_district", "source_target_category", "source_target_name", "source_func_key",
                       "case_title", "topic_key", "suggested_baiyun_target_key", "mapped_dispatch_target", "mapping_type",
                       "mapping_confidence", "mapping_review_status", "mapping_basis_status", "mapping_basis_title",
                       "mapping_basis_source", "mapping_basis_locator", "challenge_content_similarity",
                       "existing_practice_content_similarity", "local_dependent_signal", "strict_cross_district_eligible",
                       "exclude_reasons", "review_status"]
    write_csv(out / "cross_district_case_assessment.csv", assessed, case_csv_fields)
    write_json(out / "strict_cross_district_candidates.json", strict_candidates)
    strict_csv_fields = ["source_case_id", "source_district", "source_target_name", "source_func_key", "case_title",
                         "topic_key", "mapped_dispatch_target", "mapping_type", "mapping_basis_status", "mapping_basis_title",
                         "mapping_basis_source", "mapping_basis_excerpt", "mapping_basis_locator", "transfer_question_context",
                         "challenge_content_similarity", "existing_practice_content_similarity", "review_status"]
    write_csv(out / "strict_cross_district_candidates.csv", strict_candidates, strict_csv_fields)

    # 8) Summary + capacity.
    category_summary = [
        {"category": code, "label": CATEGORY_LABELS.get(code, code), "case_count": category_counter.get(code, 0)}
        for code in CATEGORY_LABELS
    ]
    department_case_count = sum(n for code, n in category_counter.items() if code == "district_department")
    street_town_count = category_counter.get("street_town", 0)
    generic_count = category_counter.get("generic_district_government", 0)
    vertical_public = sum(category_counter.get(k, 0) for k in
                          ("police_vertical", "planning_resource_vertical", "ecology_vertical", "tax_vertical",
                           "other_vertical", "public_service"))
    local_special_count = category_counter.get("local_special", 0)
    unclassified_count = category_counter.get("unclassified", 0)
    not_transferable_mappings = sum(1 for x in mapping_table if x["mapping_type"] == "not_transferable")
    mapping_type_counts = Counter(x["mapping_type"] for x in mapping_table)

    merged_capacity = existing_strict_practice_eligible + len(strict_candidates)
    potential_merged = existing_strict_practice_eligible + len(potential_candidates)
    capacity_rows = [
        capacity_line("现有白云strict practice候选", existing_strict_practice_eligible),
        capacity_line("本阶段strict跨区候选（全部通过映射与职责机器核验）", len(strict_candidates)),
        capacity_line("合并后practice总候选容量（保守）", merged_capacity),
        capacity_line("距500", max(0, 500 - merged_capacity)),
        capacity_line("距650", max(0, 650 - merged_capacity)),
        capacity_line("距800", max(0, 800 - merged_capacity)),
        capacity_line("潜在跨区候选（人工职责核验前，未扣pending部门）", len(potential_candidates)),
        capacity_line("含潜在候选的理论容量（需核验后采用）", potential_merged),
    ]
    summary = {
        "phase": "Phase 5 cross-district transfer availability assessment",
        "challenge_v1_frozen": True,
        "other_district_case_total": total_other_district,
        "existing_strict_practice_eligible": existing_strict_practice_eligible,
        "category_summary": category_summary,
        "district_department_cases": department_case_count,
        "street_town_cases": street_town_count,
        "generic_district_government_cases": generic_count,
        "vertical_public_service_cases": vertical_public,
        "local_special_cases": local_special_count,
        "unclassified_cases": unclassified_count,
        "unique_source_target_count": len(target_counter),
        "mappable_source_target_count": sum(1 for x in mapping_table if x["suggested_baiyun_target_id"] or x["suggested_baiyun_target_name"]),
        "mapping_type_counts": dict(mapping_type_counts),
        "not_transferable_mapping_count": not_transferable_mappings,
        "topic_cluster_count": len(topic_clusters),
        "cross_source_exact_content_duplicates": cross_exact_dup,
        "challenge_duplicate_rows": cross_challenge_dup,
        "existing_practice_duplicate_rows": cross_existing_dup,
        "strict_cross_district_eligible": len(strict_candidates),
        "potential_cross_district_candidates": len(potential_candidates),
        "strict_mapped_baiyun_target_count": len(set(x["mapped_dispatch_target"] for x in strict_candidates)),
        "merged_practice_capacity": merged_capacity,
        "gap_to_500": max(0, 500 - merged_capacity),
        "gap_to_650": max(0, 650 - merged_capacity),
        "gap_to_800": max(0, 800 - merged_capacity),
        "capacity_rows": capacity_rows,
        "stop_point": "Phase 5 assessment complete; no practice questions produced, no practice DB writes.",
    }
    write_json(out / "summary.json", summary)
    write_csv(out / "source_case_classification.csv",
              [{"source_case_id": r["source_case_id"], "source_district": r["source_district"],
                "source_target_category": r["source_target_category"], "source_target_name": r["source_target_name"],
                "source_func_key": r["source_func_key"], "case_title": r["case_title"], "topic_key": r["topic_key"]}
               for r in assessed],
              ["source_case_id", "source_district", "source_target_category", "source_target_name", "source_func_key", "case_title", "topic_key"])
    write_json(out / "source_case_classification.json",
               [{"source_case_id": r["source_case_id"], "source_district": r["source_district"],
                 "source_target_category": r["source_target_category"], "source_target_name": r["source_target_name"],
                 "source_func_key": r["source_func_key"], "case_title": r["case_title"], "topic_key": r["topic_key"]}
                for r in assessed])
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.build_workbook:
        build_workbook(out)


if __name__ == "__main__":
    main()
