# V1 实施与边界

## 独立边界

- 独立仓库、独立进程、独立端口（前端3100，API 8100，MySQL 3307）。
- 训练库只保存来源字符串 `source_case_id`，无热线业务表外键。
- 部门为训练系统快照；解析和依据预生成。
- 身份适配仅把外部身份映射到训练用户，业务表只认训练 `user_id`。

## 核心表

`users`、`departments`、`questions`、`question_options`、`user_progress`、`level_records`、`attempts`、`attempt_questions`、`answers`、`practice_question_progress`。

## 实施阶段

已完成机制分析、独立骨架、数据模型、Quiz/Level/Practice Engine、身份边界、基础UI、测试题种子和导入API。正式600题属于内容生产阶段，必须经过筛选、生成和人工复核后导入，不能以演示题冒充。

## 现有热线项目最小修改

只在 `frontend/app/assistant.tsx` 增加由 `NEXT_PUBLIC_TRAINING_URL` 控制的普通外链。未配置时不展示；训练服务停机不会影响热线业务请求。

## 风险

- 正式题库尚需业务人员复核，尤其是唯一承办、真实依据和高阶干扰项。
- 外部身份生产接入需要部署层验证签名/SSO，当前仅提供解耦模型和适配接口。
- 大规模并发前需要在目标MySQL上补充压测及事务并发验证。
