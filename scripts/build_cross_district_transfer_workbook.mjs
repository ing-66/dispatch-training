import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [dir, outputPath] = process.argv.slice(2);
if (!dir || !outputPath) throw new Error("usage: node build_cross_district_transfer_workbook.mjs <input-dir> <output.xlsx>");

const read = async (name) => JSON.parse(await fs.readFile(path.join(dir, name), "utf8"));
const summary = await read("summary.json");
const sourceTargets = await read("source_target_frequency.json");
const mapping = await read("cross_district_target_mapping.json");
const assessed = await read("cross_district_case_assessment.json");
const strict = await read("strict_cross_district_candidates.json");
const distribution = await read("department_distribution.json");
const clusters = await read("topic_clusters.json");

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

// Sheet 1: overall capacity
{
  const sh = wb.worksheets.add("总体容量"); sh.showGridLines = false;
  sh.getRange("A1:C1").merge(); sh.getRange("A1").values = [["Phase 5 跨区迁移可用性评估 - 总体容量"]];
  sh.getRange("A2:C2").merge(); sh.getRange("A2").values = [["现有2440条其他区历史案例：只评估候选与容量，不生成正式题目，不写practice库"]];
  const rows = [
    ["统计项", "数量", "说明"],
    ["其他区历史案例总数", summary.other_district_case_total, "department_scope=other_district"],
    ["区级部门案例", summary.district_department_cases, "可进一步做跨区映射分析的主体"],
    ["镇街案例", summary.street_town_cases, "明确禁止迁移"],
    ["区政府泛化案例", summary.generic_district_government_cases, "明确禁止迁移"],
    ["垂直/公共服务案例", summary.vertical_public_service_cases, "谨慎审核，默认needs_review"],
    ["属地特有机构案例", summary.local_special_cases, "禁止迁移"],
    ["无法唯一识别", summary.unclassified_cases, "禁止迁移"],
    ["可建立跨区映射的原承办单位数量", summary.mappable_source_target_count, "distinct raw source targets"],
    ["direct_equivalent映射", summary.mapping_type_counts.direct_equivalent ?? 0, ""],
    ["functional_equivalent映射", summary.mapping_type_counts.functional_equivalent ?? 0, ""],
    ["conditional_equivalent映射", summary.mapping_type_counts.conditional_equivalent ?? 0, ""],
    ["not_transferable映射", summary.mapping_type_counts.not_transferable ?? 0, ""],
    ["strict跨区候选", summary.strict_cross_district_eligible, "机器完成映射/门禁/职责原文命中"],
    ["潜在跨区候选（人工核验前）", summary.potential_cross_district_candidates, "含pending白云部门与谨慎类型"],
    ["现有白云strict practice候选", summary.existing_strict_practice_eligible, "Phase 4.1真实基线"],
    ["合并后practice总候选容量", summary.merged_practice_capacity, "218 + strict跨区（已去重）"],
    ["距500", summary.gap_to_500, ""],
    ["距650", summary.gap_to_650, ""],
    ["距800", summary.gap_to_800, ""],
    ["含潜在候选理论容量", summary.existing_strict_practice_eligible + summary.potential_cross_district_candidates, "需要批准pending部门并人工核验后采用"],
  ];
  sh.getRangeByIndexes(0, 0, rows.length, 3).values = rows;
  sh.getRangeByIndexes(0, 0, 1, 3).format = header;
  sh.getRangeByIndexes(1, 0, rows.length - 1, 3).format = body;
  sh.getRange("A1").format.font = { name: "Arial", size: 15, bold: true };
  [18, 18, 50].forEach((w, i) => sh.getRangeByIndexes(0, i, rows.length, 1).format.columnWidth = w);
}

// Sheet 2: original district handler frequency
table("原区承办单位频次",
  ["源区", "原始承办单位", "归一化名称", "承办单位类别", "职能键", "案例数"],
  sourceTargets.map(x => [x.source_district, x.raw_source_dispatch_target, x.normalized_source_dispatch_target,
    x.source_target_category, x.source_func_key || "", x.case_count]),
  [10, 54, 44, 22, 18, 10], "SourceTargetFrequency");

// Sheet 3: mapping suggestions
table("原区→白云映射建议",
  ["源区", "原承办单位", "归一化名称", "原类别", "建议白云ID", "建议白云单位", "映射类型", "置信度", "依据状态", "审核状态", "案例数", "审核意见"],
  mapping.map(x => [x.source_district, x.source_target_name, x.source_target_normalized, x.source_target_category,
    x.suggested_baiyun_target_id, x.suggested_baiyun_target_name, x.mapping_type, x.mapping_confidence,
    x.mapping_basis_status, x.mapping_review_status, x.case_count, x.review_note]),
  [8, 52, 40, 20, 30, 44, 18, 10, 12, 14, 8, 48], "MappingTable");

// Sheets 4-7: mapping type subsets
const typeFilter = type => mapping.filter(x => x.mapping_type === type);
table("direct equivalent",
  ["源区", "原承办单位", "建议白云单位", "置信度", "依据状态", "审核状态", "案例数", "审核意见"],
  typeFilter("direct_equivalent").map(x => [x.source_district, x.source_target_name, x.suggested_baiyun_target_name,
    x.mapping_confidence, x.mapping_basis_status, x.mapping_review_status, x.case_count, x.review_note]),
  [8, 52, 48, 10, 14, 14, 8, 44], "DirectEquivalents");
table("functional equivalent",
  ["源区", "原承办单位", "建议白云单位", "置信度", "依据状态", "审核状态", "案例数", "审核意见"],
  typeFilter("functional_equivalent").map(x => [x.source_district, x.source_target_name, x.suggested_baiyun_target_name,
    x.mapping_confidence, x.mapping_basis_status, x.mapping_review_status, x.case_count, x.review_note]),
  [8, 52, 48, 10, 14, 14, 8, 44], "FunctionalEquivalents");
table("谨慎迁移候选",
  ["源区", "原承办单位", "原类别", "建议白云单位", "映射类型", "置信度", "案例数", "审核意见"],
  mapping.filter(x => x.mapping_type === "conditional_equivalent" || ["police_vertical", "planning_resource_vertical", "ecology_vertical", "tax_vertical", "public_service"].includes(x.source_target_category))
    .map(x => [x.source_district, x.source_target_name, x.source_target_category, x.suggested_baiyun_target_name,
      x.mapping_type, x.mapping_confidence, x.case_count, x.review_note]),
  [8, 52, 20, 46, 20, 10, 8, 46], "CautiousMappings");
table("不可迁移",
  ["源区", "原承办单位", "原类别", "映射类型", "案例数", "审核意见"],
  mapping.filter(x => ["not_transferable", "unknown"].includes(x.mapping_type)).map(x =>
    [x.source_district, x.source_target_name, x.source_target_category, x.mapping_type, x.case_count, x.review_note]),
  [8, 56, 22, 16, 8, 48], "NotTransferable");

// Sheet 8: strict cross-district candidates
table("strict跨区候选",
  ["原案ID", "源区", "原承办单位", "职能键", "案例标题", "主题", "映射白云单位", "映射类型", "依据状态",
   "依据标题", "依据来源", "依据摘录", "依据定位", "challenge相似度", "practice相似度", "迁移问法上下文"],
  strict.map(x => [x.source_case_id, x.source_district, x.source_target_name, x.source_func_key, x.case_title,
    x.topic_key, x.mapped_dispatch_target, x.mapping_type, x.mapping_basis_status, x.mapping_basis_title,
    x.mapping_basis_source, x.mapping_basis_excerpt, x.mapping_basis_locator, x.challenge_content_similarity,
    x.existing_practice_content_similarity, x.transfer_question_context]),
  [24, 8, 52, 16, 30, 16, 42, 16, 12, 30, 12, 60, 46, 12, 12, 48], "StrictCandidates");

// Sheet 9: Baiyun department distribution
table("白云承办单位分布",
  ["白云规范承办单位", "候选数", "占比%", "集中度标记"],
  distribution.map(x => [x.canonical_target, x.candidate_count, x.percentage, x.share_flag]),
  [60, 12, 12, 14], "DepartmentDistribution");

// Sheet 10: high-repeat topic/content clusters
table("高重复业务簇",
  ["主题键", "映射白云单位", "案例数", "潜在候选数", "strict数", "完全重复数", "近重复案例数", "近重复对", "最大近重复组", "近重复占比", "样例原案ID", "审核意见"],
  clusters.map(x => [x.topic_key, x.mapped_dispatch_target, x.case_count, x.potential_case_count, x.strict_case_count,
    x.exact_content_duplicate_count, x.near_duplicate_case_count, x.near_duplicate_pair_count,
    x.largest_near_duplicate_group, x.near_duplicate_share, x.sample_case_ids, x.review_note]),
  [16, 42, 10, 12, 10, 12, 12, 12, 14, 10, 44, 46], "TopicClusters");

// Sheet 11: responsibility basis needs review
const basisReview = assessed.filter(x => x.mapped_dispatch_target &&
  !x.strict_cross_district_eligible &&
  x.mapping_basis_status !== "not_applicable" &&
  (x.potential_cross_district_candidate || x.mapping_basis_status !== "verified"));
table("职责依据待审核",
  ["原案ID", "源区", "原承办单位", "原类别", "主题", "建议白云单位", "映射类型", "依据状态", "依据标题", "依据来源", "依据定位", "排除原因", "是否潜在候选"],
  basisReview.map(x => [x.source_case_id, x.source_district, x.source_target_name, x.source_target_category,
    x.topic_key, x.mapped_dispatch_target, x.mapping_type, x.mapping_basis_status, x.mapping_basis_title,
    x.mapping_basis_source, x.mapping_basis_locator, x.exclude_reasons, x.potential_cross_district_candidate]),
  [24, 8, 50, 20, 14, 42, 16, 14, 28, 12, 46, 48, 12], "BasisReview");

// Sheet 12: merged capacity accounting
{
  const targetSummary = new Map();
  for (const x of strict) targetSummary.set(x.mapped_dispatch_target, (targetSummary.get(x.mapped_dispatch_target) || 0) + 1);
  const rows = [
    ["环节", "数量", "说明"],
    ["现有白云strict practice候选", summary.existing_strict_practice_eligible, "Baiyun原始严格候选218"],
    ["strict跨区候选", summary.strict_cross_district_eligible, "已过challenge/现有practice去重，相似度<0.86"],
    ["跨池重复扣除", summary.challenge_duplicate_rows + summary.existing_practice_duplicate_rows, "challenge+practice两池"],
    ["合并practice总候选容量", summary.merged_practice_capacity, "=218+strict-重复"],
    ["距离500", summary.gap_to_500, ""],
    ["距离650", summary.gap_to_650, ""],
    ["距离800", summary.gap_to_800, ""],
    ...Array.from(targetSummary.entries()).map(([name, n]) => ["strict候选-"+name, n, "白云承办单位维度容量"]),
    ["潜在候选增量（人工核验+部门批准后）", summary.potential_cross_district_candidates - summary.strict_cross_district_eligible, "health/culture/公安等pending或needs_review"],
    ["潜在理论容量", summary.existing_strict_practice_eligible + summary.potential_cross_district_candidates, "需逐条人工核验，非正式容量"],
    ["500是否满足", summary.existing_strict_practice_eligible + summary.potential_cross_district_candidates >= 500 ? "潜在可满足（需核验）" : "未满足", ""],
  ];
  table("容量合并统计", ["环节", "数量", "说明"], rows.slice(1), [48, 18, 64], "CapacityMerge");
}

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const out = await SpreadsheetFile.exportXlsx(wb);
await out.save(outputPath);
const first = wb.worksheets.getItemAt(0);
console.log("sheets:", wb.worksheets.items.length);
console.log((await wb.inspect({ kind: "table", range: `${first.name}!A1:C22`, include: "values,formulas", tableMaxRows: 22, tableMaxCols: 3 })).ndjson);
console.log((await wb.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 100 }, summary: "formula errors" })).ndjson);
