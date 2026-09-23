# Current task board

## 2026-09-21 · A股公开财务覆盖（本地实现）
- [x] 宁波银行2025真实样本检查，修复空白日期/非合计收入行导致银行漏识别；仍为不支持版式，保留银行比例停算策略，862项测试通过。
- [ ] 宁波银行式现金流出正数模板、附注五表头及换行归母字段；不得直接复用负数流出计算。
- [x] 平安银行2024/2025跨年复用与重叠期间五项对照；明确现金流标签别名，保留两期符号检查，859项测试通过。
- [x] 平安银行2025真实浏览器上传至待人工复核验收；修复首次提交重绘与银行比例显示，错误年度清除旧结果/恢复正确年度验证，857项测试通过。
- [x] 平安银行2025新增集团列/附注归母利润模板；归母利润来源独立指向第220页，两期三表与附注关系检查通过，855项测试通过。
- [x] 平安银行2025年跨公司真实样本检查；跳过报表目录，缺少模板支持的归母利润行时明确说明并保持金额为空，839项测试通过。
- [x] 银行报表标题空格/换行边界加固；缺失合并行不得借用银行自身报表，837项测试通过。
- [x] 招商银行2025年真实PDF边界检查；修复分组标题跨科目借值，814项测试通过。
- [x] 新增银行双年度带符号百万元模板；招商银行2025年五项金额、指定三表勾稽和公开对照通过，保留待人审状态。
- [x] 招商银行2024/2025年真实报告跨年复用；新增表头单位与年度列顺序校验，832项测试通过。
- [ ] 更多银行模板与银行专用监管指标核验；当前招商银行和平安银行各2024/2025真实样本通过，不能推定银行全覆盖。
- [x] 统一公开数据、候选快照、人工复核底稿和案件写回的正分母比例规则；亏损时不展示现金利润比，完整811项测试通过。
- [x] 年报候选快照对零/负基期不展示百分比变化，保留两期金额与原因说明；页面和HTML导出同步，完整804项测试通过。
- [x] 两源对照保存/恢复、公开候选读回；修复浏览器写入成功但未回执的问题。
- [x] 官方PDF手工输入候选快照，校验公司/年度/正文、来源元数据与资源上限。
- [x] 覆盖抽查命令与18家真实接口样本；Python 3.12/3.14分别794项测试、5项JS存储测试通过。
- [x] 泸州老窖2024年真实官方PDF的手工输入函数、三表提取与同年公开金额对照通过；修复跨页摘录和负债小计误匹配。
- [x] 格力2025年真实PDF浏览器上传、字段提交、生成候选、错误年度拒绝/清除旧快照、恢复正确年度；正式底稿仍受人审门槛约束。
- [ ] 更多行业真实报告模板、生产下载环境与线上表现；默认urllib下载在本机仍有证书错误。
- [x] 按代码接入沪深北公司最多六个完整年度公开财务；校验公司、期间、币种与版本。
- [x] 在趋势、异常方向、共同年度比较与综合研究中使用候选数据，保留缺失字段。
- [x] 导出HTML/JSON/比较CSV，综合研究导出保留公开源及取数时间。
- [x] 写入同公司当前研究案件的分析产物，不新增已确认事实，不进入历史时点案件。
- [x] 增加数据、页面交互和案件写回测试，抽查真实公开接口。
- [ ] 扩展官方年报逐页核验的公司、年度和现金流附注桥；目前仍为原有案例范围。
- [ ] 对金融控股、行业特殊口径、上市不足六年等情形继续积累官方样本。
- [ ] 线上版本核验与部署：本次没有执行，不能把本地完成视为已上线。

- [x] 连接公开财务与官方年报快照，提供同公司同年五项金额对照及可下载复核清单；不自动确认数字。

## Now
- [x] Reduce the public sidebar to two entries: 《消失的现金》 and 研究案件;
      keep every specialist research view as a child of the same case workflow.
- [x] Keep prologue and scenes 01–09 inside one fixed game screen while
      preserving sequential unlocks and browser-local completion records.
- [x] Reorganise the product home page around two connected primary modules:
      《消失的现金》 and 研究案件.
- [x] Implement the complete nine-scene learning loop, including dual-clock
      practice, evidence investigation, defence and Historical Lens transfer.
- [x] Preserve all specialist research views under 研究案件 and reorganise the
      sidebar labels without removing functionality.
- [x] Verify desktop and mobile layouts, both module entry points, the
      collapsible sidebar recovery control, and browser-console health.
- [x] Build the first playable slice of 《消失的现金》 with player naming,
      beginner profit-versus-cash teaching, and a changing guided calculation.
- [x] Replace the practice sheet after every wrong answer without deducting a
      life.
- [x] Build the first evidence-reading node with six changing documents, four
      required evidence links, and two plausible distractions.
- [x] Add a three-round formal defence for conclusion, evidence boundary, and
      next verification action; share three lives across the rounds, replace
      the case after each error, and return failed players to a new evidence
      file without deleting their identity or learned progress.
- [x] Unlock the Historical Lens mission only after all three defence rounds,
      rather than immediately after the guided evidence search.
- [x] Replace the Historical Lens date picker with a form-backed daily time
      rail that avoids repeated public-data requests while dragging.
- [x] Add exactly one cross-module open investigation that asks the player to
      find an official evidence publication boundary inside Historical Lens.
- [x] Derive the mission answer from the verified flagship event catalogue and
      distinguish publication time from the effective market trading date.
- [x] Require a second migration judgement that separates evidence publication,
      the effective K-line date, the next trading session, and causality before
      the first case is marked complete; reshuffle wrong answers without using
      the three formal-defence lives.
- [x] Add the horizontal honour archive and optional vertical social poster
      only after the first case can be completed end to end.
- [x] Connect a same-company on-demand financial snapshot to the Comprehensive
      Research Agent as partial evidence, while keeping verified multi-year
      history first and avoiding duplicate PDF parsing.
- [x] Convert a completed onboarding package into a production-shaped CSV
      candidate with deterministic RMB-unit conversion, official PDF links,
      page provenance, and a non-importable candidate status.
- [x] Add resumable one-click serial processing for all remaining onboarding
      reports while keeping only one PDF in memory and preserving the human
      approval gate.
- [x] Add a bounded audited-company expansion Agent that discovers three
      official complete annual reports, processes one PDF at a time, checks
      three reconciled statements and units, surfaces restatement clues, and
      exports a candidate JSON package behind a mandatory human approval gate.
- [x] Export the Comprehensive Research run as a versioned JSON audit package
      with five evidence lanes, Agent trace, matching radar context, official
      URL filtering, and a clearly bounded SHA-256 evidence fingerprint.
- [x] Preserve the matching Market Radar trigger and validated disclosure clue
      inside the downloadable Comprehensive Research report without changing
      calculations, evidence coverage, or conclusions.
- [x] Connect a Market Radar candidate to the Comprehensive Research Agent with
      same-company session context, explicit re-verification, and no automatic
      external request on navigation.
- [x] Separate broad on-demand A-share access from the audited
      deep-dive catalogue on the home page and state the product boundary.
- [x] Promote Midea's 2023-2025 candidate package into the verified catalogue
      after three-statement reconciliation and cross-report consistency checks.
- [x] Add an offline-first company-code path, faster market-source order,
      parallel market/disclosure loading, shared one-hour caching, and visible
      comprehensive-run timing.
- [x] Remove the duplicate full-history turnover decode and bound both market
      providers to protect the Render free instance from long waits and memory
      spikes.
- [x] Bound and parallelise official-disclosure pagination, query only annual
      reports on the annual-report page, and lazy-load PDF parsing.
- [x] Preserve Tencent's raw ordinary-turnover field in bounded fast-path
      chunks, with Eastmoney retained only as a provider-outage fallback.
- [x] Migrate all production pages to Streamlit's current stretch-width API
      and guard against reintroducing the removed container-width argument.
- [x] Add staged loading, elapsed-time receipts, and source-health visibility
      to the three core research pages; parallelise anomaly data loading.
- [x] Add browser-local recent research and a five-company watchlist without
      login, server-side user records, or extra cloud storage.
- [x] Connect the browser-local watchlist to the bounded Market Radar with
      one-click scanning while keeping manual code input.
- [x] Run Market Radar with a bounded three-company worker pool and display
      measured scan time without weakening per-company failure isolation.
- [x] Skip the full company-directory download for already verified radar
      codes while retaining on-demand directory lookup for all other codes.
- [x] Reposition the product as a Chinese listed-company research Agent.
- [x] Add a clean home page and separate research subpages.
- [x] Add company-name and six-digit stock-code identification.
- [x] Add a source-linked official disclosure wall with on-demand refresh.
- [x] Add daily K-lines, volume, moving averages, returns, volatility, and drawdown.
- [x] Add latest-session market-activity evidence with explicit data limits.
- [x] Add point-in-time volume and ordinary-turnover historical percentiles.
- [x] Add a dedicated volume-and-turnover research page.
- [x] Add provenance-aware optional effective-turnover verification.
- [x] Add a standalone audited Financial Trend Lab for the flagship case.
- [x] Add an on-demand daily limit-up board with transparent ranking.
- [x] Add a deterministic post-market limit-up structure review.
- [x] Add a bounded five-company watchlist anomaly radar.
- [x] Connect the watchlist radar to official disclosures and generate a deterministic research task queue.
- [x] Export the research task queue as an offline, source-linked Chinese HTML brief.
- [x] Add abnormal-trading-day replay into Historical Lens.
- [x] Add point-in-time activity percentiles to abnormal-day replay.
- [x] Link selected abnormal days to nearby point-in-time official evidence.
- [x] Add a dedicated Market Anomaly Agent page.
- [x] Include high ordinary-turnover percentile days in anomaly screening.
- [x] Verify that the Tencent adapter truncates a wider raw row and preserve
      the raw ordinary-turnover field with explicit provenance.
- [x] Synthesize independent price, volume, and turnover checks without predictions.
- [x] Export a selected anomaly date as an auditable offline research report.
- [x] Match a selected anomaly to strictly earlier rule-based historical analogs.
- [x] Include historical analog evidence and replay links in the offline report.
- [x] Deep-link each exported analog to its company and Historical Lens date.
- [x] Define Company Research Engine and Historical Lens product specifications.
- [x] Add a tested point-in-time evidence engine that excludes future disclosures.
- [x] Add a Historical Lens page with a separate 1/3/6-month outcome reveal.
- [x] Manually verify three flagship Historical Lens event dates for 贵州茅台.
- [x] Add point-in-time profitability and cash-quality ratios.
- [x] Find the latest complete official annual report and exclude summaries.
- [x] Prefer the Chinese original over a translation for the same report year.
- [x] Add server-side official PDF loading with signature and size checks.
- [x] Validate the public data adapters in the deployed Render environment.
- [x] Deploy the multi-page version to the existing website.
- [x] Confirm operating system and preferred development setup.
- [x] Install Python, Git, and a code editor.
- [x] Create and activate a virtual environment.
- [x] Run `src/app.py`.
- [x] Run `pytest`.
- [x] Implement and test the first financial-ratio function.
- [x] Build the first Streamlit product interface.
- [x] Test profitable, loss-making, and zero-revenue scenarios.
- [x] Build and test the revenue growth calculator.
- [ ] Try the product with user-selected figures.
- [x] Confirm the revenue growth formula with the project owner.
- [x] Build and test the current ratio calculator.
- [x] Confirm the current ratio formula with the project owner.
- [x] Build and test the liabilities-to-assets calculator.
- [x] Confirm the liabilities-to-assets formula with the project owner.
- [x] Build and test PDF upload with page-level text extraction.
- [x] Test PDF extraction with the first real annual report.
- [x] Automatically find the income statement and extract revenue and profit totals.
- [x] Add deterministic extraction for common Chinese A-share consolidated income statements.
- [x] Add reconciled extraction for common Chinese A-share consolidated balance sheets.
- [x] Add reconciled extraction for common Chinese A-share consolidated cash-flow statements.
- [x] Support multi-page Chinese statements and retain their PDF page ranges.
- [x] Validate all three extractors against the real Guizhou Moutai 2025 statement layout.
- [x] Use a lightweight Chinese evidence-retrieval path on the free server.
- [x] Compare current and previous income-statement figures with period warnings.
- [x] Extract and reconcile balance-sheet liquidity figures.
- [x] Calculate current and previous current ratios from the annual report.
- [x] Reconcile total assets, total liabilities, and net assets.
- [x] Calculate liabilities-to-assets ratios from the annual report.
- [x] Extract and reconcile the group cash flow statement.
- [x] Compare operating, investing, and financing cash flows.

## Next
- [x] Choose the first annual report: Tesco PLC 2026.
- [x] Define the initial financial indicators.
- [x] Create a small, manually checked sample dataset.
- [x] Compare live PDF extraction with the verified answer key.
- [x] Split report text into searchable chunks that preserve PDF pages.
- [x] Add keyword evidence search with PDF-page citations.
- [x] Add concept-aware retrieval for differently worded finance questions.
- [x] Draft extractive answers using only cited report evidence.
- [x] Structure answers as conclusion, evidence, and limitation.
- [x] Refuse to answer when retrieved evidence is too weak.
- [x] Add the rule-based, page-cited foundation for Skeptic Mode.
- [x] Add a deterministic Verifier Agent for provenance and disclosure checks.
- [x] Add an Agent Router that controls evidence and challenge depth.
- [x] Route four supported report metrics to deterministic Python tools.
- [x] Add deterministic, explainable dynamic escalation between Agent depths.
- [x] Coordinate Agent handoffs and export a structured JSON audit trail.
- [x] Add a human-defined Q&A evaluation benchmark and quality dashboard.
- [x] Add local embedding-based semantic retrieval beyond the concept dictionary.
- [x] Add a portfolio-quality branded interface and developer attribution.
- [x] Add a Chinese-first domestic recruitment demonstration interface.
- [x] Add CNY as the default manual-analysis currency.
- [x] Add a downloadable Chinese user guide and interview-demo script.
- [x] Show the full **Durham University** attribution across the product.
- [x] Add public-hosting configuration with a health check and custom-domain support.
- [x] Bound report caches and disable memory-heavy local embeddings on the free server.
- [x] Retrieve Chinese annual-report evidence directly from Chinese questions.

## Later
- [x] LLM integration with structured outputs and local guardrails.
- [ ] Enable API billing/quota before the first live LLM answer.
- [ ] Add source-controlled media news only after source-quality evaluation.
- [ ] Add scheduled background refresh only when traffic justifies the cost.
- [ ] Extend deterministic statement extraction to bank, insurer, and other special-industry layouts.
- [x] Extend audited cross-year financial trends beyond the flagship case.
- [x] Add a standardised audited-company onboarding catalogue with automatic checks.
- [x] Prove catalogue-only expansion by adding BYD as the third audited company.
- [x] Add common-year cross-company comparison with official evidence and an
  explicit non-peer warning.
- [x] Add annual-report-backed industry evidence and conservative peer-group candidate rules.
- [x] Onboard Wuliangye as the second verified company in the baijiu peer group.
- [x] Add the first deterministic financial-anomaly explanation with a
      page-linked cash-flow bridge and explicit unresolved-cause boundary.
- [x] Prove the financial-anomaly explanation is reusable by adding BYD 2024
      with an 18-row page-linked cash-flow bridge and dynamic research questions.
- [x] Add a device-local Evidence Delta Agent that rechecks official
      disclosures since the previous successful review without requiring a
      login, cloud database, or paid AI API.
- [x] Add a human-reviewed Research Thesis Ledger with falsifiable criteria,
      topic-matched official evidence, browser-local persistence, and a safe
      offline export.
- [x] Add an on-demand, single-report financial snapshot for ordinary A-share
      companies with three-statement reconciliation, page provenance, bounded
      PDF memory, safe HTML export, and a mandatory human-review status.
- [ ] Add comparable-company valuation only after business-mix, accounting, and same-date market checks.
- [ ] Expand the 贵州茅台 flagship set from three to five events after review.
- [x] GitHub publication and public Render website.
- [ ] Complete recruitment materials.
- [ ] Complete any remaining standalone Python exercises if useful.

## 2026-08-11 — Conclusion-first company research

- [x] Add a deterministic important-question ranking engine.
- [x] Put one company research conclusion card above detailed evidence.
- [x] Keep financial, market, and official-disclosure states separate.
- [x] Make low evidence coverage override attention-grabbing market signals.
- [x] Preserve the same conclusion in HTML and JSON exports.
- [x] Keep numeric priorities internal and retain the non-advisory boundary.

## 2026-08-11 — One-action company research entry

- [x] Treat “开始研究” as the explicit request for one bounded public-data run.
- [x] Complete and store the matching brief before the page transition.
- [x] Clear the previous company's rendered brief before the new run.
- [x] Keep passive page navigation free from automatic external requests.
- [x] Offer “重新运行并刷新公开数据” after a matching result exists.

## 2026-08-12 — Landing page and first-case presentation

- [x] Restore a polished hidden default landing page at the root URL.
- [x] Keep only 《消失的现金》 and 研究案件 in the public sidebar.
- [x] Route each landing-page card to its matching parent module.
- [x] Add a distinct first-case intake scene with restrained challenge copy.
- [x] Show the complete game-stage navigator with completed, current, and locked states.
- [x] Keep the game-stage navigator usable through horizontal scrolling on narrow screens.

## 2026-08-30 — PDF stability boundary and unified research cases

- [x] Reduce the Streamlit upload boundary from 200 MB to 32 MB.
- [x] Give manual, official, onboarding, and snapshot PDF paths named limits.
- [x] Reject encrypted, oversized, over-page, and over-text PDFs without partial evidence.
- [x] Serialise PyMuPDF extraction per server process to avoid concurrent memory spikes.
- [x] Add downloader, parser, configuration, and resource-policy regression tests.
- [x] Replace cross-session raw-PDF caches with one bounded, text-only parsed
      report artifact per browser session, bound to company and SHA-256 fingerprint.
- [x] Add the browser-persisted `wfz.research_cases.v1` Store behind the five-question workspace.
- [x] Define revision-checked, idempotent CasePatch and Store reducers with bounded payloads.
- [x] Connect explicit Comprehensive Research and Historical Lens results to Research Case patches.
- [x] Connect completed five-field annual-report review, verifier-approved annual-report
      Q&A source excerpts, and official Evidence Delta references to the same case.
- [ ] Convert the remaining specialist research views into bounded CasePatch producers.
- [x] Add field-level annual-report confirmation, correction, and rejection for all five core metrics.
- [x] Preserve original value, unit, accounting basis, PDF pages, excerpt, decision and correction reason.
- [x] Add a gated complete-case workpaper export layer with evidence, contradictions, unknowns,
      hypotheses, Responsible AI controls, audit history and a case fingerprint.
- [x] Surface the formal complete-case download in the workspace only when `ready_to_export` is true.
- [x] Synchronise README, product scope, Research Case, snapshot and Chinese user-guide terminology.


## 2026-09-21 — Batch financial coverage

- [x] Add Ningbo Bank signed-income/unsigned-cash template and verify 2024/2025 real reports.
- [x] Add 248 explicit BSE old/current code mappings without rewriting historical identities.
- [x] Add bounded manifest-driven batch auditing with per-item journals and visible failures.
- [x] Check 60 companies using current codes and 12 official PDFs (10 ready, 2 blocked).
- [x] Compare 50 candidate amounts to same-year public values; fix Gree note-reference revenue error.
- [x] Support scoped, source-preserving statement-unit inheritance (BYD 2024).
- [x] Define and test unit-aware rounding reconciliation (CATL 2024).
- [ ] Expand real-report fixtures to securities, insurance and further market segments.
- [ ] Verify new samples through browser and genuine human review; deployment remains separate.

2026-09-21 follow-up: the same 12 official reports now all produce review candidates; 60 same-year public/PDF amount checks pass, previous ten reports retain both-period amounts. 924 tests pass; no new human confirmations or deployment.


## 2026-09-21 — Financial sector boundaries and first BSE PDF

- [x] Validate Jinbo 2024 using current BSE code; fix wrapped parent-profit sign annotation.
- [x] Accept exact Chinese-numeral annual-report years while rejecting wrong years and summaries.
- [x] Identify explicit securities/insurance issuers and retain unsupported status through review/export/case; keep generic ratios disabled.
- [x] Rerun 15 PDFs: 13 candidates, 2 unsupported; all 65 comparable amounts agree within existing tolerances; 939 tests pass.
- [x] Implement and validate Huatai 2024 consolidated/company four-column financial statements.
- [x] Implement separately evidenced insurance/group revenue and three-statement reconciliation for explicitly verified layouts; see 2026-09-23 scope.
- [ ] Retrieve and verify further BSE samples; BTR official download remains HTTP403.

2026-09-21证券模板后续：15份样本14份候选；70项对照69一致、1项收入差异由华泰2025年报重述说明支持。956 tests passed。后续补第二年度/第二家证券真实样本；2025报告目前仅作为重述证据，不计入完整解析覆盖。


## 2026-09-23 — Multi-insurer batch

- [x] Add PICC/CPIC two-year and NCI consolidated/company four-column 2024 templates; validate signed/unsigned expenses, parent columns, and all three statements.
- [x] Bind known insurer identities; block general fallback even when the cover name is an image. New extraction still requires legal-name evidence.
- [x] Preserve operating revenue vs total operating revenue across snapshot, public comparison, review, export and case policies.
- [x] Admit only the two exact verified CPIC 2024/Ping An 2023 company-hosted PDF URLs; arbitrary company-host URLs remain rejected.
- [x] Run all 19 complete PDFs through manual-upload functions; 19 candidates, no human confirmations. Prior 14 candidates retain both-year amounts.
- [x] Compare all 15 new current-year amounts with public source; all amount-close, not human-verified.
- [ ] Validate additional insurer years and China Life's new-standard, restated multi-year layout; China Life mirror was diagnostic only.
- [ ] Add more securities/BSE issuer fixtures and continue remaining research-view case producers.


## 2026-09-23 — Cross-year insurance/securities batch

- [x] Add full-report CPIC/NCI 2025, Huatai 2025 and China Life 2024/2025 fixtures and explicit layout rules.
- [x] Preserve Huatai restated group comparatives and negative operating cash flow; suppress China Life 2024 automatic growth for mixed accounting-standard comparatives.
- [x] Fix independent-review findings: Ping An legal-name gate, malformed thousands separators, and extra comparison/amount columns.
- [x] Run 25 official full PDFs: 24 candidates and PICC 2025 needs-review; no filled-in missing amounts and no human confirmations.
- [x] Check 25 new current-year public/PDF amounts and preserve all prior 19 reports' current/prior values.
- [ ] Obtain usable official PICC 2025 numeric text and validate its year profile before enabling.
- [ ] Expand beyond the verified securities issuer and BSE sample; untested reports remain unclaimed.

## 2026-09-23 — Wider issuer coverage and navigation reliability

- [x] Add CMS Securities 2024/2025 with strict legal-name/code/year evidence and all consolidated/parent statement checks.
- [x] Validate eight additional 2025 ordinary-company/BSE reports, including BTR as a second BSE issuer.
- [x] Require explicit parent-attributable profit; prevent parent-table borrowing and nonconsecutive-page joins.
- [x] Validate standalone unit declarations across continuation headers; reject conflicting units without re-inheriting them.
- [x] Fix reproduced navigation registration and empty-case-storage acknowledgement races; verify saved-state restoration.
- [x] Run 35 complete PDFs: 34 candidates, PICC 2025 still needs review; previous 25 reports unchanged.
- [x] Compare 50 new current amounts: 49 close, Huichuan assets differ by RMB390,000; preserve both values, cause unverified.
- [ ] Obtain usable PICC 2025 numerical source without substituting vendor/manual amounts.
- [ ] Further investigate Huichuan vendor/official asset difference and remaining untested issuer/year layouts.

## 2026-09-24 — General profit reconciliation and seven-report expansion

- [x] Add two-period tax-to-net and parent/minority-profit arithmetic checks with Decimal, original units, page evidence and explicit rounding limits.
- [x] Bind checked parent profit to displayed output; reject reversed/missing/extra period columns, damaged numeric cells, duplicate rows and borrowed parent-table evidence.
- [x] Validate four Shanghai 2025 reports plus Linton/Jinbo 2025 and BTR 2024; 42 complete PDFs now yield 41 candidates and one unsupported PICC 2025.
- [x] Preserve all prior 35 reports' status and both-period amounts; retain financial-sector-specific rules.
- [x] Carry arithmetic details into snapshot, HTML, UI and batch receipts; label legacy generic snapshots as requiring regeneration.
- [x] Explain Huichuan RMB390,000 difference using official 2026Q1 before/after figures, without replacing the original annual value.
- [x] Compare 35 added current amounts: 33 close, two Shenhua balance differences retained and matched to later interim restatement columns.
- [ ] Expand complete-report coverage beyond these explicitly tested issuer/year layouts; PICC 2025 still needs a usable numeric source.
- [ ] Extend ordinary-income component reconciliation beyond the two checked subtotal relationships.

## 2026-09-24 — Eight industry reports and official restatement explanations

- [x] Run 50 complete official annual PDFs in two batches capped at 40: 46 candidates, four needs-review reports, 38 companies, zero new human financial confirmations.
- [x] Add COSCO Shipping, China Mobile, SANY, Vanke and Yangtze Power 2025 candidates; compare all 25 current amounts with the public source, all amount-close.
- [x] Preserve the previous 42 reports' status and both-period amounts. Support only the exact evidenced Vanke loss qualifiers; reject unknown qualifiers.
- [x] Keep LONGi split-sign, PetroChina signed-expense/cash-outflow, CMOC image-only statements and prior PICC 2025 numeric-layer failures explicit. Zijin's oversized original is excluded from the 50-report count.
- [x] Register three precise Huichuan/Shenhua restatement explanations using company/year/original SHA/metric/both amounts; additionally match source URL/date/page count at the comparison boundary.
- [x] Display original/restated amounts, official sources and physical pages in current and saved comparisons. Preserve original values, difference statuses, human review decisions and historical receipts; no vendor update mechanism is inferred.
- [ ] Support the remaining PDF layouts using independently evidenced rules or a separately validated image-reading workflow; never infer signs or substitute vendor values to pass checks.
- [ ] Expand beyond the three registered restatement explanations and the explicitly tested reports.
