# dispatch-training V1 Release

## 1. 项目定位

面向“若发生此类事项应派发至哪个承办单位”的政务派单训练系统。V1 由 100 道闯关题与 450 道自由练习题组成，共 550 道正式题。

## 2. 与 hotline-advisor 的关系

本项目是独立训练应用，不依赖 hotline-advisor。两者是不同系统；本项目数据源于广州公开历史案例与白云区职责资料的治理结果，运行时与 hotline-advisor 无调用关系。

## 3. 独立运行架构

运行态只有：

- FastAPI 后端 + SQLAlchemy
- Next.js 前端
- 本地 SQLite（或可选 MySQL）
- Alembic 迁移

运行时不依赖 Qdrant / RAG / LLM；解析、职责依据和来源说明均为预生成数据。

## 4. Challenge 100 题规则

- 10 关 × 10 题
- Level 1 起解锁，60 分通关后解锁下一关
- 题目固定，同关内只 shuffle 选项
- 已冻结，禁止修改

## 5. Practice 450 题规则

- 固定题库，每轮随机 10 题
- 未做题优先；单轮内 question_id 不重复
- 全部 450 题完成后进入下一 Cycle
- Cycle 边界按“实际启用题库容量”动态计算，不依赖固定 500/450 数字

## 6. 题库来源类型

- `baiyun_original`：白云区真实历史案例
- `cross_district_transfer`：广州其他区同类案例，答案映射为白云区职责
- `citywide_same_target`：广州市级统一承办事项，白云区仍由同一市级单位承办
- `public_service_same_target`：城市级公共服务主体，白云区仍由同一主体承办

跨区/市级/公共服务题保留原始 `source_case_id`、来源区与原承办单位，不改写原文区名。

## 7. 数据库启动方式

默认 SQLite：

```powershell
python -m alembic upgrade head
```

MySQL 模式：

```powershell
Copy-Item .env.example .env
docker compose up -d training-db
python -m alembic upgrade head
```

## 8. 后端启动方式

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8100
```

## 9. 前端启动方式

```powershell
Set-Location frontend
npm install
npm run dev
```

访问 `http://127.0.0.1:3100/training`。

## 10. 测试命令

```powershell
pytest -q
Set-Location frontend
npm run build
```

V1 冻结时结果为：51 passed，前端生产构建通过。

## 11. 正式题库哈希

- Challenge V1 SHA-256：`82023DF9C7672FA23FC579EB2A64F6BC59F9EC03266671F1D07DFBBC3833BB2D`
- Practice V1 SHA-256：`89D46AB36C71BFC64FA70DA4816D549C025F64307D1D75F659016BE568CA7731`

校验：

```powershell
Get-FileHash artifacts/challenge-v1/challenge_questions_v1_approved.json
Get-FileHash artifacts/practice-v1/practice_questions_v1_approved.json
```

## 12. Freeze manifest 路径

- Challenge：`artifacts/practice-source-assessment/challenge_v1_freeze_manifest.json`
- Practice：`artifacts/practice-v1/practice_v1_freeze_manifest.json`

两个 manifest 为本地正式资产，不包含原始工单正文。

## 13. 数据库备份说明

正式导入前自动生成备份，例如：

- `dispatch_training.db.pre-v1-*.bak`
- `dispatch_training.db.pre-practice-v1-*.bak`

备份文件不纳入 Git。

## 14. 新数据接入命令

```powershell
python scripts/practice_source_ingest.py "D:\新数据\白云区历史工单.xlsx" --dataset-id baiyun-2026
```

## 15. 如何未来扩充 practice 题库

1. 新数据接入 → `practice_source_ingest.py`
2. 跨区迁移评估 → `cross_district_transfer_assessment.py`
3. 市级/公共服务同体评估 → `practice_expansion_phase51.py`
4. 制题与选择 → `build_practice_v1.py`
5. dry-run / 正式导入 / 冻结 → `import_practice_v1.py`、`freeze_practice_v1.py`

Practice Engine 动态读取启用题数，450/453/500 均无需改容量代码。

## 16. V1 明确不包含

- 排行榜、金币、每日任务、成就、PK、收藏、错题本 UI、AI 动态出题、难度选择
- 运行时 RAG/LLM 解释
- hotline-advisor 联动
- 500 道练习题的承诺（V1 正式基线为 450）

## 敏感数据与版本控制

正式题库 JSON/CSV/audit、中间治理产物和数据库备份包含原始工单内容（含地址与个人信息），不纳入 Git。`artifacts/` 已整体加入 `.gitignore`。正式库内容通过本地文件与上述哈希恢复/核对，不在仓库中公开原始案例。
