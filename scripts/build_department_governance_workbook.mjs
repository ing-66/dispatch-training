import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const inputDir = process.argv[2];
const outputPath = process.argv[3];
if (!inputDir || !outputPath) throw new Error("usage: node build_department_governance_workbook.mjs <input-dir> <output.xlsx>");
const readJson = async (name) => JSON.parse(await fs.readFile(path.join(inputDir, name), "utf8"));
const summary = await readJson("summary.json");
const top50 = await readJson("top50_department_governance.json");
const allFrequency = await readJson("all_department_frequency.json");
const projected = await readJson("projected_in_scope_cases.json");

const canonicalGroups = new Map();
for (const row of top50) {
  const key = row.suggested_canonical_name || "待识别";
  const group = canonicalGroups.get(key) ?? {canonical_name:key, department_code:row.suggested_department_code, scope:row.department_scope,
    type:row.department_type, aliases:[], case_count:0, suggested_action:row.suggested_action};
  group.aliases.push(row.raw_department_name); group.case_count += row.case_count; canonicalGroups.set(key, group);
}
const canonical = [...canonicalGroups.values()].sort((a,b) => b.case_count-a.case_count);
const wb = Workbook.create();
const overview = wb.worksheets.add("治理概览");
const review = wb.worksheets.add("Top50待审核");
const groups = wb.worksheets.add("规范部门建议");
const frequency = wb.worksheets.add("全部名称频次");
const pool = wb.worksheets.add("预计新增案例");
const font = "Arial";
const header = {fill:"#1F4E78",font:{name:font,bold:true,color:"#FFFFFF"},wrapText:true};

overview.showGridLines = false;
overview.getRange("A1:F1").merge(); overview.getRange("A1").values = [["历史承办单位治理试跑"]];
overview.getRange("A2:F2").merge(); overview.getRange("A2").values = [["处理范围：历史承办单位名称频次 Top 50；全部建议均待人工审核，未写入正式部门表。"]];
overview.getRange("A4:B12").values = [
  ["统计项","结果"], ["原始案例",summary.raw_case_count], ["历史承办名称",summary.distinct_department_names],
  ["Top 20覆盖案例",summary.top_coverage_counts["20"]], ["Top 50覆盖案例",summary.top_coverage_counts["50"]],
  ["Top 100覆盖案例",summary.top_coverage_counts["100"]], ["Top 50规范部门建议",summary.top50_unique_canonical_suggestions],
  ["当前严格可出题池",summary.baseline_questionable_pool], ["安全批准Top 50后的预计池",summary.projected_pool_if_safe_top50_approved],
];
overview.getRange("D4:F9").values = [
  ["范围","名称数","案例数"],
  ["白云区",summary.top50_scope_name_counts.baiyun ?? 0,summary.top50_scope_case_counts.baiyun ?? 0],
  ["市级/全市",summary.top50_scope_name_counts.guangzhou_city ?? 0,summary.top50_scope_case_counts.guangzhou_city ?? 0],
  ["广州其他区",summary.top50_scope_name_counts.other_district ?? 0,summary.top50_scope_case_counts.other_district ?? 0],
  ["未知",summary.top50_scope_name_counts.unknown ?? 0,summary.top50_scope_case_counts.unknown ?? 0],
  ["合计",50,summary.top_coverage_counts["50"]],
];
overview.getRange("A14:F14").merge(); overview.getRange("A14").values = [["口径说明"]];
overview.getRange("A15:F17").values = [
  ["预计扩展只计算白云区单位，以及题面明确出现白云区地点信号的公共服务单位。",null,null,null,null,null],
  ["“广州政务”和市级部门继续保持待确认，不计入预计可出题池。",null,null,null,null,null],
  ["原始数据没有退单、转派、主办、协办和争议结论；复杂度统一保守标记为 needs_review。",null,null,null,null,null],
];
for (const row of [15,16,17]) overview.getRange(`A${row}:F${row}`).merge();
overview.getRange("A1:F17").format.font = {name:font,size:11,color:"#1F2937"};
overview.getRange("A1").format.font = {name:font,size:16,bold:true,color:"#111827"};
overview.getRange("A2").format.font = {name:font,size:10,italic:true,color:"#4B5563"};
overview.getRange("A4:B4").format = header; overview.getRange("D4:F4").format = header;
overview.getRange("A14:F14").format = {fill:"#D9EAF7",font:{name:font,bold:true,color:"#1F2937"}};
overview.getRange("A1:F17").format.wrapText = true;
overview.getRange("A:A").format.columnWidth=30; overview.getRange("B:B").format.columnWidth=18;
overview.getRange("C:C").format.columnWidth=5; overview.getRange("D:D").format.columnWidth=25;
overview.getRange("E:F").format.columnWidth=16; overview.getRange("15:17").format.rowHeight=28;

const reviewCols = ["rank","raw_department_name","normalized_name","suggested_canonical_name","suggested_department_code","department_scope","department_type","match_method","match_confidence","case_count","cumulative_case_count","cumulative_coverage","existing_department","suggested_action","review_status","review_note"];
const reviewLabels = ["排名","历史承办名称","归一化名称","建议规范名称","建议部门代码","范围","类型","匹配方法","置信度","案例数","累计案例数","累计覆盖率","现有部门","建议动作","审核状态","审核备注"];
const reviewRows = [reviewLabels,...top50.map(x=>reviewCols.map(k=>x[k]??""))];
review.getRangeByIndexes(0,0,reviewRows.length,reviewCols.length).values=reviewRows;
review.freezePanes.freezeRows(1); review.freezePanes.freezeColumns(2); review.showGridLines=false;
review.getRangeByIndexes(0,0,1,reviewCols.length).format=header;
review.getRangeByIndexes(1,0,top50.length,reviewCols.length).format={font:{name:font,size:10},wrapText:true,verticalAlignment:"top"};
review.getRange(`I2:I${top50.length+1}`).setNumberFormat("0%"); review.getRange(`L2:L${top50.length+1}`).setNumberFormat("0.0%");
review.getRange(`F2:F${top50.length+1}`).dataValidation={rule:{type:"list",values:["baiyun","guangzhou_city","other_district","unknown"]}};
review.getRange(`G2:G${top50.length+1}`).dataValidation={rule:{type:"list",values:["district_department","subdistrict_or_town","vertical_agency","public_service","municipal_department","other"]}};
review.getRange(`O2:O${top50.length+1}`).dataValidation={rule:{type:"list",values:["pending","approved","rejected","needs_review"]}};
review.getRange(`O2:O${top50.length+1}`).conditionalFormats.add("containsText",{text:"pending",format:{fill:"#FFF2CC",font:{color:"#7F6000"}}});
review.getRange("A:A").format.columnWidth=8; review.getRange("B:D").format.columnWidth=34; review.getRange("E:E").format.columnWidth=24;
review.getRange("F:H").format.columnWidth=22; review.getRange("I:M").format.columnWidth=14; review.getRange("N:P").format.columnWidth=24;
review.tables.add(`A1:P${reviewRows.length}`,true,"Top50Governance").style="TableStyleMedium2";

const groupRows = [["建议规范名称","建议部门代码","范围","类型","历史别名","覆盖案例","建议动作"],...canonical.map(x=>[x.canonical_name,x.department_code,x.scope,x.type,x.aliases.join("\n"),x.case_count,x.suggested_action])];
groups.getRangeByIndexes(0,0,groupRows.length,7).values=groupRows; groups.freezePanes.freezeRows(1); groups.showGridLines=false;
groups.getRange("A1:G1").format=header; groups.getRangeByIndexes(1,0,canonical.length,7).format={font:{name:font,size:10},wrapText:true,verticalAlignment:"top"};
groups.getRange("A:B").format.columnWidth=38; groups.getRange("C:D").format.columnWidth=20; groups.getRange("E:E").format.columnWidth=42; groups.getRange("F:F").format.columnWidth=14; groups.getRange("G:G").format.columnWidth=26;
groups.tables.add(`A1:G${groupRows.length}`,true,"CanonicalSuggestions").style="TableStyleMedium2";

const freqCols=["rank","raw_department_name","case_count","cumulative_case_count","cumulative_coverage","governance_status"];
const freqRows=[["排名","历史承办名称","案例数","累计案例数","累计覆盖率","治理状态"],...allFrequency.map(x=>freqCols.map(k=>x[k]))];
frequency.getRangeByIndexes(0,0,freqRows.length,6).values=freqRows; frequency.freezePanes.freezeRows(1); frequency.showGridLines=false;
frequency.getRange("A1:F1").format=header; frequency.getRangeByIndexes(1,0,allFrequency.length,6).format={font:{name:font,size:10},wrapText:true};
frequency.getRange(`E2:E${freqRows.length}`).setNumberFormat("0.0%"); frequency.getRange("A:A").format.columnWidth=9; frequency.getRange("B:B").format.columnWidth=52; frequency.getRange("C:F").format.columnWidth=18;
frequency.tables.add(`A1:F${freqRows.length}`,true,"AllDepartmentFrequency").style="TableStyleMedium4";

const poolCols=["source_case_id","raw_department_name","suggested_canonical_name","case_title","scope_reason","complexity_status"];
const poolRows=[["案例ID","历史承办名称","建议规范名称","案例标题","纳入预计池原因","复杂度状态"],...projected.map(x=>poolCols.map(k=>x[k]))];
pool.getRangeByIndexes(0,0,poolRows.length,6).values=poolRows; pool.freezePanes.freezeRows(1); pool.showGridLines=false;
pool.getRange("A1:F1").format=header; pool.getRangeByIndexes(1,0,projected.length,6).format={font:{name:font,size:10},wrapText:true,verticalAlignment:"top"};
pool.getRange("A:A").format.columnWidth=22; pool.getRange("B:C").format.columnWidth=38; pool.getRange("D:E").format.columnWidth=44; pool.getRange("F:F").format.columnWidth=20;
pool.tables.add(`A1:F${poolRows.length}`,true,"ProjectedCases").style="TableStyleMedium2";

await fs.mkdir(path.dirname(outputPath),{recursive:true});
const output=await SpreadsheetFile.exportXlsx(wb); await output.save(outputPath);
console.log((await wb.inspect({kind:"table",range:"治理概览!A1:F17",include:"values,formulas",tableMaxRows:20,tableMaxCols:8})).ndjson);
console.log((await wb.inspect({kind:"match",searchTerm:"#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",options:{useRegex:true,maxResults:100},summary:"final formula error scan"})).ndjson);
const ranges={"治理概览":"A1:F17","Top50待审核":"A1:P16","规范部门建议":"A1:G20","全部名称频次":"A1:F25","预计新增案例":"A1:F25"};
for(const [sheetName,range] of Object.entries(ranges)){
  const preview=await wb.render({sheetName,range,scale:sheetName==="治理概览"?1.5:1,format:"png"});
  await fs.writeFile(path.join(inputDir,`${sheetName}.png`),new Uint8Array(await preview.arrayBuffer()));
}
