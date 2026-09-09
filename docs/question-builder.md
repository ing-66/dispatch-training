# 正式题库生产流水线

流水线只从指定历史案例目录读取数据，不直接写训练数据库：

`原始 Markdown → 字段标准化 → 可出题性过滤 → AI 加工候选 → Excel/CSV 人工审核 → approved JSON → 导入 API`

## 数据边界

- 历史案例：5个按诉求类型分类的 Markdown 文件，每条案例由二级标题和 `【字段】` 块组成。
- 原始数据没有工单编号，`source_case_id` 使用来源文件、标题和原文内容的 SHA-256 摘要稳定生成。
- 部门主数据只取原热线项目 `knowledge-source/01_机构职责` 和 `02_权责清单` 中可证明的白云区单位。
- 历史案例无法唯一映射到部门主数据时直接排除，不根据案例字符串创建新部门。
- 当前历史文件只提供“实际承办单位”，没有退单轨迹、争议结论和具体职责条款。因此所有候选默认 `pending`，依据默认 `needs_review`。

## 测试批次

```powershell
python scripts/question_builder.py `
  --source "D:\热线派单系统V2\assets\knowledge-original\C. 历史案例库\官方工单案例" `
  --asset-root "D:\热线派单系统V2\assets" `
  --output artifacts/question-builder-test `
  --sample-size 25
```

审核工作簿包含“生产概览、待审核题目、排除案例、部门主数据”四张表。审核人员需逐题检查题干、唯一答案、干扰项、五维评分与理由、解析和依据，并设置：

- `review_status`：`pending / approved / rejected / needs_revision`
- `reference_basis_status`：`needs_review / verified`

将审核后的“待审核题目”工作表另存为 UTF-8 CSV，再生成导入载荷：

```powershell
python scripts/prepare_question_import.py `
  --reviewed-csv artifacts/question-builder-test/candidates-reviewed.csv `
  --output artifacts/question-builder-test/import-approved.json
```

脚本只导出 `approved` 且依据已核验的题目，并校验五维总分和闯关/练习去重。导入接口还会再次检查审核状态、部门代码、部门名称、部门启用状态及四个选项唯一性。

## 批量生产前提

初次试跑在现有26个部门主数据下只有36条合格案例。Phase 2.1完成全量名称治理和白云区地点约束后，严格题源为318条，仍不足以生产600题；不得放宽唯一答案、白云区范围或内容质量标准来补足数量。

## 正式闯关候选阶段

Phase 2.1治理后，从318条严格题源生成180道待审核闯关候选：

```powershell
python scripts/challenge_candidate_builder.py `
  --eligible artifacts/department-governance-full/case_assessments.json `
  --output artifacts/challenge-candidates `
  --count 180 `
  --per-target-cap 7
```

脚本按规范承办单位轮转选题，限制单单位最多7题，并在同单位内排除高度近似文本。五维评分和建议关卡用于排序与人工分层，不替代业务审核；建议关卡按候选池相对难度、承办单位类型和干扰项难度形成，不按每10分机械划分。

全部候选保持 `review_status=pending` 和 `reference_basis_status=needs_review`。历史实际承办记录只能证明历史处理结果，不能替代职责条款。人工应从每个建议Level的18道候选中选择10道，并在核实唯一责任、职责依据、题面质量和整体覆盖后批准最终100题。

## Phase 3.1 终审准备与梯度校准

`challenge_finalization.py` 只生成终审中间数据，不修改题库数据库：

```powershell
python scripts/challenge_finalization.py `
  --candidates artifacts/challenge-candidates/candidates.json `
  --case-assessments artifacts/department-governance-full/case_assessments.json `
  --asset-root "D:\热线派单系统V2\assets" `
  --output artifacts/challenge-finalization
```

脚本统一正式承办单位名称和别名，以机构职责、镇街职责、权责清单原文建立可追溯依据，并按题干理解、职责边界和干扰项相关度重新建议关卡。`verified` 表示检索到与事项关键词直接相关的职责原文；`needs_review` 表示找到承办单位资料但缺少直接段落；`insufficient` 表示当前资料不足；`conflict` 仅用于明确冲突。所有题继续保持 `pending`，推荐池只标记 `recommended`，不能作为正式批准结果。

## Phase 3.2 正式100题

主审核从128道推荐题剔除指定28题后锁定100题。`finalize_challenge_v1.py` 只对锁定题执行职责依据硬门禁，失败时按同关被剔除题、同关总候选的顺序最小替补。正式产物位于 `artifacts/challenge-v1/`，每题保存职责依据标题、来源、原文摘录、文件定位和核验理由。

正式导入先运行隔离库 dry run，再执行数据库迁移和安全替换：旧闯关演示题仅禁用，不删除；练习题、用户、答题记录和关卡记录不受影响。

```powershell
python scripts/import_challenge_v1.py --approved artifacts/challenge-v1/challenge_questions_v1_approved.json --dry-run --disable-old
python -m alembic upgrade head
python scripts/import_challenge_v1.py --approved artifacts/challenge-v1/challenge_questions_v1_approved.json --disable-old
python scripts/verify_formal_challenge_v1.py
```

## Phase 4.1 新历史工单接入

新数据导入器支持 `.xlsx`、`.xls`、`.csv` 和 `.json`，按表头同义词提出字段映射，不要求源文件预先改列名。原文件只读，所有结果写入独立数据集目录：

```powershell
python scripts/practice_source_ingest.py "D:\incoming\白云区历史工单.xlsx" `
  --dataset-id baiyun-2026-09 `
  --output-root artifacts/practice-source-ingest
```

输出包括数据画像、字段映射、标准化案例、新部门映射建议、排除案例、严格候选、容量评估和十张表的审核工作簿。严格候选只接受白云区明确、内容完整、唯一承办、已批准规范单位、无闯关重复且无明显复杂信号的案例。文本近重复会写明相似案例和相似度并进入审核，不会静默删除。`challenge_source_ids.json` 始终作为正式闯关题永久去重集合。

## Phase 5 其他区案例跨区迁移可用性评估

对 `department_scope=other_district` 的2440条其他区历史案例只做候选筛选、原区承办单位归一化、原区→白云承办单位映射建议、逐案迁移门禁、白云职责依据机器核验与容量统计，不生成正式题，不写practice库。

```powershell
python scripts/cross_district_transfer_assessment.py `
  --output-root artifacts/cross-district-transfer-assessment
node scripts/build_cross_district_transfer_workbook.mjs `
  artifacts/cross-district-transfer-assessment `
  artifacts/cross-district-transfer-assessment/cross_district_transfer_assessment.xlsx
```

映射建议区分 `direct_equivalent / functional_equivalent / conditional_equivalent / not_transferable / unknown`。镇街、区政府泛化、属地特有机构和无法唯一识别单位一律 `not_transferable`；规划和自然资源分局、生态环境分局、公安分局、税务分局和公共服务企业默认 `conditional_equivalent` 且 `needs_review`。职责依据硬门禁只接受已批准白云规范单位且机器命中 `白云区政府部门职责明细` 或权责清单原文的 `verified` 记录；命中的摘录和定位必须进入人工审核工作簿复核。跨区候选原始区名、原承办单位和原文均不替换，只生成 `transfer_question_context` 作为后续出题说明。

## Phase 5.1 市级/公共服务同体承办 + 白云稳定职能扩容评估

在 Phase 5 的 218+136 候选基础上继续评估三个不重复的池：市级统一承办主体（`same_citywide_target`）、公共服务同体主体（`same_public_service_target`）、以及 Phase 5 中因白云 pending 规范单位未能进入 strict 的潜在跨区候选。规则明确区分“市级统一事项仍由市级承办”和“某市局历史案例因此白云也一定派该市局”，后者一律不允许；公安、住建、教育、人社等存在区级主责单位的职能不会仅凭历史名称自动放行。公共服务同体候选除引用《广州市供用电条例》《广州市城市轨道交通管理条例》《广州市井盖设施管理办法》等权威原文外，还校验该主体是否已有白云区同类受理记录；公交集团因全市存在多家线路经营主体，只保留 `needs_review`，不计入 strict。允许对卫健、文旅体、政务数据等提出 `verified_candidate` 的白云规范单位，但仍不写入正式 `departments` 主表。

```powershell
python scripts/practice_expansion_phase51.py `
  --output-root artifacts/practice-expansion-phase51
node scripts/build_practice_expansion_phase51_workbook.mjs `
  artifacts/practice-expansion-phase51 `
  artifacts/practice-expansion-phase51/practice_expansion_phase51.xlsx
```

产物包含 `summary.json`、三个候选池评估 JSON、`new_strict_practice_candidates.json`、`combined_practice_candidates.json`、部门/主题/近重复簇分布和 14 表审核工作簿。`case_origin` 保留 `baiyun_original / cross_district_transfer / citywide_same_target / public_service_same_target` 四种来源能力，原始 `case_content` 一律不改写区名。

## Phase 6 450道正式自由练习题生产与入库

V1基线调整为自由练习450题。制题只从 Phase 5.1 的465道 strict 候选中选择，机器主审核 + reserve替换，不允许用 needs_review 补数。制题器为每个候选生成 core_issue、responsibility_reasoning、固定 explanation、transfer_reasoning 与 verified 的可追溯职责依据，并按业务相关性为每题选择3个真实干扰承办单位（答案只存 canonical target，由运行时随机 A/B/C/D）。

```powershell
python scripts/build_practice_v1.py
python scripts/import_practice_v1.py --approved artifacts/practice-v1/practice_questions_v1_approved.json --dry-run --disable-old
python -m alembic upgrade head
python scripts/import_practice_v1.py --approved artifacts/practice-v1/practice_questions_v1_approved.json --disable-old
python scripts/freeze_practice_v1.py
```

旧演示 practice 题只安全禁用不删除；正式 practice 450题与 challenge 100题保存在同一 questions 表但 `source_case_id` 全不重叠，`question_type` 隔离。Question 增加 `case_origin` 字段，前端仅增加来源低强调文字展示，不改 Practice 核心算法。题库容量始终动态读取启用题数，450/453/500 均可运行，不依赖固定数字。
