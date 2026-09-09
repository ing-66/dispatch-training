import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const inputDir = process.argv[2];
const outputPath = process.argv[3];
if (!inputDir || !outputPath) throw new Error("usage: node build_review_workbook.mjs <input-dir> <output.xlsx>");

const readJson = async (name) => JSON.parse(await fs.readFile(path.join(inputDir, name), "utf8"));
const summary = await readJson("summary.json");
const candidates = await readJson("candidates.json");
const departments = await readJson("departments.json");

const excludedText = await fs.readFile(path.join(inputDir, "excluded.csv"), "utf8");
const excludedLines = excludedText.replace(/^\uFEFF/, "").split(/\r?\n/).filter(Boolean);
const parseCsvLine = (line) => {
  const out = []; let value = ""; let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (c === '"' && quoted && line[i + 1] === '"') { value += '"'; i++; }
    else if (c === '"') quoted = !quoted;
    else if (c === ',' && !quoted) { out.push(value); value = ""; }
    else value += c;
  }
  out.push(value); return out;
};
const excluded = excludedLines.map(parseCsvLine);

const wb = Workbook.create();
const summarySheet = wb.worksheets.add("生产概览");
const candidateSheet = wb.worksheets.add("待审核题目");
const excludedSheet = wb.worksheets.add("排除案例");
const departmentSheet = wb.worksheets.add("部门主数据");
const font = "Arial";

summarySheet.showGridLines = false;
summarySheet.getRange("A1:F1").merge();
summarySheet.getRange("A1").values = [["正式题库测试生产概览"]];
summarySheet.getRange("A2:F2").merge();
summarySheet.getRange("A2").values = [["数据范围：5个官方历史工单 Markdown 文件；本表仅用于人工审核，未写入正式训练数据库。"]];
summarySheet.getRange("A4:B10").values = [
  ["指标", "数量"], ["源文件", summary.source_files], ["原始案例", summary.raw_case_count],
  ["合格案例", summary.eligible_count], ["排除案例", summary.excluded_count],
  ["本轮待审核题目", summary.test_candidate_count], ["权威部门主数据", departments.length],
];
summarySheet.getRange("D4:E4").values = [["主要排除原因", "数量"]];
const reasonLabels = {
  department_not_in_master: "部门不在权威主数据",
  multiple_departments: "包含多个承办部门",
  case_content_missing_or_too_short: "事项内容缺失或过短",
  possible_dispute_or_complex_collaboration: "疑似争议或复杂主协办",
  missing_final_department: "最终承办部门缺失",
  ambiguous_department_mapping: "部门映射不唯一",
};
const reasonRows = Object.entries(summary.exclude_reasons).map(([key, value]) => [reasonLabels[key] ?? key, value]);
summarySheet.getRangeByIndexes(4, 3, reasonRows.length, 2).values = reasonRows;
summarySheet.getRange("A12:F15").values = [
  ["审核说明", null, null, null, null, null],
  ["1", "逐题核对唯一承办部门及三个干扰项，确认部门名称和代码均来自“部门主数据”。", null, null, null, null],
  ["2", "补充或核实职责依据后，将 reference_basis_status 改为 verified。", null, null, null, null],
  ["3", "只有业务人员将 review_status 改为 approved 后，题目才允许进入正式导入。", null, null, null, null],
];
for (const row of [13, 14, 15]) summarySheet.getRange(`B${row}:F${row}`).merge();
summarySheet.getRange("A1:F15").format.font = {name: font, size: 11, color: "#1F2937"};
summarySheet.getRange("A1").format.font = {name: font, size: 16, bold: true, color: "#111827"};
summarySheet.getRange("A2").format.font = {name: font, size: 10, italic: true, color: "#4B5563"};
summarySheet.getRange("A4:B4").format = {fill: "#1F4E78", font: {name: font, bold: true, color: "#FFFFFF"}};
summarySheet.getRange("D4:E4").format = {fill: "#1F4E78", font: {name: font, bold: true, color: "#FFFFFF"}};
summarySheet.getRange("A12:F12").format = {fill: "#D9EAF7", font: {name: font, bold: true, color: "#1F2937"}};
summarySheet.getRange("A1:F15").format.wrapText = true;
summarySheet.getRange("A:A").format.columnWidth = 24;
summarySheet.getRange("B:B").format.columnWidth = 18;
summarySheet.getRange("C:C").format.columnWidth = 4;
summarySheet.getRange("D:D").format.columnWidth = 40;
summarySheet.getRange("E:E").format.columnWidth = 16;
summarySheet.getRange("F:F").format.columnWidth = 4;
summarySheet.getRange("13:15").format.rowHeight = 34;

const candidateColumns = [
  "source_case_id","source_file","case_title","case_content","correct_department_id","correct_department_name",
  "wrong_department_1_id","wrong_department_1","wrong_department_2_id","wrong_department_2","wrong_department_3_id","wrong_department_3",
  "explanation","reference_basis","reference_basis_status",
  "difficulty_dimension_1","difficulty_dimension_1_reason","difficulty_dimension_2","difficulty_dimension_2_reason",
  "difficulty_dimension_3","difficulty_dimension_3_reason","difficulty_dimension_4","difficulty_dimension_4_reason",
  "difficulty_dimension_5","difficulty_dimension_5_reason","difficulty_score","suggested_level","question_type","review_status","review_note"
];
const candidateLabels = [
  "案例ID","来源文件","案例标题","题干","正确部门代码","正确部门名称","干扰项1代码","干扰项1","干扰项2代码","干扰项2","干扰项3代码","干扰项3",
  "答案解析","参考依据","依据状态","诉求明确度","评分理由1","唯一性判断难度","评分理由2","职责边界复杂度","评分理由3",
  "信息判断难度","评分理由4","易错部门相似度","评分理由5","难度总分","建议关卡","题型","审核状态","审核备注"
];
const candidateRows = [candidateLabels, ...candidates.map(x => candidateColumns.map(k => x[k] ?? ""))];
candidateSheet.getRangeByIndexes(0, 0, candidateRows.length, candidateColumns.length).values = candidateRows;
candidateSheet.showGridLines = false;
candidateSheet.freezePanes.freezeRows(1);
candidateSheet.freezePanes.freezeColumns(3);
candidateSheet.getRangeByIndexes(0, 0, 1, candidateColumns.length).format = {fill: "#1F4E78", font: {name: font, bold: true, color: "#FFFFFF"}, wrapText: true};
candidateSheet.getRangeByIndexes(1, 0, candidates.length, candidateColumns.length).format.font = {name: font, size: 10, color: "#1F2937"};
candidateSheet.getRangeByIndexes(1, 0, candidates.length, candidateColumns.length).format.verticalAlignment = "top";
candidateSheet.getRangeByIndexes(1, 0, candidates.length, candidateColumns.length).format.wrapText = true;
candidateSheet.getRange(`P2:P${candidates.length + 1}`).setNumberFormat("0");
candidateSheet.getRange(`R2:R${candidates.length + 1}`).setNumberFormat("0");
candidateSheet.getRange(`T2:T${candidates.length + 1}`).setNumberFormat("0");
candidateSheet.getRange(`V2:V${candidates.length + 1}`).setNumberFormat("0");
candidateSheet.getRange(`X2:X${candidates.length + 1}`).setNumberFormat("0");
candidateSheet.getRange(`Z2:AA${candidates.length + 1}`).setNumberFormat("0");
candidateSheet.getRange(`AC2:AC${candidates.length + 1}`).dataValidation = {rule: {type: "list", values: ["pending","approved","rejected","needs_revision"]}};
candidateSheet.getRange(`O2:O${candidates.length + 1}`).dataValidation = {rule: {type: "list", values: ["needs_review","verified"]}};
candidateSheet.getRange(`AC2:AC${candidates.length + 1}`).conditionalFormats.add("containsText", {text: "pending", format: {fill: "#FFF2CC", font: {color: "#7F6000"}}});
candidateSheet.getRange("A:A").format.columnWidth = 20;
candidateSheet.getRange("B:C").format.columnWidth = 20;
candidateSheet.getRange("D:D").format.columnWidth = 48;
candidateSheet.getRange("E:L").format.columnWidth = 22;
candidateSheet.getRange("M:N").format.columnWidth = 42;
candidateSheet.getRange("O:AC").format.columnWidth = 18;
candidateSheet.getRange("Q:Q").format.columnWidth = 32;
candidateSheet.getRange("S:S").format.columnWidth = 32;
candidateSheet.getRange("U:U").format.columnWidth = 32;
candidateSheet.getRange("W:W").format.columnWidth = 32;
candidateSheet.getRange("Y:Y").format.columnWidth = 32;
candidateSheet.getRange("AD:AD").format.columnWidth = 32;
candidateSheet.tables.add(`A1:AD${candidateRows.length}`, true, "CandidateQuestions").style = "TableStyleMedium2";

excludedSheet.getRangeByIndexes(0, 0, excluded.length, excluded[0].length).values = excluded;
excludedSheet.freezePanes.freezeRows(1);
excludedSheet.showGridLines = false;
excludedSheet.getRangeByIndexes(0, 0, 1, excluded[0].length).format = {fill: "#595959", font: {name: font, bold: true, color: "#FFFFFF"}};
excludedSheet.getRangeByIndexes(1, 0, excluded.length - 1, excluded[0].length).format.font = {name: font, size: 10};
excludedSheet.getRange("A:E").format.wrapText = true;
excludedSheet.getRange("A:A").format.columnWidth = 20;
excludedSheet.getRange("B:B").format.columnWidth = 14;
excludedSheet.getRange("C:D").format.columnWidth = 34;
excludedSheet.getRange("E:E").format.columnWidth = 34;
excludedSheet.tables.add(`A1:E${excluded.length}`, true, "ExcludedCases").style = "TableStyleMedium4";

const deptRows = [["部门代码","部门名称","部门类型","权威来源"], ...departments.map(x => [x.department_code,x.department_name,x.department_kind,x.source_paths.join("\n")])];
departmentSheet.getRangeByIndexes(0, 0, deptRows.length, 4).values = deptRows;
departmentSheet.freezePanes.freezeRows(1);
departmentSheet.showGridLines = false;
departmentSheet.getRange("A1:D1").format = {fill: "#1F4E78", font: {name: font, bold: true, color: "#FFFFFF"}};
departmentSheet.getRangeByIndexes(1, 0, departments.length, 4).format = {font: {name: font, size: 10}, wrapText: true, verticalAlignment: "top"};
departmentSheet.getRange("A:A").format.columnWidth = 24;
departmentSheet.getRange("B:B").format.columnWidth = 36;
departmentSheet.getRange("C:C").format.columnWidth = 14;
departmentSheet.getRange("D:D").format.columnWidth = 64;
departmentSheet.tables.add(`A1:D${deptRows.length}`, true, "DepartmentMaster").style = "TableStyleMedium2";

await fs.mkdir(path.dirname(outputPath), {recursive: true});
const output = await SpreadsheetFile.exportXlsx(wb);
await output.save(outputPath);

const checks = await wb.inspect({kind: "table", range: "生产概览!A1:F15", include: "values,formulas", tableMaxRows: 20, tableMaxCols: 8});
console.log(checks.ndjson);
const errors = await wb.inspect({kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: {useRegex: true, maxResults: 100}, summary: "final formula error scan"});
console.log(errors.ndjson);
const previewRanges = {"生产概览": "A1:F15", "待审核题目": "A1:AD12", "排除案例": "A1:E30", "部门主数据": `A1:D${deptRows.length}`};
for (const sheetName of ["生产概览","待审核题目","排除案例","部门主数据"]) {
  const preview = await wb.render({sheetName, range: previewRanges[sheetName], scale: sheetName === "生产概览" ? 1.5 : 0.8, format: "png"});
  await fs.writeFile(path.join(inputDir, `${sheetName}.png`), new Uint8Array(await preview.arrayBuffer()));
}
