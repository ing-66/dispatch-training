import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const inputDir = process.argv[2];
const outputPath = process.argv[3];
if (!inputDir || !outputPath) throw new Error("usage: node build_challenge_review_workbook.mjs <input-dir> <output.xlsx>");
const readJson = async name => JSON.parse(await fs.readFile(path.join(inputDir, name), "utf8"));
const summary = await readJson("summary.json");
const candidates = await readJson("candidates.json");
const distribution = await readJson("target_distribution.json");

const wb = Workbook.create();
const font = "Arial";
const header = { fill: "#1F4E78", font: { name: font, bold: true, color: "#FFFFFF" }, wrapText: true, verticalAlignment: "center" };
const body = { font: { name: font, size: 10, color: "#1F2937" }, wrapText: true, verticalAlignment: "top" };
const reviewValues = ["pending", "approved", "rejected", "needs_revision"];
function colName(n) { let out = ""; while (n) { n--; out = String.fromCharCode(65 + n % 26) + out; n = Math.floor(n / 26); } return out; }
function addTable(name, labels, rows, widths, tableName, reviewCol = -1) {
  const sheet = wb.worksheets.add(name); sheet.showGridLines = false;
  const matrix = [labels, ...rows];
  sheet.getRangeByIndexes(0, 0, matrix.length, labels.length).values = matrix;
  sheet.getRangeByIndexes(0, 0, 1, labels.length).format = header;
  if (rows.length) sheet.getRangeByIndexes(1, 0, rows.length, labels.length).format = body;
  sheet.freezePanes.freezeRows(1); sheet.freezePanes.freezeColumns(Math.min(2, labels.length));
  widths.forEach((width, index) => sheet.getRangeByIndexes(0, index, matrix.length, 1).format.columnWidth = width);
  if (reviewCol >= 0 && rows.length) {
    const range = sheet.getRangeByIndexes(1, reviewCol, rows.length, 1);
    range.dataValidation = { rule: { type: "list", values: reviewValues } };
    range.conditionalFormats.add("containsText", { text: "pending", format: { fill: "#FFF2CC", font: { color: "#7F6000" } } });
  }
  if (rows.length) sheet.tables.add(`A1:${colName(labels.length)}${matrix.length}`, true, tableName).style = "TableStyleMedium2";
  return sheet;
}

const overview = wb.worksheets.add("候选题总览"); overview.showGridLines = false;
overview.getRange("A1:F1").merge(); overview.getRange("A1").values = [["正式闯关题候选总览"]];
overview.getRange("A2:F2").merge(); overview.getRange("A2").values = [["本批次只提供180道候选和建议关卡。所有题目默认 pending，不写正式数据库。"]];
overview.getRange("A4:C12").values = [
  ["统计项", "数量", "说明"], ["严格题源输入", summary.strict_eligible_input, "来自Phase 2.1 strict eligible"],
  ["闯关候选", summary.candidate_count, "按承办单位轮转并控制单单位上限"], ["覆盖承办单位", summary.candidate_target_count, "规范 dispatch target"],
  ["单单位候选上限", summary.per_target_cap, "避免高频镇街占据候选池"], ["近重复剔除", summary.duplicate_excluded_count, "同承办单位三字片段相似度阈值0.86"],
  ["职责依据待核验", summary.reference_basis_needs_review_count, "未把历史承办结果冒充职责条款"], ["疑难题", summary.difficult_review_count, "高难度或建议Level 9-10"],
  ["审核状态", "pending", "人工改为approved/rejected/needs_revision"],
];
overview.getRange("E4:F14").values = [["建议关卡", "候选数"], ...Array.from({length: 10}, (_, i) => [`Level ${i + 1}`, summary.suggested_level_distribution[String(i + 1)]])];
overview.getRange("A14:C19").values = [
  ["难度维度", "平均分", "范围"],
  ["诉求明确度", summary.difficulty_summary.dimension_1.average, `${summary.difficulty_summary.dimension_1.min}-${summary.difficulty_summary.dimension_1.max}`],
  ["唯一性判断", summary.difficulty_summary.dimension_2.average, `${summary.difficulty_summary.dimension_2.min}-${summary.difficulty_summary.dimension_2.max}`],
  ["职责边界", summary.difficulty_summary.dimension_3.average, `${summary.difficulty_summary.dimension_3.min}-${summary.difficulty_summary.dimension_3.max}`],
  ["信息判断", summary.difficulty_summary.dimension_4.average, `${summary.difficulty_summary.dimension_4.min}-${summary.difficulty_summary.dimension_4.max}`],
  ["易错相似度", summary.difficulty_summary.dimension_5.average, `${summary.difficulty_summary.dimension_5.min}-${summary.difficulty_summary.dimension_5.max}`],
];
overview.getRange("A21:F21").merge(); overview.getRange("A21").values = [["最终100题建议：各Level从18道候选中人工选10道，检查职责依据、题面价值和部门覆盖；不要按总分机械截取。"]];
overview.getRange("A1:F21").format = body; overview.getRange("A1").format.font = { name: font, size: 16, bold: true, color: "#111827" };
overview.getRange("A2").format.font = { name: font, size: 10, italic: true, color: "#4B5563" };
overview.getRange("A4:C4").format = header; overview.getRange("E4:F4").format = header; overview.getRange("A14:C14").format = header;
overview.getRange("A21:F21").format = { fill: "#D9EAF7", font: { name: font, bold: true, color: "#1F2937" }, wrapText: true };
overview.getRange("A:A").format.columnWidth = 27; overview.getRange("B:B").format.columnWidth = 16; overview.getRange("C:C").format.columnWidth = 46;
overview.getRange("D:D").format.columnWidth = 4; overview.getRange("E:E").format.columnWidth = 20; overview.getRange("F:F").format.columnWidth = 16; overview.getRange("21:21").format.rowHeight = 30;

const labels = ["案例ID", "原始工单", "正确承办单位", "错误选项1", "错误选项2", "错误选项3",
  "诉求明确度", "理由1", "唯一性难度", "理由2", "职责边界", "理由3", "信息判断", "理由4", "易错相似度", "理由5",
  "总难度", "干扰项难度", "建议关卡", "核心诉求", "责任判断", "固定解析", "参考依据", "依据状态", "审核状态", "审核意见"];
const widths = [22, 72, 40, 38, 38, 38, 13, 38, 13, 38, 13, 42, 13, 38, 13, 38, 13, 20, 13, 36, 58, 72, 56, 18, 16, 38];
const row = x => [x.source_case_id, x.case_content, x.correct_department_name, x.wrong_department_1, x.wrong_department_2, x.wrong_department_3,
  x.difficulty_dimension_1, x.difficulty_dimension_1_reason, x.difficulty_dimension_2, x.difficulty_dimension_2_reason,
  x.difficulty_dimension_3, x.difficulty_dimension_3_reason, x.difficulty_dimension_4, x.difficulty_dimension_4_reason,
  x.difficulty_dimension_5, x.difficulty_dimension_5_reason, x.difficulty_score, x.distractor_difficulty, x.suggested_level,
  x.core_issue, x.responsibility_reasoning, x.explanation, x.reference_basis, x.reference_basis_status, x.review_status, x.review_note];
const bands = [
  ["Level 1-3", candidates.filter(x => x.suggested_level <= 3), "LevelLow"],
  ["Level 4-6", candidates.filter(x => x.suggested_level >= 4 && x.suggested_level <= 6), "LevelMid"],
  ["Level 7-10", candidates.filter(x => x.suggested_level >= 7), "LevelHigh"],
];
for (const [name, items, tableName] of bands) addTable(name, labels, items.map(row), widths, tableName, 24);

const distSheet = addTable("承办单位分布", ["规范承办单位", "候选数", "占比", "累计占比", "建议最终上限", "说明"],
  distribution.map(x => [x.canonical_dispatch_target, x.candidate_count, x.share, x.cumulative_share, Math.min(4, x.candidate_count), "最终100题兼顾覆盖面，不按原始频次直接抽取"]),
  [46, 14, 14, 16, 18, 48], "CandidateDistribution");
if (distribution.length) distSheet.getRange(`C2:D${distribution.length + 1}`).setNumberFormat("0.0%");

const basis = candidates.filter(x => x.reference_basis_status === "needs_review");
addTable("需要补充职责依据", ["案例ID", "正确承办单位", "核心诉求", "责任判断", "当前参考依据", "依据状态", "审核状态", "审核意见"],
  basis.map(x => [x.source_case_id, x.correct_department_name, x.core_issue, x.responsibility_reasoning, x.reference_basis, x.reference_basis_status, x.review_status, x.review_note]),
  [22, 42, 38, 70, 58, 18, 16, 38], "BasisReview", 6);

const difficult = candidates.filter(x => x.issue_status === "difficult_review");
addTable("疑难争议题", ["案例ID", "正确承办单位", "原始工单", "总难度", "建议关卡", "干扰项难度", "五维分数", "疑难原因", "审核状态", "审核意见"],
  difficult.map(x => [x.source_case_id, x.correct_department_name, x.case_content, x.difficulty_score, x.suggested_level, x.distractor_difficulty,
    [1,2,3,4,5].map(i => x[`difficulty_dimension_${i}`]).join(" / "), x.difficulty_score >= 68 ? "难度评分较高，需重点核查唯一答案和职责边界" : "建议Level 9-10，需重点核查高相似干扰项", x.review_status, x.review_note]),
  [22, 42, 72, 14, 14, 20, 22, 52, 16, 38], "DifficultReview", 8);

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const output = await SpreadsheetFile.exportXlsx(wb); await output.save(outputPath);
console.log((await wb.inspect({ kind: "table", range: "候选题总览!A1:F21", include: "values,formulas", tableMaxRows: 24, tableMaxCols: 8 })).ndjson);
console.log((await wb.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 100 }, summary: "final formula error scan" })).ndjson);
for (const sheet of wb.worksheets.items) {
  const used = sheet.getUsedRange(true); const rows = Math.min(16, used.rowCount); const cols = used.columnCount;
  const preview = await wb.render({ sheetName: sheet.name, range: `A1:${colName(cols)}${rows}`, scale: sheet.name === "候选题总览" ? 1.3 : 0.55, format: "png" });
  await fs.writeFile(path.join(inputDir, `${sheet.name}.png`), new Uint8Array(await preview.arrayBuffer()));
}
