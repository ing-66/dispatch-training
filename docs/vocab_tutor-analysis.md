# vocab_tutor 机制分析与适配

分析基于 `deanliao/vocab_tutor` 的 `levels.js`、`store.js`、`wordbank.js`、`ui.js`、`app.js`。

1. 关卡机制：5级难度，练习达到至少12题且正确率80%后开放挑战；挑战8题，80%升级。本项目只复用“状态门控—挑战—晋级”的流程，改为固定10关、每关固定10题、60分直接通关。
2. 状态管理：参考项目由 `store.js` 统一管理并持久化到 localStorage。本项目保留集中业务规则，但状态全部进入独立数据库，前端不作为事实来源。
3. 挑战生命周期：`app.js` 抽题、逐题调用 UI、汇总正确数并调用 `promote()`。本项目由后端创建不可篡改的 attempt 和 attempt_questions，逐题提交，全部完成后结算。
4. 解锁：参考项目仅维护 current/unlocked 的最高值。本项目保存 `highest_unlocked_level`，并增加每关 `is_passed/best/latest/attempt_count`。
5. 重复挑战：参考项目已解锁等级保持开放。本项目进一步明确永久通关；低分重试只更新 latest 和次数，不撤销 passed 或后续解锁。
6. Practice：参考项目按当前等级配合 Leitner SRS 选词。本项目不复用 SRS，改为独立500题池、未做优先和 cycle 轮换。
7. 随机：参考项目采用 Fisher–Yates 和 sample；题目、拼写干扰项都会随机。本项目闯关题绝不随机，只随机四个固定部门选项；练习题由后端在未做集合中随机且单次不重复。
8. 可复用思想：常量化门槛、纯业务规则、模型/视图/控制解耦、一次答题状态防重复提交、结果汇总。
9. 不适用部分：localStorage、纯静态单机架构、动态拼写干扰项、按练习正确率开放挑战、每日训练与积分、SRS、定位测试、儿童化 UI。
10. 当前适配：FastAPI 承担权威状态和判题，MySQL 保存训练域数据；Next.js 只负责流程展示；题库通过独立导入 API/脚本进入，不运行时调用热线顾问、Qdrant 或 LLM。
