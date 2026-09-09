import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [mode, inputPath, outputPath] = process.argv.slice(2);
if (!mode || !outputPath) throw new Error("usage: node build_practice_ingest_workbooks.mjs <review|template|fixture> <input> <output.xlsx>");
const wb = Workbook.create(), font = "Arial";
const header = { fill: "#1F4E78", font: { name: font, bold: true, color: "#FFFFFF" }, wrapText: true, verticalAlignment: "center", horizontalAlignment: "center" };
const body = { font: { name: font, size: 10, color: "#1F2937" }, wrapText: true, verticalAlignment: "top" };
function colName(n){let s="";while(n){n--;s=String.fromCharCode(65+n%26)+s;n=Math.floor(n/26);}return s;}
function table(name, labels, rows, widths, tableName){const sh=wb.worksheets.add(name);sh.showGridLines=false;const matrix=[labels,...rows];sh.getRangeByIndexes(0,0,matrix.length,labels.length).values=matrix;sh.getRangeByIndexes(0,0,1,labels.length).format=header;if(rows.length)sh.getRangeByIndexes(1,0,rows.length,labels.length).format=body;sh.freezePanes.freezeRows(1);sh.freezePanes.freezeColumns(Math.min(2,labels.length));widths.forEach((w,i)=>sh.getRangeByIndexes(0,i,matrix.length,1).format.columnWidth=w);if(rows.length)sh.tables.add(`A1:${colName(labels.length)}${matrix.length}`,true,tableName).style="TableStyleMedium2";return sh;}
function value(v){return Array.isArray(v)?v.join(" | "):typeof v==="object"&&v!==null?JSON.stringify(v):v??"";}

if(mode==="template"){
  const labels=["工单编号","诉求标题","诉求类型","事项内容","所属区","镇街","地址","最终承办单位","留言时间","主办单位","协办单位","办理过程","办结单位"];
  const sh=table("历史工单模板",labels,[],[20,28,14,60,14,16,42,32,20,28,28,48,28],"TemplateTable");
  sh.getRange("A3:M3").merge();sh.getRange("A3").values=[["前9列为建议采集字段，后4列为可选字段。导入器也支持其他常见字段名，无需按此模板改造已有数据。"]];sh.getRange("A3:M3").format={fill:"#FFF2CC",font:{name:font,color:"#7F6000"},wrapText:true};sh.getRange("3:3").format.rowHeight=30;
}else if(mode==="fixture"){
  const labels=["工单编号","诉求标题","诉求类型","事项内容","所属区","镇街","地址","最终承办单位","留言时间","协办单位"];
  const rows=[
    ["N-001","垃圾清理","投诉","白云区某内街垃圾堆积超过两日，请安排清理。","白云区","景泰街","白云区景泰街测试路1号","广州市白云区人民政府-景泰街","2026-09-01 10:00",null],
    ["N-002","道路问题","投诉","道路路面破损影响车辆通行，希望尽快维修处理。","越秀区","光塔街","越秀区解放路","广州市白云区人民政府-景泰街","2026-09-02 10:00",null],
    ["N-003","未知地点","咨询","市民咨询公共设施维护问题，但未提供具体发生地址。",null,null,null,"广州市白云区人民政府-景泰街","2026-09-03 10:00",null],
    ["N-004","多单位","投诉","白云区某处存在道路及绿化综合问题，要求联合办理。","白云区","景泰街","测试路2号","广州市白云区人民政府-景泰街","2026-09-04 10:00","广州市白云区水务局"],
    ["N-005","新部门","咨询","白云区居民咨询某项新设机构负责的公共服务事项。","白云区","景泰街","测试路3号","白云区测试新部门","2026-09-05 10:00",null],
    ["N-006","内容缺失","投诉","太短","白云区","景泰街","测试路4号","广州市白云区人民政府-景泰街","2026-09-06 10:00",null],
  ];
  table("正常Excel数据",labels,rows,[18,24,14,58,14,16,36,38,20,34],"FixtureTable");
}else if(mode==="review"){
  const dir=inputPath; const read=async n=>JSON.parse(await fs.readFile(path.join(dir,n),"utf8"));
  const profile=await read("raw_profile.json"), mapping=await read("field_mapping.json"), cases=await read("normalized_cases.json"), assessment=await read("assessment.json"), departments=await read("department_mapping_suggestions.json");
  const overview=wb.worksheets.add("数据源概览");overview.showGridLines=false;overview.getRange("A1:C1").merge();overview.getRange("A1").values=[["新增历史工单数据源概览"]];overview.getRange("A2:C2").merge();overview.getRange("A2").values=[[profile.source_file]];overview.getRange("A4:C16").values=[["统计项","数量/内容","说明"],["总记录数",profile.record_count,"源文件读取行数"],["字段数量",profile.fields.length,profile.fields.join("、")],["重复记录",profile.duplicate_records,"同ID或同内容"],["有工单ID",profile.records_with_case_id,"缺失时生成稳定哈希"],["内容完整",profile.complete_content_records,"事项内容不少于20字"],["有区域信息",profile.records_with_region_field,"区、镇街或地址"],["白云区明确",profile.baiyun_confirmed_records,"可进入后续严格筛选"],["有承办单位",profile.records_with_dispatch_target,"原始字段"],["承办单位名称数",profile.unique_dispatch_target_names,"去重名称"],["疑似多承办",profile.suspected_multi_handler_records,"进入审核"],["最早时间",profile.created_at_min||"无",""] ,["最晚时间",profile.created_at_max||"无",""]];overview.getRange("A1:C16").format=body;overview.getRange("A1").format.font={name:font,size:16,bold:true};overview.getRange("A2").format.font={name:font,italic:true,color:"#4B5563"};overview.getRange("A4:C4").format=header;[24,48,64].forEach((w,i)=>overview.getRangeByIndexes(0,i,16,1).format.columnWidth=w);
  table("字段映射",["标准字段","源字段","匹配方式","置信度","审核状态"],Object.entries(mapping).map(([k,v])=>[k,v.source_field||"",v.match_method,v.confidence,v.review_status]),[34,30,20,14,16],"FieldMapping");
  table("新承办单位映射",["原承办单位","建议规范单位","匹配方式","置信度","审核状态","审核意见"],departments.map(x=>[x.raw_dispatch_target,x.suggested_canonical_target,x.match_method,x.match_confidence,x.review_status,x.review_note]),[42,42,24,14,16,42],"DepartmentSuggestions");
  const caseLabels=["案例ID","源行","标题","事项内容","区","镇街","地址","原承办单位","规范承办单位","范围","范围理由","相似闯关ID","相似度","排除原因","审核状态","审核意见"];
  const caseRow=x=>[x.source_case_id,x.source_row,x.case_title,x.case_content,x.district,x.subdistrict,x.address,x.raw_dispatch_target,x.canonical_dispatch_target_name,x.baiyun_scope,x.scope_reason,x.nearest_challenge_source_id,x.challenge_content_similarity,x.exclude_reasons.join(" | "),x.review_status,x.review_note];
  const widths=[24,10,24,62,14,16,36,38,38,18,40,24,12,44,14,36];
  table("白云区probable案例",caseLabels,cases.filter(x=>x.baiyun_scope==="baiyun_probable").map(caseRow),widths,"ProbableCases");
  table("多承办复杂案例",caseLabels,cases.filter(x=>!x.has_unique_dispatch_target||x.complexity_status!=="clear").map(caseRow),widths,"ComplexCases");
  table("strict practice eligible",caseLabels,cases.filter(x=>x.strict_practice_eligible).map(caseRow),widths,"EligibleCases");
  table("排除原因",caseLabels,cases.filter(x=>!x.strict_practice_eligible&&!x.challenge_duplicate&&!x.challenge_near_duplicate).map(caseRow),widths,"ExcludedCases");
  table("与challenge重复",caseLabels,cases.filter(x=>x.challenge_duplicate||x.challenge_near_duplicate).map(caseRow),widths,"ChallengeDuplicates");
  const dist=Object.entries(cases.filter(x=>x.strict_practice_eligible).reduce((a,x)=>(a[x.canonical_dispatch_target_name]=(a[x.canonical_dispatch_target_name]||0)+1,a),{})).sort((a,b)=>b[1]-a[1]);
  table("部门分布",["规范承办单位","strict候选数"],dist,[46,18],"DepartmentDistribution");
  table("容量统计",["统计项","数量"],[["现有strict practice候选",assessment.existing_strict_practice_eligible],["本数据源新增strict候选",assessment.new_strict_practice_eligible],["跨数据源精确重复",assessment.cross_dataset_exact_duplicates],["当前总practice容量",assessment.current_total_practice_capacity],["距离500题",assessment.gap_to_500],["距离650候选",assessment.gap_to_650],["距离800候选",assessment.gap_to_800]], [34,18],"CapacityStats");
}else throw new Error("unknown mode");

await fs.mkdir(path.dirname(outputPath),{recursive:true});const out=await SpreadsheetFile.exportXlsx(wb);await out.save(outputPath);
const first=wb.worksheets.getItemAt(0),used=first.getUsedRange(true);console.log((await wb.inspect({kind:"table",range:`${first.name}!A1:${colName(used.columnCount)}${Math.min(20,used.rowCount)}`,include:"values,formulas",tableMaxRows:20,tableMaxCols:16})).ndjson);console.log((await wb.inspect({kind:"match",searchTerm:"#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",options:{useRegex:true,maxResults:100},summary:"formula errors"})).ndjson);
for(const sh of wb.worksheets.items){const range=sh.getUsedRange(true);const preview=await wb.render({sheetName:sh.name,range:`A1:${colName(range.columnCount)}${Math.min(14,range.rowCount)}`,scale:sh.name==="数据源概览"?1.1:0.55,format:"png"});await fs.writeFile(`${outputPath}.${sh.name}.png`,new Uint8Array(await preview.arrayBuffer()));}
