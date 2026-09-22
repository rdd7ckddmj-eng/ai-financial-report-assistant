# 研究案件 v1 数据契约

## 目标

研究案件不是新增的孤立工具，而是所有研究模块共同更新的一份工作底稿。用户
输入一家公司后，系统围绕同一案件持续回答五类问题、保存证据出处、暴露矛盾和
未知，并记录下一步核验动作。纯数据契约、Streamlit 工作台、浏览器存储组件和
已接入的 CasePatch 生产者复用同一结构；页面不得再维护另一份“案件真相”。

浏览器端已使用独立键 `wfz.research_cases.v1`。旧的自选股、最近研究和游戏
存档不属于本契约，也不得被覆盖。

## Store

Store 是 JSON 可序列化对象：

- `schema_version`: 固定为 `"1.0"`；
- `store_revision`: 每个成功的新命令增加 1；
- `active_case_id`: 当前案件编号或 `null`；
- `cases`: 以 `case_id` 为键的案件对象，最多 5 个，不自动淘汰；
- `applied_command_ids`: 最近 50 个已执行命令编号组成的重试窗口。

单个案件序列化后的 UTF-8 JSON 最多 150,000 字节，整个 Store 最多 750,000
字节。Store 会在 Streamlit 组件和浏览器之间传输，因此总量限制与条数限制必须
同时满足；不能因为每个 artifact 单独小于 20 KB，就允许累计成巨大的通信包。

Store reducer 支持 `create`、`activate`、`archive`、`delete_archived`、
`roll_forward` 和 `apply_patch`。所有命令必须提供 `command_id`、
`base_store_revision` 和 `emitted_at`。已执行命令重放时原样返回；新命令必须命中
当前 Store revision，否则拒绝。命令窗口满后保留最近 50 项，使正常研究不会被
永久锁死；窗口外的原命令仍携带旧 revision，因此会作为过期命令拒绝，不会重复
执行业务动作。案件的 patch id 使用同样的最近 50 项策略。

## Case

每个案件包含：

- `schema_version`、`case_id` 和递增的 `revision`；
- 已核验公司身份 `company`，至少包含 6 位 `code`、`canonical_code`、
  `name` 和 `exchange`；
- `scope`：`current` 或 `historical`、`as_of_date`、
  `effective_market_date`；
- `lifecycle`：`active` 或 `archived`；
- `readiness`：`draft`、`in_progress`、`needs_human_review` 或
  `ready_to_export`；
- `created_at`、`updated_at` 和严格结构化的 `case_brief`；
- 专题研究泳道、模块产物、证据引用、研究假设、跟踪点、审计记录；
- 已执行 `patch_id` 和已执行 `migration_id`。

`current` 案件只能将 `effective_market_date` 向后推进；`historical` 案件创建后
不允许改变截止范围，防止前视偏差。案件一经 `archived` 就成为只读对象，不得
再次 activate、应用 Patch 或 roll forward；后续研究应创建新案件。

## 首页五个答案：case_brief

首页不得从多个工具的临时状态拼接结论。它只读取一份 `case_brief`，其中恰好
包含：

1. `primary_question`：当前最值得核验的问题；
2. `evidence`：已有证据摘要，以及实际存在的 `artifact_ids` 和
   `evidence_ids`；
3. `contradictions`：矛盾列表，每项都必须引用至少一个实际存在的 artifact
   或 evidence；
4. `unknowns`：尚未解决的未知列表；
5. `next_action`：下一步应进入的白名单模块、具体动作和原因。

空案件仍保留上述完整结构，但文本和引用为空，`next_action.module` 为 `null`。
Patch 通过 `case_brief_update` 原子替换一个或多个完整答案。引用可以指向同一
Patch 新增的 artifact/evidence；应用完成后如果仍有任何悬空引用，整包拒绝且
案件不变。

`contradictions == []` 只表示当前尚未登记一条带真实引用的矛盾，页面和导出不得
把它改写成“没有矛盾”“证据一致”或其他确定性结论。

## 专题研究泳道

`questions` 不再冒充首页五个答案，而是保留为可选的专题研究泳道。它只能包含
下列键，新案件全部从 `not_started` 开始：

1. `recent_events`：近期发生了什么；
2. `market_change`：市场表现发生了什么变化；
3. `financial_quality`：财务质量最值得核验什么；
4. `point_in_time`：在指定时点当时能够知道什么；
5. `research_judgement`：当前研究判断及其边界是什么。

每项状态只能是 `not_started`、`in_progress`、`answered`、`blocked` 或
`needs_human_review`。每项另有 `artifact_ids` 和 `evidence_ids`，且不得存在
悬空引用。泳道进度不会替代或自动改写 `case_brief`。

## 模块产物与证据

允许写入案件的模块只有：

- `company_research`
- `comprehensive_research`
- `market_activity`
- `financial_snapshot`
- `annual_report`
- `financial_trend`
- `historical_lens`
- `evidence_delta`
- `research_thesis`

单个 artifact 的 `payload` 必须是标准 JSON，UTF-8 编码不超过 20 KB。禁止
bytes、NaN、Infinity 和任意 Python 对象。每案最多 25 个 artifact、50 条
evidence、10 条 hypothesis、100 条 audit、50 个 patch id；所有容量均采用
明确的有界策略：artifact、evidence、hypothesis、audit、单案 JSON 和 Store
JSON 满则拒绝且不自动淘汰；patch id 是最近 50 项重试窗口，不会让案件在第 51
次正常更新时永久锁死。

Evidence 只保存可追溯引用，不保存整份 PDF。每条证据必须显式声明
`source_tier`：

- `official_disclosure`：巨潮资讯、上交所、深交所和北交所白名单；
- `official_company`：必须命中案件公司身份中登记的 `official_domains`；
- `public_market_data`：东方财富、新浪财经、腾讯行情及中证/国证指数等公开市场
  数据白名单；
- `user_provided`：允许其他有效 `http(s)` 来源，但不会被冒充为官方来源。

人工复核状态只允许 `pending`、`confirmed`、`corrected`、`rejected` 和
`not_required`。证据还可保存 `page_start/page_end`、`excerpt`、
`original_value`、`unit` 和 `basis`，所有文本和页码均有边界检查。无论来源层级
如何，历史案件中的 `published_date` 都不得晚于 `as_of_date`。

## CasePatch 原子规则

Patch 信封必须包含：`patch_id`、`case_id`、`base_revision`、
`canonical_code`、`mode`、`as_of_date`、`emitted_at` 和 `source_module`。
内容可以包含一个 artifact、若干 evidence、`case_brief_update`、专题泳道更新、
假设增删、tracking 更新和审计消息。

应用前先在副本上完成全部结构、身份、截止日、容量和 revision 检查。任何检查
失败，原案件完全不变。已应用 patch 重放时原样返回。新 patch revision 冲突则
拒绝；成功后案件 revision 只增加 1。

## 页面与已接入的 CasePatch 生产者

研究案件工作台只从活动案件的 `case_brief` 读取首页五问，并从 `questions` 读取
五条专题泳道。公司切换先执行显式 activate/create 命令，所有写入都保留命令 ID、
base store revision 和 base case revision；浏览器存储暂不可用时保留当前会话数据
并禁用新的持久化写入，不用空对象覆盖有效案件。

同公司当前案件在接收新证据前按 UTC 日历日执行 `roll_forward`；历史案件永不
前滚。这样底稿的有效日期不会停在旧日期却混入后来公告，也避免英国夏令时本地
午夜与 UTC `emitted_at` 跨日时把合法当天资料误判为未来数据。

当前接入规则：

- 一键综合研究只有在用户明确运行后才生成紧凑 CasePatch；被动浏览、旧简报和
  DataFrame 不写入案件；综合模块生成的泳道摘要属于来源派生记录，保留链接与
  日期但使用 `not_required`，不能因为上游状态为 verified 就升级为已确认事实；
- Historical Lens 只有在用户明确锁定时点后才生成历史 CasePatch；历史案件的
  `as_of_date` 与 `effective_market_date` 不可向未来修改，晚于截止日的公告和后来
  收益不得进入当时证据；它不修改公告增量专属的
  `tracking.evidence_checked_at`，同一内容重试必须使用内容寻址 ID 并保持幂等；
- 全市场按需财务快照的五项核心数字必须先完成逐项人工决定，未复核候选不能被
  提升为已确认事实；
- 年报证据问答只把 Verifier 已核验的官方原文短摘录、来源 URL 和 PDF 页码写成
  evidence；Agent 生成的结论只能保存在 artifact 的 `analysis_output`，不能冒充
  来源事实；
- 公告增量只为同公司当前案件保存通过官方披露域名与日期复核的紧凑引用，包括
  标题、发布日期、类别、关注程度和“新增/同日待复核”状态；关注程度只决定
  阅读优先级，不表示利好、利空或价格方向；
- 上述专项写入均不得保存 PDF、本地全文、HTTP 响应、DataFrame 或其他大对象。
  尚未接入的专项视图仍须复用同一 CasePatch 契约，不能另建平行底稿格式。

## 年报五项人工复核

营业收入、净利润、经营现金流、总资产和总负债分别保留：自动提取标准化值、
原报表数值、原单位、会计口径、比较口径、报表名称、PDF 页码和有界原文摘录。
用户对每项只能执行：

- `confirmed`：确认原值；缺失值不能直接确认；
- `corrected`：保留原值，同时填写修改值、理由和决定时间；
- `rejected`：保留被驳回候选与理由，不产生替代值；
- `pending`：尚未作出人工决定。

五项仍有任何 `pending` 时禁止导出该份单期人工复核底稿，也不能把该快照写入
案件 evidence/artifact 或用它推动 readiness。五项全部有决定后，单期复核底稿
仍只是一个可写回案件的财务 artifact。研究案件可以不包含年报快照；是否进入
`ready_to_export` 始终只按下面的规范化 readiness 规则派生，不能另设“必须完成
年报五项复核”的全局前置条件。

## Readiness 派生规则

`readiness` 不是由 AI 自报，而是纯函数重新计算：

1. 没有 artifact 时为 `draft`；
2. 任一 artifact/evidence/hypothesis 的 review status 为 `pending`，或任一
   专题泳道为 `needs_human_review` 时为
   `needs_human_review`；
3. `case_brief.primary_question`、证据摘要及至少一个实际存在的 `evidence_id`、
   下一步模块/动作/原因都已填写，并且五条专题研究泳道均已离开
   `not_started` 时，为
   `ready_to_export`；若泳道为 `blocked`，还必须写明摘要和下一步；矛盾和未知
   可以是空列表，仅表示当前尚未登记对应项目；只有 artifact 或程序摘要不能
   解锁正式导出；五条泳道不能全部为 `blocked`，至少一条必须达到
   `answered` 或 `in_progress`；
4. 其他情况为 `in_progress`。

## 完整研究工作底稿导出

`src/research_case_workpaper.py` 是规范案件的只读导出层，不维护第二份可变状态。
`build_research_case_workpaper()` 只接受经过 `validate_research_case()` 且派生状态
为 `ready_to_export` 的案件；未完成案件没有静默“正式草稿”旁路。

正式 JSON 保留完整 ResearchCase，因此包括公司与时点范围、首页五问、五条专题
泳道、来源 URL、发布日期、可用 PDF 页码、原值、单位、口径、复核状态、紧凑
artifact payload、hypothesis、tracking、矛盾、未知和审计日志。额外索引明确区分：

- 已确认或已更正来源记录形成的事实引用；
- 仍属于推断的研究假设；
- 不自动等于事实的分析产物；
- 未知、矛盾及未被提升为事实的其他来源记录。

导出同时保留 Responsible AI controls 和规范案件 SHA-256 指纹。JSON 与安全 HTML
输出均不得超过 500 KB，不得包含 PDF、图片或其他二进制本体；HTML 中所有动态
内容必须转义。指纹用于发现导出后篡改，不宣称数字签名、第三方认证或投资建议。

## Legacy v3 迁移

迁移只读取旧 `version == 3` 状态中与目标 `canonical_code` 匹配的：

- evidence checkpoint，写入 `tracking.evidence_checked_at`；
- research theses，写入 hypotheses。

`recent` 和 `watchlist` 不创建案件、不迁移为证据。迁移编号是目标公司与经过
规范化的迁移内容的 SHA-256；相同内容重复迁移必须幂等。损坏或非 v3 数据返回
warning 并创建一个空案件，不猜测或修复旧数据。

## 人工判断边界

本契约只保存事实、引用、状态和人工研究过程。它不生成买卖建议，不把 AI
文本当成已核验证据，也不允许模块绕过人工复核标记。页面、导出和以后可能增加的
服务器持久化必须继续复用本契约，而不是各自维护另一份“案件真相”。
