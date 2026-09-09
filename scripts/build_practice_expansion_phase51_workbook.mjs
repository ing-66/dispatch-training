import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [dir, outputPath] = process.argv.slice(2);
const read = async (name) => JSON.parse(await fs.readFile(path.join(dir, name), "utf8"));
const summary = await read("summary.json");
const newStrict = await read("new_strict_practice_candidates.json");
const combined = await read("combined_practice_candidates.json");
const dist = await read("department_distribution.json");
const topics = await read("topic_clusters.json");
const duplicates = await read("duplicate_clusters.json");
const pending = await read("pending_target_assessment.json");
const audit = await read("audit_all_new_rows.json");
const citywide = await read("citywide_case_assessment.json");
const publicSvc = await read("public_service_case_assessment.json");

const wb = Workbook.create();
const header = { fill: "#1F4E78", font: { name: "Arial", bold: true, color: "#FFFFFF" }, wrapText: true, verticalAlignment: "center", horizontalAlignment: "center" };
const body = { font: { name: "Arial", size: 10, color: "#1F2937" }, wrapText: true, verticalAlignment: "top" };
function colName(n){let s="";while(n){n--;s=String.fromCharCode(65+n%26)+s;n=Math.floor(n/26);}return s;}
function table(name, labels, rows, widths, tableName){
  const sh = wb.worksheets.add(name); sh.showGridLines = false;
  const matrix = [labels, ...rows];
  sh.getRangeByIndexes(0, 0, matrix.length, labels.length).values = matrix;
  sh.getRangeByIndexes(0, 0, 1, labels.length).format = header;
  if (rows.length) sh.getRangeByIndexes(1, 0, rows.length, labels.length).format = body;
  sh.freezePanes.freezeRows(1); sh.freezePanes.freezeColumns(Math.min(2, labels.length));
  widths.forEach((w, i) => sh.getRangeByIndexes(0, i, matrix.length, 1).format.columnWidth = w);
  if (rows.length) sh.tables.add(`A1:${colName(labels.length)}${matrix.length}`, true, tableName).style = "TableStyleMedium2";
  return sh;
}
function value(v){return Array.isArray(v) ? v.join(" | ") : typeof v === "object" && v !== null ? JSON.stringify(v) : v ?? "";}

// Sheet 1
{
  const rows = [
    ["统计项", "数量", "说明"],
    ["现有白云strict practice候选", summary.existing_baiyun_strict, "baiyun_original"],
    ["Phase5跨区strict", summary.phase5_cross_district_strict, "cross_district_transfer"],
    ["Phase5.1新增strict", summary.phase51_new_strict_total, "Pool A/B/C新增"],
    ["其中：市级同体", summary.same_citywide_target_strict, "citywide_same_target"],
    ["其中：公共服务同体", summary.public_service_same_target_strict, "public_service_same_target"],
    ["其中：跨区转正（pending白云单位终验）", summary.phase51_new_by_origin?.cross_district_transfer ?? 0, "Pool C"],
    ["合并practice总候选容量", summary.merged_practice_capacity, "去重后"],
    ["距500", summary.gap_to_500, ""],
    ["距650", summary.gap_to_650, ""],
    ["距800", summary.gap_to_800, ""],
    ["教育类占比%", summary.education_share_percent, "合并池口径"],
    ["待人工复核needs_review", summary.needs_review_total, "当前未计入strict"],
    ["待人工复核理论上限容量", summary.merged_practice_capacity + summary.needs_review_total, "仅当全部needs_review复核通过"],
  ];
  const sh = table("总体容量", rows[0], rows.slice(1), [42, 20, 70], "Capacity51");
  sh.getRange("A1:C1").format.fill = { type: "solid", color: "#1F4E78" };
}

// Sheet 2: municipal subject stats
{
  const agg = new Map();
  for (const x of citywide) {
    const key = x.rule_key || "not_mapped";
    agg.set(key, (agg.get(key) || 0) + 1);
  }
  table("市级单位主题统计", ["市级规则/未映射", "案例数"], Array.from(agg, ([k, v]) => [k, v]), [40, 12], "CitywideSubjects");
}

// Sheet 3 same citywide candidates
const cityStrict = newStrict.filter(x => x.case_origin === "citywide_same_target");
table("same_citywide_target候选",
  ["原案ID", "来源范围", "原承办单位", "事项标题", "映射同体单位", "主题", "依据状态", "依据标题", "依据摘录", "依据定位"],
  cityStrict.map(x => [x.source_case_id, x.source_district, x.source_target_name, x.case_title,
    x.mapped_dispatch_target, x.topic_key, x.basis_status, x.basis_title, x.basis_excerpt, x.basis_locator]),
  [26, 14, 48, 36, 46, 18, 12, 30, 70, 56], "CitywideCandidates");

// Sheet 4 public service same target
const pubStrict = newStrict.filter(x => x.case_origin === "public_service_same_target");
table("公共服务同体候选",
  ["原案ID", "来源范围", "原承办单位", "事项标题", "映射同体单位", "主题", "依据状态", "依据标题", "依据摘录", "依据定位"],
  pubStrict.map(x => [x.source_case_id, x.source_district, x.source_target_name, x.case_title,
    x.mapped_dispatch_target, x.topic_key, x.basis_status, x.basis_title, x.basis_excerpt, x.basis_locator]),
  [26, 14, 48, 36, 46, 16, 12, 30, 70, 56], "PublicCandidates");

// Sheet 5 pending Baiyun units
table("pending白云承办单位",
  ["职能键", "建议规范名称", "职责章节", "有权威职责资料", "有权责清单目录", "终验状态", "审核意见"],
  pending.map(x => [x.canonical_target_key, x.canonical_target_name, x.doc_section, x.has_authoritative_doc,
    x.has_02_folder, x.status, x.review_note]),
  [24, 52, 34, 18, 18, 20, 50], "PendingTargets");

// Sheet 6 new verified canonical candidates
const verifiedCanonical = pending.filter(x => x.status === "verified_candidate");
table("新增verified canonical候选",
  ["职能键", "建议规范名称", "职责章节", "终验状态", "审核意见"],
  verifiedCanonical.map(x => [x.canonical_target_key, x.canonical_target_name, x.doc_section, x.status, x.review_note]),
  [24, 52, 34, 20, 50], "VerifiedCanonical");

// Sheet 7 new strict candidates
table("新增strict practice候选",
  ["原案ID", "来源类型", "原承办单位", "映射白云/市级单位", "主题", "职责依据状态", "依据标题", "依据来源", "审核状态"],
  newStrict.map(x => [x.source_case_id, x.case_origin, x.source_target_name, x.mapped_dispatch_target,
    x.topic_key, x.basis_status, x.basis_title, x.basis_source, x.review_status]),
  [26, 26, 50, 46, 16, 14, 32, 34, 12], "NewStrict");

// Sheet 8 needs_review
const needReview = audit.filter(x => !x.strict_eligible);
table("needs_review",
  ["原案ID", "来源类型", "原承办单位", "映射单位", "主题", "依据状态", "排除原因", "审核意见"],
  needReview.map(x => [x.source_case_id, x.case_origin, x.source_target_name, x.mapped_dispatch_target,
    x.topic_key, x.basis_status, x.exclude_reasons, x.review_note]),
  [26, 26, 50, 46, 16, 14, 46, 44], "NeedsReview");

// Sheet 9 insufficient/conflict
table("insufficient/conflict",
  ["原案ID", "来源类型", "原承办单位", "映射单位", "依据状态", "状态说明"],
  (audit.filter(x => ["insufficient", "conflict"].includes(x.basis_status))).map(x =>
    [x.source_case_id, x.case_origin, x.source_target_name, x.mapped_dispatch_target, x.basis_status, "当前证据不足/冲突"]),
  [26, 26, 50, 46, 16, 50], "InsufficientConflict");

// Sheet 10-11 distributions
table("部门分布", ["白云/市级规范承办单位", "候选数", "占比%", "集中度标记"],
  dist.map(x => [x.canonical_target, x.candidate_count, x.percentage, x.share_flag]), [60, 12, 12, 14], "DepartmentDistribution51");
table("业务主题分布", ["主题键", "候选数"],
  topics.map(x => [x.topic_key, x.case_count]), [40, 12], "TopicDistribution51");

// Sheet 12 near duplicate clusters
table("近重复簇",
  ["簇规模", "映射单位", "原案ID列表", "相似对"],
  duplicates.map(x => [x.cluster_size, x.mapped_dispatch_target, x.source_case_ids, x.similar_pairs.map(p => `${p.a}~${p.b}:${p.score}`)]),
  [10, 46, 60, 60], "DuplicateClusters");

// Sheet 13 merged pool
table("合并后的practice候选池",
  ["原案ID", "来源类型", "源区", "来源文件", "映射单位", "事项标题", "主题", "审核状态"],
  combined.map(x => [x.source_case_id, x.case_origin, x.source_district || "", x.source_file || "",
    x.mapped_dispatch_target, x.case_title || "", x.topic_key, x.review_status || "pending"]),
  [26, 26, 12, 28, 46, 40, 18, 12], "CombinedPool");

// Sheet 14 capacity targets
table("距500/650/800容量",
  ["容量口径", "候选数", "距500", "距650", "距800", "说明"],
  [
    [summary.merged_practice_capacity, summary.merged_practice_capacity, summary.gap_to_500, summary.gap_to_650, summary.gap_to_800, "现有strict合并池"],
    [summary.merged_practice_capacity + summary.needs_review_total, summary.merged_practice_capacity + summary.needs_review_total,
      Math.max(0, 500 - summary.merged_practice_capacity - summary.needs_review_total),
      Math.max(0, 650 - summary.merged_practice_capacity - summary.needs_review_total),
      Math.max(0, 800 - summary.merged_practice_capacity - summary.needs_review_total), "全部needs_review复核通过的理论上限"],
  ],
  [40, 12, 12, 12, 12, 46], "CapacityTargets");

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const out = await SpreadsheetFile.exportXlsx(wb);
await out.save(outputPath);
console.log("sheets:", wb.worksheets.items.length);
