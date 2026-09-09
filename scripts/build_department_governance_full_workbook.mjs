import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const inputDir = process.argv[2];
const outputPath = process.argv[3];
if (!inputDir || !outputPath) throw new Error("usage: node build_department_governance_full_workbook.mjs <input-dir> <output.xlsx>");
const readJson = async (name) => JSON.parse(await fs.readFile(path.join(inputDir, name), "utf8"));
const summary = await readJson("summary.json");
const nameRows = await readJson("all_name_governance.json");
const newBaiyun = await readJson("new_baiyun_targets.json");
const townAliases = await readJson("baiyun_town_aliases.json");
const publicCases = await readJson("public_service_candidates.json");
const municipalCases = await readJson("municipal_case_candidates.json");
const unknownNames = await readJson("unknown_scope_candidates.json");
const eligibleSample = await readJson("eligible_sample.json");
const exclusionStats = await readJson("exclusion_reason_stats.json");
const distribution = await readJson("eligible_distribution.json");

const wb = Workbook.create();
const font = "Arial";
const header = { fill: "#1F4E78", font: { name: font, bold: true, color: "#FFFFFF" }, wrapText: true, verticalAlignment: "center" };
const body = { font: { name: font, size: 10, color: "#1F2937" }, wrapText: true, verticalAlignment: "top" };
const statusValues = ["pending", "approved", "rejected", "needs_review"];

function addTableSheet(name, labels, rows, widths, tableName, reviewColumn = -1) {
  const sheet = wb.worksheets.add(name);
  sheet.showGridLines = false;
  const matrix = [labels, ...rows];
  sheet.getRangeByIndexes(0, 0, matrix.length, labels.length).values = matrix;
  sheet.getRangeByIndexes(0, 0, 1, labels.length).format = header;
  if (rows.length) sheet.getRangeByIndexes(1, 0, rows.length, labels.length).format = body;
  sheet.freezePanes.freezeRows(1);
  for (let i = 0; i < widths.length; i++) sheet.getRangeByIndexes(0, i, matrix.length, 1).format.columnWidth = widths[i];
  if (reviewColumn >= 0 && rows.length) {
    const range = sheet.getRangeByIndexes(1, reviewColumn, rows.length, 1);
    range.dataValidation = { rule: { type: "list", values: statusValues } };
    range.conditionalFormats.add("containsText", { text: "pending", format: { fill: "#FFF2CC", font: { color: "#7F6000" } } });
  }
  if (rows.length) sheet.tables.add(`A1:${columnName(labels.length)}${matrix.length}`, true, tableName).style = "TableStyleMedium2";
  return sheet;
}
function columnName(n) { let out = ""; while (n) { n--; out = String.fromCharCode(65 + n % 26) + out; n = Math.floor(n / 26); } return out; }
function groupTargets(rows) {
  const grouped = new Map();
  for (const x of rows) {
    const key = x.suggested_canonical_name || "待识别";
    const item = grouped.get(key) ?? { name: key, code: x.suggested_department_code, scope: x.department_scope, type: x.organization_type, aliases: [], cases: 0, status: "pending", note: "" };
    item.aliases.push(x.raw_department_name); item.cases += x.case_count; grouped.set(key, item);
  }
  return [...grouped.values()].sort((a, b) => b.cases - a.cases);
}

const overview = wb.worksheets.add("治理总览");
overview.showGridLines = false;
overview.getRange("A1:F1").merge(); overview.getRange("A1").values = [["全量承办单位治理与题源容量评估"]];
overview.getRange("A2:F2").merge(); overview.getRange("A2").values = [["范围：5,143条历史案例、754种历史承办名称。结果用于审核，不写正式承办单位或题库。"]];
overview.getRange("A4:C13").values = [
  ["案例漏斗", "数量", "说明"],
  ["原始案例", summary.funnel.raw_cases, "全部历史案例"],
  ["承办单位可识别", summary.funnel.recognizable_dispatch_target, "排除泛化标签和无法识别名称"],
  ["属于允许训练范围", summary.funnel.allowed_training_scope, "白云区、公共服务及条件市级单位"],
  ["地点明确为白云区", summary.funnel.baiyun_location_confirmed, "标题或事项内容明确出现白云区"],
  ["唯一承办单位", summary.funnel.unique_dispatch_target, "源字段仅含一个实际承办单位"],
  ["内容完整", summary.funnel.content_complete, "事项内容不少于30个规范化字符"],
  ["无可见复杂信号", summary.funnel.no_visible_complex_signal, "不补造退单、转派或争议结论"],
  ["严格 eligible", summary.funnel.strict_eligible, "市级逐案候选仍待人工批准"],
  ["待人工审核案例", summary.needs_review_count, "市级或地点边界项"],
];
overview.getRange("E4:F10").values = [
  ["容量判断", "结果"], ["当前严格 eligible", summary.eligible_count], ["距离600题", summary.gap_to_600],
  ["距离建议800题", summary.gap_to_800], ["容量区间", summary.capacity_band],
  ["其他区自动排除", summary.other_district_case_count], ["泛化标签排除", summary.generic_handler_case_count],
];
overview.getRange("A15:F15").merge(); overview.getRange("A15").values = [["口径说明"]];
overview.getRange("A16:F19").values = [
  [summary.method_note, null, null, null, null, null],
  ["公共服务单位只有地点明确为白云区才可自动进入；市级单位即使地点明确也必须逐案审核唯一责任。", null, null, null, null, null],
  ["广州政务和白云区政府等不能代表明确职责主体的泛化名称继续排除。", null, null, null, null, null],
  ["源数据不含可靠退单次数、转派链、主协办和争议结论，本工作簿不补造这些字段。", null, null, null, null, null],
];
for (let row = 16; row <= 19; row++) overview.getRange(`A${row}:F${row}`).merge();
overview.getRange("A1:F19").format = body; overview.getRange("A1").format.font = { name: font, size: 16, bold: true, color: "#111827" };
overview.getRange("A2").format.font = { name: font, size: 10, italic: true, color: "#4B5563" };
overview.getRange("A4:C4").format = header; overview.getRange("E4:F4").format = header;
overview.getRange("A15:F15").format = { fill: "#D9EAF7", font: { name: font, bold: true, color: "#1F2937" } };
overview.getRange("A:A").format.columnWidth = 28; overview.getRange("B:B").format.columnWidth = 14; overview.getRange("C:C").format.columnWidth = 44;
overview.getRange("D:D").format.columnWidth = 4; overview.getRange("E:E").format.columnWidth = 28; overview.getRange("F:F").format.columnWidth = 18;
overview.getRange("16:19").format.rowHeight = 27;

const baiyunGroups = groupTargets(newBaiyun.filter(x => !["subdistrict", "town"].includes(x.organization_type)));
addTableSheet("白云区承办单位", ["建议规范名称", "代码", "类型", "历史别名", "案例数", "审核状态", "审核备注"],
  baiyunGroups.map(x => [x.name, x.code, x.type, x.aliases.join("\n"), x.cases, x.status, x.note]),
  [40, 25, 22, 46, 12, 16, 36], "BaiyunTargets", 5);

const townGroups = groupTargets(townAliases);
addTableSheet("白云区镇街及别名", ["规范镇街", "代码", "类型", "历史别名", "案例数", "审核状态", "审核备注"],
  townGroups.map(x => [x.name, x.code, x.type, x.aliases.join("\n"), x.cases, x.status, x.note]),
  [40, 25, 15, 48, 12, 16, 34], "BaiyunTownAliases", 5);

const caseCols = x => [x.source_case_id, x.raw_department_name, x.canonical_dispatch_target, x.case_title, x.case_content, x.location_scope, x.location_reason, x.case_status, x.review_reason, x.review_status, x.review_note];
const caseLabels = ["案例ID", "历史承办名称", "规范承办单位", "案例标题", "事项内容", "地点范围", "地点判断依据", "案例状态", "审核原因", "审核状态", "审核备注"];
addTableSheet("公共服务候选", caseLabels, publicCases.map(caseCols), [22, 34, 38, 35, 70, 18, 38, 16, 28, 16, 34], "PublicServiceCases", 9);
addTableSheet("市级单位逐案候选", caseLabels, municipalCases.map(caseCols), [22, 34, 38, 35, 70, 18, 38, 16, 28, 16, 34], "MunicipalCases", 9);

addTableSheet("无法确定范围", ["排名", "历史承办名称", "规范化名称", "案例数", "匹配方法", "审核状态", "审核备注"],
  unknownNames.map(x => [x.rank, x.raw_department_name, x.normalized_name, x.case_count, x.match_method, x.review_status, x.review_note]),
  [10, 52, 48, 12, 24, 16, 38], "UnknownScope", 5);

addTableSheet("eligible案例抽样", ["案例ID", "规范承办单位", "类型", "历史承办名称", "标题", "事项内容", "地点范围", "复杂度"],
  eligibleSample.map(x => [x.source_case_id, x.canonical_dispatch_target, x.organization_type, x.raw_department_name, x.case_title, x.case_content, x.location_scope, x.complexity_status]),
  [22, 40, 20, 34, 35, 72, 20, 18], "EligibleSample");

addTableSheet("排除原因统计", ["原因", "案例数", "性质"],
  exclusionStats.map(x => [x.reason, x.case_count, x.reason.includes("review") ? "人工审核" : "排除"]),
  [42, 16, 18], "ExclusionStats");

const distributionSheet = addTableSheet("部门题源分布", ["规范承办单位", "eligible案例数", "占比", "累计占比", "高集中标记"],
  distribution.map(x => [x.canonical_dispatch_target, x.eligible_case_count, x.share, x.cumulative_share, x.concentration_flag]),
  [46, 18, 16, 18, 18], "EligibleDistribution");
if (distribution.length) {
  distributionSheet.getRange(`C2:D${distribution.length + 1}`).setNumberFormat("0.0%");
  distributionSheet.getRange(`E2:E${distribution.length + 1}`).conditionalFormats.add("containsText", { text: ">10%", format: { fill: "#FCE8B2", font: { color: "#7F6000", bold: true } } });
}

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const output = await SpreadsheetFile.exportXlsx(wb); await output.save(outputPath);
console.log((await wb.inspect({ kind: "table", range: "治理总览!A1:F19", include: "values,formulas", tableMaxRows: 25, tableMaxCols: 8 })).ndjson);
console.log((await wb.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 100 }, summary: "final formula error scan" })).ndjson);
for (const sheet of wb.worksheets.items) {
  const used = sheet.getUsedRange(true);
  const previewRows = Math.min(25, used.rowCount);
  const previewCols = used.columnCount;
  const previewRange = `A1:${columnName(previewCols)}${previewRows}`;
  const preview = await wb.render({ sheetName: sheet.name, range: previewRange, scale: sheet.name === "治理总览" ? 1.4 : 0.8, format: "png" });
  await fs.writeFile(path.join(inputDir, `${sheet.name}.png`), new Uint8Array(await preview.arrayBuffer()));
}
