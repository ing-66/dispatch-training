# 历史承办单位治理（Phase 2）

本阶段只治理历史案例中出现频次最高的前50种承办单位名称，不修改原始案例，不把建议结果写入正式 `departments`，也不生成正式题库。

## 运行

```powershell
python scripts/department_governance.py `
  --source "D:\热线派单系统V2\assets\knowledge-original\C. 历史案例库\官方工单案例" `
  --asset-root "D:\热线派单系统V2\assets" `
  --output artifacts/department-governance-top50
node scripts/build_department_governance_workbook.mjs
```

输出包括全部754种名称频次、Top 50治理建议、预计新增案例明细、统计摘要，以及供人工审核的 Excel 工作簿。所有映射建议初始均为 `pending`。

## 治理边界

- 依次使用字符串归一化、明确的别名规则和保守分类；相似字符串不会自动合并。
- `baiyun` 单位优先列为新增规范部门候选；公共服务单位只在题面明确出现“白云区”地点信号时计入安全估算。
- 市级单位标记为范围待审，不计入估算；广州其他区单位原则上排除；无法判断的名称保留待审。
- 原始 Markdown 不含可靠的退单、转派、主协办或争议结论，因此不补造这些字段；预计案例仅标记 `complexity_status=needs_review`。
- 预计可出题数是部门映射批准后的上限估算，仍需逐案检查题面完整性、唯一责任和历史结果可靠性。

## 别名层

`department_aliases` 独立保存原始别名到规范部门的映射，并保留范围、类型、匹配方法、置信度和审核意见。运行时解析只接受 `approved` 且启用的别名及启用的规范部门；`pending`、`rejected` 和 `needs_review` 均不会生效。

建议审核顺序：先核定规范部门是否属于白云区训练范围，再核定别名等价关系，最后才将批准的规范部门和别名通过后续受控导入写入数据库。

## Phase 2.1 全量治理

全量容量评估使用：

```powershell
python scripts/department_governance_full.py `
  --source "D:\热线派单系统V2\assets\knowledge-original\C. 历史案例库\官方工单案例" `
  --asset-root "D:\热线派单系统V2\assets" `
  --output artifacts/department-governance-full
node scripts/build_department_governance_full_workbook.mjs `
  artifacts/department-governance-full `
  artifacts/department-governance-full/全量承办单位治理与题源容量评估.xlsx
```

该流程治理全部754种名称，并对5,143条案例分别判断承办单位范围、地点范围、内容完整性、单一承办字段和可见复杂信号。公共服务单位仅在标题或事项内容明确出现“白云区”时自动准入；市级单位即使满足地点要求也保持逐案 `pending`。广州政务、白云区政府等不能代表明确职责主体的泛化标签直接排除。

`baiyun_probable` 只表示题面出现已识别白云镇街信号但缺少明确“白云区”字样，不能自动进入严格题源池。严格 `eligible` 是审核前的保守容量估算，不表示已完成题目质量和职责依据审核。
