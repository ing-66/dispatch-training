# 12345 派单训练系统（dispatch-training V1）

独立运行的派单业务训练应用。V1 正式题库为 100 道闯关题 + 450 道自由练习题，运行时只依赖本地训练数据库，不依赖 hotline-advisor、Qdrant、RAG 或 LLM；判题、解析与职责依据全部预生成并入库。

## V1 基线

- Challenge V1：100 题，10 关 × 10 题，已冻结。
- Practice V1：450 题，固定题库，每轮随机 10 题、未做题优先、全部完成后进入下一 Cycle，已冻结。
- 来源类型：`baiyun_original` / `cross_district_transfer` / `citywide_same_target` / `public_service_same_target`。
- 正式题库哈希与发布说明见 `docs/V1_RELEASE.md` 和本地 `artifacts/practice-v1/practice_v1_freeze_manifest.json`。

## 独立运行架构

运行时仅包含：

- 后端：FastAPI + SQLAlchemy + 本地 SQLite（或 MySQL），`backend/`
- 前端：Next.js，`frontend/`
- 数据库迁移：Alembic，`migrations/`

正式运行不调用任何知识库生成解释。治理/制题阶段使用的外部广州公开案例与白云职责资料只存在于本机，不进入运行时依赖。

## 本地启动

```powershell
Copy-Item .env.example .env
docker compose up -d training-db          # 仅 MySQL 模式需要；默认 SQLite 可跳过
python -m pip install -e ".[dev]"
python -m alembic upgrade head
python -m uvicorn backend.main:app --reload --port 8100
```

另开终端：

```powershell
Set-Location frontend
npm install
npm run dev
```

访问 `http://127.0.0.1:3100/training`。

## 测试与构建

```powershell
pytest -q
python scripts/verify_detachment.py
python scripts/verify_formal_challenge_v1.py
Set-Location frontend
npm run build
```

V1 Release 回归：51 项测试通过；前端生产构建通过；独立 API 运行验证通过。

## 正式题库数据与敏感信息

正式题库 JSON/CSV/audit 等产物含原始广州历史工单正文（含地址与个人信息），**不纳入 Git**，仅保存在本机：

- `artifacts/challenge-v1/`
- `artifacts/practice-v1/`
- `artifacts/practice-expansion-phase51/`
- `artifacts/cross-district-transfer-assessment/`

上述目录已加入 `.gitignore`。哈希、来源统计与冻结信息记录于 `docs/V1_RELEASE.md` 和本地 `practice_v1_freeze_manifest.json`；本地数据库与备份同样不提交。

## 正式题库导入

```powershell
python scripts/import_challenge_v1.py --approved artifacts/challenge-v1/challenge_questions_v1_approved.json --dry-run --disable-old
python -m alembic upgrade head
python scripts/import_challenge_v1.py --approved artifacts/challenge-v1/challenge_questions_v1_approved.json --disable-old
python scripts/verify_formal_challenge_v1.py

python scripts/build_practice_v1.py
python scripts/import_practice_v1.py --approved artifacts/practice-v1/practice_questions_v1_approved.json --dry-run --disable-old
python scripts/import_practice_v1.py --approved artifacts/practice-v1/practice_questions_v1_approved.json --disable-old
python scripts/freeze_practice_v1.py
```

导入脚本只新增/更新 approved 题并安全禁用旧演示题，不删除历史答题记录。正式数据库导入前自动创建 `.pre-practice-v1-*.bak` 备份。

## 新数据接入与未来扩容

新白云区历史工单先走标准接入流水线：

```powershell
python scripts/practice_source_ingest.py "D:\新数据\白云区历史工单.xlsx" --dataset-id baiyun-2026
```

再按 Phase 5/5.1/6 流水线治理、筛选、映射、制题、dry-run 与正式导入。Practice Engine 动态读取启用题数，题库从 450 扩到 453/500/更多时无需修改容量代码。

详细过程见 `docs/question-builder.md`、`docs/department-governance.md` 与 `docs/V1_RELEASE.md`。
