import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const inputDir = process.argv[2], outputPath = process.argv[3];
if (!inputDir || !outputPath) throw new Error("usage: node build_challenge_finalization_workbook.mjs <input-dir> <output.xlsx>");
const readJson = async n => JSON.parse(await fs.readFile(path.join(inputDir, n), "utf8"));
const candidates = await readJson("candidates_finalized.json");
const aliases = await readJson("dispatch_target_alias_review.json");
const stats = await readJson("level_statistics.json");
const summary = await readJson("summary.json");
const recommended = await readJson("recommended_pool.json");
const rejects = await readJson("suggested_rejections.json");

const wb = Workbook.create(), font = "Microsoft YaHei";
const header = { fill: "#1F4E78", font: { name: font, bold: true, color: "#FFFFFF" }, wrapText: true, verticalAlignment: "center" };
const body = { font: { name: font, size: 10, color: "#1F2937" }, wrapText: true, verticalAlignment: "top" };
const reviewValues = ["pending", "approved", "rejected", "needs_revision"];
function colName(n) { let s=""; while(n){n--;s=String.fromCharCode(65+n%26)+s;n=Math.floor(n/26);} return s; }
function addTable(name, labels, rows, widths, tableName, reviewCol=-1) {
  const sh=wb.worksheets.add(name); sh.showGridLines=false;
  const matrix=[labels,...rows]; sh.getRangeByIndexes(0,0,matrix.length,labels.length).values=matrix;
  sh.getRangeByIndexes(0,0,1,labels.length).format=header;
  if(rows.length) sh.getRangeByIndexes(1,0,rows.length,labels.length).format=body;
  sh.freezePanes.freezeRows(1); sh.freezePanes.freezeColumns(Math.min(2,labels.length));
  widths.forEach((w,i)=>sh.getRangeByIndexes(0,i,matrix.length,1).format.columnWidth=w);
  if(reviewCol>=0&&rows.length){const r=sh.getRangeByIndexes(1,reviewCol,rows.length,1);r.dataValidation={rule:{type:"list",values:reviewValues}};r.conditionalFormats.add("containsText",{text:"pending",format:{fill:"#FFF2CC",font:{color:"#7F6000"}}});}
  if(rows.length) sh.tables.add(`A1:${colName(labels.length)}${matrix.length}`,true,tableName).style="TableStyleMedium2";
  return sh;
}
const qLabels=["案例ID","原始工单","正确承办单位","错误选项1","错误选项2","错误选项3","维度1","理由1","维度2","理由2","维度3","理由3","维度4","理由4","维度5","理由5","总难度","原关卡","新关卡","高相关干扰项数","梯度适配分","梯度说明","核心诉求","责任判断","解析","依据状态","依据标题","依据原文","依据定位","依据说明","推荐分","终审推荐","审核状态","审核意见"];
const qWidths=[22,68,39,36,36,36,10,34,10,34,10,36,10,34,10,34,12,11,11,15,13,42,32,52,60,16,32,62,64,48,12,14,14,34];
const qRow=x=>[x.source_case_id,x.case_content,x.correct_department_name,x.wrong_department_1,x.wrong_department_2,x.wrong_department_3,x.difficulty_dimension_1,x.difficulty_dimension_1_reason,x.difficulty_dimension_2,x.difficulty_dimension_2_reason,x.difficulty_dimension_3,x.difficulty_dimension_3_reason,x.difficulty_dimension_4,x.difficulty_dimension_4_reason,x.difficulty_dimension_5,x.difficulty_dimension_5_reason,x.difficulty_score,x.previous_suggested_level,x.suggested_level,x.high_related_distractor_count,x.level_fit_score,x.level_fit_review,x.core_issue,x.responsibility_reasoning,x.explanation,x.reference_basis_status,x.reference_basis_title,x.reference_basis_excerpt,x.reference_basis_locator,x.reference_basis_reason,x.final_selection_score,x.final_recommendation,x.review_status,x.review_note];

const overview=wb.worksheets.add("最终候选总览"); overview.showGridLines=false;
overview.getRange("A1:H1").merge();overview.getRange("A1").values=[["正式闯关题终审与梯度校准"]];
overview.getRange("A2:H2").merge();overview.getRange("A2").values=[["仅供人工终审：recommended 不等于 approved；未导入数据库。"]];
overview.getRange("A4:C14").values=[["统计项","数量","说明"],["候选题",summary.candidate_count,"全部 review_status=pending"],["规范承办单位",summary.canonical_target_count,"别名统一后"],["别名记录",summary.alias_record_count,"其中纠正规范记录 "+summary.corrected_alias_count],["依据已核验",summary.reference_basis_status.verified,"有直接相关原文"],["依据待审核",summary.reference_basis_status.needs_review,"有单位资料，待人工定位"],["依据不足",summary.reference_basis_status.insufficient,"降低选择优先级"],["依据冲突",summary.reference_basis_status.conflict,"明确冲突才建议直接淘汰"],["关卡调整",summary.suggested_level_adjustment_count,"相对分布校准"],["推荐池",summary.recommended_count,"每关12–13题，不含依据不足"],["建议淘汰",summary.suggested_reject_count,"不把依据不足自动判为淘汰"]];
overview.getRange("E4:H14").values=[["关卡","候选数","平均难度","高相关干扰项均值"],...stats.map(x=>[`Level ${x.level}`,x.candidate_count,x.average_difficulty_score,x.average_related_distractors])];
overview.getRange("A16:H16").merge();overview.getRange("A16").values=[["终审原则：逐题确认规范承办单位、唯一答案和职责依据；从每关推荐的12–13题中人工选10题，必要时退回修订。"]];
overview.getRange("A1:H16").format=body;overview.getRange("A1").format.font={name:font,size:16,bold:true,color:"#111827"};overview.getRange("A2").format.font={name:font,italic:true,color:"#4B5563"};overview.getRange("A4:C4").format=header;overview.getRange("E4:H4").format=header;overview.getRange("A16:H16").format={fill:"#D9EAF7",font:{name:font,bold:true},wrapText:true};
[25,16,45,4,16,14,16,22].forEach((w,i)=>overview.getRangeByIndexes(0,i,16,1).format.columnWidth=w);overview.getRange("16:16").format.rowHeight=32;

addTable("承办单位规范化检查",["历史名称","原规范名","终审规范名","部门代码","单位类型","别名状态","审核状态","审核意见"],aliases.map(x=>[x.raw_name,x.previous_canonical_name,x.canonical_name,x.canonical_code,x.organization_type,x.alias_status,x.review_status,x.review_note]),[38,38,42,25,20,16,14,38],"AliasReview",6);
const evidenceLabels=["案例ID","正确承办单位","核心诉求","依据标题","来源类型","职责原文摘录","文件及段落定位","匹配说明","依据状态","审核状态","审核意见"];
const evidenceRow=x=>[x.source_case_id,x.correct_department_name,x.core_issue,x.reference_basis_title,x.reference_basis_source,x.reference_basis_excerpt,x.reference_basis_locator,x.reference_basis_reason,x.reference_basis_status,x.review_status,x.review_note];
const evidenceWidths=[22,42,34,34,18,72,72,54,16,14,36];
addTable("职责依据已核验",evidenceLabels,candidates.filter(x=>x.reference_basis_status==="verified").map(evidenceRow),evidenceWidths,"EvidenceVerified",9);
addTable("职责依据待审核",evidenceLabels,candidates.filter(x=>x.reference_basis_status==="needs_review").map(evidenceRow),evidenceWidths,"EvidencePending",9);
addTable("职责依据不足冲突",evidenceLabels,candidates.filter(x=>["insufficient","conflict"].includes(x.reference_basis_status)).map(evidenceRow),evidenceWidths,"EvidenceIssues",9);
for(const [name,items,t] of [["Level 1-3",candidates.filter(x=>x.suggested_level<=3),"FinalLow"],["Level 4-6",candidates.filter(x=>x.suggested_level>=4&&x.suggested_level<=6),"FinalMid"],["Level 7-10",candidates.filter(x=>x.suggested_level>=7),"FinalHigh"]]) addTable(name,qLabels,items.map(qRow),qWidths,t,32);
addTable("关卡梯度统计",["关卡","候选数","平均总难度","诉求明确度均值","职责边界均值","易错相似度均值","高相关干扰项均值","非verified数","推荐数"],stats.map(x=>[x.level,x.candidate_count,x.average_difficulty_score,x.average_clarity,x.average_boundary,x.average_similarity,x.average_related_distractors,x.needs_review_count,recommended.filter(r=>r.suggested_level===x.level).length]),[12,14,16,18,18,20,22,16,14],"GradientStats");
const rejectRows=rejects.map(qRow); const rejectSheet=addTable("建议淘汰题",qLabels,rejectRows,qWidths,"SuggestedRejects",32); if(!rejectRows.length){rejectSheet.getRange("A3:H3").merge();rejectSheet.getRange("A3").values=[["当前无明确职责冲突题，故不自动建议淘汰；27道依据不足题已降低优先级并排除在推荐池外。"]];rejectSheet.getRange("A3:H3").format={fill:"#FFF2CC",font:{name:font,color:"#7F6000"},wrapText:true};}
addTable("最终100题推荐池",qLabels,recommended.map(qRow),qWidths,"RecommendedPool",32);

await fs.mkdir(path.dirname(outputPath),{recursive:true}); const out=await SpreadsheetFile.exportXlsx(wb); await out.save(outputPath);
console.log((await wb.inspect({kind:"table",range:"最终候选总览!A1:H16",include:"values,formulas",tableMaxRows:20,tableMaxCols:10})).ndjson);
console.log((await wb.inspect({kind:"match",searchTerm:"#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",options:{useRegex:true,maxResults:100},summary:"formula errors"})).ndjson);
for(const sh of wb.worksheets.items){const used=sh.getUsedRange(true), rows=Math.min(14,used.rowCount), cols=used.columnCount;const preview=await wb.render({sheetName:sh.name,range:`A1:${colName(cols)}${rows}`,scale:sh.name==="最终候选总览"?1.15:0.45,format:"png"});await fs.writeFile(path.join(inputDir,`preview-${sh.name}.png`),new Uint8Array(await preview.arrayBuffer()));}
