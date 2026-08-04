# WFZ Chinese Listed Company Research Agent

A Chinese-first portfolio product combining listed-company research,
financial analysis, public market data, annual-report evidence, and auditable
Agent workflows.

## Project objective

Build a web application that can:

1. identify a mainland listed company from its name or six-digit code;
2. show source-linked official disclosures that refresh on demand;
3. display validated daily K-lines and deterministic market-risk statistics;
4. separate volume, ordinary turnover, and verified effective turnover;
5. organise one recent public limit-up pool into a daily research wall;
6. combine watchlist activity evidence and recent official disclosures into a
   deterministic research task queue;
7. connect a selected candidate to point-in-time official disclosures;
8. locate and temporarily load the latest official annual report;
9. extract and calculate key financial indicators;
10. answer questions using retrieved report evidence and PDF pages;
11. show source references, limitations, and the Agent audit trail;
12. revisit a past date without leaking later information into the snapshot;
13. export a selected anomaly date as an auditable offline research report;
14. compare audited multi-year financial trends without losing report versions;
15. compare multiple verified companies on one common financial year while
    retaining each annual-report source and page;
16. avoid presenting AI output as investment advice.
17. run one bounded Comprehensive Research Agent that joins identity, market,
    disclosure, annual-report, and verified-financial evidence into a
    downloadable brief without hiding missing sources.
18. build a three-report, page-linked candidate package for expanding the
    audited company catalogue while retaining a mandatory human approval gate.
19. explain verified financial-direction mismatches through annual-report
    cash-flow bridges while separating confirmed arithmetic from unresolved
    business causes.

## Product specifications

- [Product Scope and Positioning](docs/PRODUCT_SCOPE.md) separates broad
  on-demand A-share research from the narrower audited deep-dive catalogue and
  states the commercial-database boundary.
- [Company Research Engine](docs/COMPANY_RESEARCH_ENGINE_SPEC.md) defines the
  current-company research scope, evidence grades, verification states, and
  division between Python and AI.
- [Comprehensive Research Agent](docs/COMPREHENSIVE_RESEARCH_AGENT_SPEC.md)
  defines the five evidence lanes, evidence-coverage meaning, failure
  isolation, deterministic observations, and portable research brief.
- [Market Anomaly Agent](docs/MARKET_ANOMALY_AGENT_SPEC.md) defines the
  deterministic anomaly rules, official-evidence link, and non-predictive
  product boundary.
- [Volume and Turnover Research](docs/VOLUME_TURNOVER_SPEC.md) defines the
  point-in-time participation metrics, bounded activity review, and
  provenance-aware effective-turnover verification.
- [Daily Limit-Up Board](docs/LIMIT_UP_BOARD_SPEC.md) defines the recent
  public pool, validation, post-market structure review, deterministic
  ranking, and ordinary-versus-effective-turnover boundary.
- [Watchlist Research Queue](docs/MARKET_RADAR_SPEC.md) defines the bounded
  five-company scan, three independent activity triggers, recent official
  disclosure check, known-code directory fast path, P1/P2/P3 research order,
  and free-server boundary.
- [Historical Lens](docs/HISTORICAL_LENS_SPEC.md) defines the point-in-time
  boundary, publication-date filtering, and separate later-outcome reveal.
- [Financial Trend Lab](docs/FINANCIAL_TREND_LAB_SPEC.md) defines the audited
  multi-year calculations, restatement handling, evidence pages, and
  non-predictive boundary.
- [Financial Anomaly Explanation Agent](docs/FINANCIAL_ANOMALY_EXPLANATION_AGENT_SPEC.md)
  defines the deterministic signal, annual-report cash-flow bridge, confirmed
  findings, unresolved cause questions, and non-advisory boundary.
- [Cross-Company Comparison](docs/CROSS_COMPANY_COMPARISON_SPEC.md) defines the
  common-year rule, sample-median descriptions, annual-report evidence, and
  boundary between a cross-industry demonstration and a true peer group.
- [Baijiu Operating Quality](docs/BAIJIU_OPERATING_QUALITY_SPEC.md) defines the
  audited 2023-2025 gross-margin, inventory, contract-liability, cash-quality,
  and three-year trend calculations that appear only for the verified baijiu
  peer candidate.
- [Audited Company Onboarding Agent](docs/AUDITED_COMPANY_ONBOARDING_AGENT_SPEC.md)
  defines official three-report discovery, statement and unit checks,
  restatement clues, the 32 MB free-server boundary, and the mandatory human
  approval gate before any catalogue write.

## Development principles

- Build in small, testable versions.
- Use Python for all deterministic calculations.
- Use an LLM mainly for explanation and summarisation.
- Never let the LLM invent financial figures.
- Every report-based answer should show supporting evidence.
- Never commit API keys, private bank information, or confidential client data.

## Versions

### V0 — Foundations
Python basics, Git, project structure, and finance refresh.

### V1 — Deterministic financial analysis
Read CSV/Excel data, calculate ratios, generate charts, and create rule-based commentary.

### V2 — Annual-report extraction
Read PDFs, clean text, identify relevant sections, and preserve page metadata.

### V3 — Evidence-grounded Q&A
Add retrieval, answer questions from selected report passages, and display citations.

### V4 — Portfolio product
Build a Streamlit interface, tests, documentation, evaluation cases, and a demo.

## Quick start

1. Create a Python virtual environment.
2. Install packages from `requirements.txt`.
3. Copy `.env.example` to `.env` and add a local API key for the optional
   LLM synthesis step. The `.env` file is ignored by Git.
4. Run tests with `pytest`.
5. Run the application with `streamlit run src/app.py`.

The company directory, official-disclosure wall, and K-line page use public
data adapters and do not require an OpenAI API key. Public sources can be
temporarily rate-limited or unavailable, so the product keeps official links
and manual PDF upload as fallbacks.

The OpenAI Platform API is billed separately from a ChatGPT subscription.
Without available API quota, the product keeps the verified extractive answer
and explains why the optional LLM step did not run.

## Public deployment

The project includes a Render Blueprint in `render.yaml`. It runs the existing
Streamlit application as a Python web service, exposes Streamlit's health
endpoint, and can be connected to a custom domain with managed HTTPS.

The optional `OPENAI_API_KEY` must be added through the hosting provider's
secret environment settings. It must never be committed to the repository.

## Current working features

- Present two explicit coverage layers on the home page: on-demand identity,
  market, disclosure, and annual-report entry points for Shanghai, Shenzhen,
  and Beijing listed-company codes when public sources are available; plus a
  source-controlled audited catalogue of six deep-dive companies, 21
  financial periods, and 23 publication vintages. The site clearly states
  that it is not a real-time trading terminal or commercial data substitute.
- Keep up to six recently researched companies and five self-selected companies
  in the visitor's own browser. The shortcuts require no login or server-side
  user database, store only public company identity and access timestamps, and
  disappear when the visitor clears this site's browser data. The saved local
  watchlist also pre-fills the bounded Market Radar and can be scanned with one
  click without re-entering stock codes. Market Radar checks at most three
  companies concurrently, reports measured scan time, and isolates failures by
  company without increasing the five-company limit.
- Use a first-run performance path for the flagship workflow: six-digit stock
  codes and the verified demonstration list resolve without downloading the
  full A-share directory; Tencent daily history is attempted before the slower
  market fallback; market history and official disclosures are fetched in
  parallel; CNINFO disclosure pages use per-request timeouts, a small bounded
  worker pool, and a hard response-size/page limit; and the bounded result
  bundle is cached for one hour. PDF parsing is loaded only after a report is
  submitted. The page displays the measured run time without weakening source
  labels or failure isolation.
- Run a one-click Comprehensive Research Agent for one selected A-share
  company. It independently checks company identity, market/activity evidence,
  official disclosures, the latest complete annual report, and any available
  page-linked financial history. The page shows evidence coverage rather than
  an investment score, preserves failed lanes, exposes a six-step Agent trace,
  recommends the next verification page, and exports both a safe offline HTML
  brief and a versioned JSON audit package with a SHA-256 evidence fingerprint.
  A radar candidate can open this workflow with its queue priority, triggered
  signals, task reason, and latest disclosure clue, but the user still starts
  the run explicitly and all five lanes independently re-verify their evidence.
  When present, the matching trigger context is also preserved as a separate,
  non-scoring section in both exports; untrusted links and another company's
  context are excluded. The fingerprint identifies an evidence payload but is
  not presented as a digital signature or third-party certification.
- Use a responsive institutional research-terminal interface with a dark
  grouped navigation rail, consistent page-introduction cards, a visible
  sidebar close control, and a persistent reopen control after collapse.
- Provide a multi-page product structure: home, company research centre,
  K-line and market evidence, Daily Limit-Up Board, Watchlist Market Radar,
  Market Anomaly Agent, Historical Lens, annual-report evidence, Financial
  Trend Lab, audited-company onboarding, and methodology/audit.
- Build an audited-company candidate package for any selected ordinary A-share
  company: discover the latest three distinct complete annual reports, process
  only one bounded PDF at a time, reconcile three statements, retain five core
  values and page ranges, flag cross-report restatement clues, and export JSON.
  The workflow never writes to the verified catalogue without separate human
  review and therefore does not turn automated extraction into an audit claim.
- Resolve mainland listed-company names or six-digit stock codes to a
  code-plus-exchange identity shared across all pages.
- Synchronise official CNINFO disclosures on demand with a one-hour cache,
  source links, topic classification, and a neutral attention level instead of
  unsupported bullish/bearish labels.
- Find the latest complete annual report while excluding summaries, inquiry
  letters, cancellations, and replies; prefer the Chinese original over a
  later translation for the same reporting year.
- Temporarily load a validated CNINFO annual-report PDF on the server and feed
  it into the existing evidence workflow, with manual upload as a fallback.
- Display daily candlesticks, volume, MA5/MA20/MA60, 20/60/250-trading-day
  returns, annualised historical volatility, and maximum drawdown.
- Retrieve one recent Eastmoney public limit-up pool on demand and show daily
  limit-up count, first-board and consecutive-board counts, maximum streak,
  ordinary-turnover median, leading industry, amount, seal funds, first seal
  time, break count, and a deterministic research order. The same validated
  pool also produces a board ladder, top-five industry structure, early-seal
  coverage, reseal coverage, and rule-based observations without a forecast.
  The page makes one bounded pool request, needs no paid API, and does not
  persist a full-market history.
- Show a deterministic market-activity evidence panel with the latest daily
  return, volume versus the preceding 20-session median, ordinary turnover
  availability, point-in-time volume and turnover percentiles versus up to
  250 preceding sessions, and a board-rule-based limit-up candidate label.
  When the primary Eastmoney history is unavailable and Tencent becomes the
  price/volume fallback, ordinary turnover is supplemented on demand from
  Sina's documented traded-volume divided by circulating-share fields.
  Effective turnover remains unavailable until a verified point-in-time
  investable free-float denominator is connected.
- Provide a dedicated volume-and-turnover page that counts recent high-volume
  and high ordinary-turnover sessions, plots a bounded 60-session
  participation history, and preserves the distinction between ordinary and
  effective turnover. An optional verification form calculates effective
  turnover only after the user supplies same-unit circulating and free-float
  shares plus a traceable source; missing denominators are never estimated.
- Scan up to five user-entered A-share codes on demand, combine three market
  activity triggers with recent validated official disclosures, display the
  latest source, and create an explained P1/P2/P3 research task queue. Export
  the queue as a self-contained Chinese HTML brief with the task reasons,
  metrics, source labels, official links, failed scans, and non-predictive
  boundary. Disclosure failures do not erase valid market results, each company
  fails independently, and no paid API or persistent full-market dataset is
  required. A primary action carries the selected candidate into the
  Comprehensive Research Agent as session-only research context; it does not
  persist a user record or convert a radar clue into an investment conclusion.
- Scan the latest 250 trading sessions for limit-up candidates, days whose
  volume is at least twice the preceding 20-session median, and days whose
  ordinary turnover reaches the 90th percentile of prior observations.
  A dedicated Market Anomaly Agent synthesises the three checks, connects a
  selected date to official disclosures, and can carry it into Historical Lens
  without weakening its publication-date boundary.
- Compare a selected anomaly with strictly earlier anomaly candidates using
  transparent weights for signal overlap, daily return, volume multiple, and
  ordinary-turnover percentile. Missing fields are excluded and weights are
  renormalised; weak matches are rejected. One click opens an earlier analog
  in Historical Lens without exposing any later return.
- Build an auditable abnormal-day evidence chain from official disclosures
  published on the selected date or within the preceding six calendar days.
  Later disclosures are excluded, links and date gaps remain visible, and
  time proximity is never presented as proof of market causation.
- Export the selected anomaly date as a self-contained Chinese HTML research
  report. The file retains calculated metrics, source labels, official links,
  excluded-future-evidence counts, historical analog scores, shared signals,
  comparable-dimension counts, company-and-date Historical Lens deep links,
  and limitations. Each replay link is validated and loads its earlier analog
  only once, so later page interaction remains under the user's control. The
  report can be opened offline or printed to PDF without adding server-side
  document dependencies.
- Rebuild a historical market snapshot at a user-selected cut-off, using only
  earlier observations and disclosures, then reveal the subsequent 20/60/120
  trading-day outcomes in a separate user-controlled step.
- Offer three manually verified Guizhou Moutai flagship dates with direct
  Shanghai Stock Exchange or company-source links, while keeping free date
  selection available.
- Show verified Guizhou Moutai, Wuliangye, Luzhou Laojiao, CATL, BYD, and Midea multi-year financial trends with
  revenue, attributable net profit, operating cash flow, assets, liabilities, annual
  report pages, publication vintages, net margin, cash-to-profit conversion,
  and liabilities-to-assets. A later restatement replaces the original figure
  only after the restatement has actually been published.
- Provide a standalone Financial Trend Lab that calculates three audited
  compound annual change rates, distinguishes revenue-profit and
  profit-operating-cash direction alignment, highlights restated vintages,
  and keeps every annual-report link and evidence page visible. Coverage now
  includes Guizhou Moutai, Wuliangye, and Luzhou Laojiao for 2022-2025 plus
  CATL and BYD for 2022-2024, plus Midea for 2023-2025; other
  companies remain unavailable until they pass the same page-level verification. A
  source-controlled onboarding catalogue now discovers approved companies
  without hard-coded page changes and rejects identity, exchange, year-range,
  file-path, source-domain, page, amount, or accounting-version inconsistencies.
- Explain the verified Midea 2025 and BYD 2024 revenue-profit-cash-flow
  divergences with separate 14-row and 18-row annual-report bridges. Both
  cases reconcile current and comparison-year operating cash flow, rank the
  contribution of each adjustment, adapt unresolved working-capital questions
  to the observed directions, and export a source-linked offline report.
- Provide a standalone Cross-Company Comparison workbench that finds the latest
  financial year shared by every selected verified company, keeps scale,
  growth, profitability, cash conversion, and balance-sheet structure separate,
  and links each displayed row back to its official annual report and pages.
  A separate audited industry catalogue preserves each annual-report label,
  source page, and narrower research peer tag. The current default view spans
  four research groups. Baijiu now has a three-company peer-group candidate,
  while the default six-company view remains cross-industry and
  never produces a composite quality score.
- Add a baijiu-only 2023-2025 operating-quality panel for Guizhou Moutai,
  Wuliangye, and Luzhou Laojiao. It calculates consolidated gross margin,
  inventory growth and asset weight, contract-liability growth and revenue
  weight, and operating-cash conversion from audited report values. Every
  incremental fact retains its income-statement or balance-sheet page. Three
  separate trend charts preserve metric units, while the interface explicitly
  rejects backlog, demand, forecast, and composite quality-score interpretations.
- Record the requested date and effective trading date, use unadjusted prices
  to avoid current adjustment-factor leakage, and audit disclosures excluded
  because they were published after the historical cut-off.
- Validate company-directory fields, OHLC relationships, disclosure domains,
  PDF signatures, and download size before showing or analysing data.
- Present a branded portfolio interface for **WFZ Financial Intelligence**,
  with clear developer attribution to **王方正 · Durham University** and a
  consistent finance-and-technology visual system across research, upload,
  metrics, forms, alerts, and audit results.
- Provide a Chinese-first interface for domestic recruitment demonstrations,
  while preserving original annual-report wording for evidence verification.
- Support **CNY (¥ 人民币)** as the default manual-analysis currency, alongside
  GBP, USD, EUR, and a generic other-currency option.
- Include a downloadable Chinese user guide with operating steps, a
  three-minute interview-demo script, safety boundaries, and troubleshooting.
- Run the full automated test suite during every Render build so a failing
  change cannot replace the live version.
- Upload a public annual-report PDF and preview page-level text.
- Preserve the PDF filename and page number as evidence.
- Automatically extract revenue and profit totals from the verified Tesco
  six-column layout and common Chinese A-share consolidated income statements,
  including RMB units and attributable net profit. Chinese statement windows
  can span adjacent PDF pages without losing the inclusive source-page range.
- Extract current and non-current assets and liabilities, total assets, total
  liabilities, and total equity from common Chinese A-share consolidated
  balance sheets.
- Compare current and previous reported results and flag unequal period lengths.
- Reconcile current plus non-current subtotals to published totals, then verify
  assets equal liabilities plus equity before calculating liquidity and
  leverage ratios.
- Extract and reconcile common Chinese A-share consolidated cash-flow
  statements, including the different treatment of foreign-exchange effects,
  opening cash, and ending cash.
- Show an immediate three-statement verification panel. A statement is marked
  as verified only after its required rows and arithmetic reconciliations pass.
- Calculate net profit margin, revenue growth, current ratio, and
  liabilities-to-assets ratio with deterministic Python functions.
- Check 20 extracted figures against a manually verified Tesco 2026 answer
  key, including source statement, PDF page, row label, unit, and sign.
- Split the report into searchable text segments without losing PDF-page
  provenance.
- Search for report evidence with transparent hybrid ranking: direct
  keywords, bilingual Chinese-report and English-report terms, auditable financial
  concept groups, and an optional small local sentence-embedding model.
  The memory-safe lexical/concept path is the default. Local embeddings require
  `ENABLE_LOCAL_EMBEDDINGS=true`, should only be used on a server with enough
  memory, and remain disabled for Chinese queries and very large reports.
- Draft concise extractive answers using only retrieved report wording, with
  an inline PDF-page citation for every evidence extract.
- Present supported answers as a conclusion plus evidence-backed points, and
  refuse to answer when retrieval only finds a weak one-word overlap.
- Run a transparent first-pass Skeptic Mode that searches retrieved report
  passages for cited offsets, caveats, and limitations before presenting an
  answer.
- Audit every answer and challenge with a deterministic Verifier Agent that
  checks evidence thresholds, source traceability, PDF pages, and disclosure
  consistency before approving, approving with caveats, or rejecting output.
- Route direct lookups, analytical questions, and management-claim questions
  into different evidence and challenge depths with a transparent Agent
  Router.
- Let the Agent Router call deterministic Python tools for net profit margin,
  revenue growth, current ratio, total liabilities, and
  liabilities-to-assets, showing the exact formula, report inputs,
  comparability warnings, and PDF source page.
- Escalate the Agent workflow by one bounded level when deterministic checks
  find weak or missing evidence, counter-evidence, a 53-week versus 52-week
  comparability issue, missing metric inputs, or a rejected verification.
  The page shows the exact signal and the expanded evidence limits.
- Coordinate the Router, Python tool, Retriever, Analyst, Skeptic, and
  Verifier through a shared workflow state. Every handoff records its status,
  task, output summary, and PDF pages, and the full audit record can be
  downloaded as structured JSON.
- Optionally call an OpenAI LLM only after the deterministic Verifier approves
  the evidence. The LLM receives verified excerpts and Python-calculated
  metrics, returns a typed structured response, and is checked again locally
  for valid PDF pages, verbatim support, invented digit-based figures, and
  investment recommendations. A failed API request or guardrail automatically
  falls back to the original verified answer.
- Measure the complete workflow against 10 human-defined Tesco Q&A cases.
  The current deterministic baseline passes 10/10 cases and 92/92 individual checks:
  routing, deterministic metrics, escalation, and safe refusal are 100%;
  key-page retrieval is 100%. The total-liabilities case finds the group
  balance sheet through a deterministic financial-statement scope check,
  without requiring the local embedding model.

## Verified benchmark

The human-checked source data is stored in
`data/verified/tesco_2026_key_figures.csv`. The benchmark covers the income
statement, balance sheet, cash flow statement, and the 53-week versus 52-week
period warning.

The human-defined Q&A regression cases are stored in
`data/verified/tesco_qa_benchmark.csv`. Run them locally with:

```bash
python -m src.qa_benchmark
```

When the local Tesco report is available, `pytest` compares every benchmark
row with the program's live PDF extraction. This catches both incorrect
figures and lost provenance such as a wrong page or unit.

The first Historical Lens flagship dates are stored separately in
`data/verified/moutai_historical_events.csv`. They provide official event
anchors only; later market outcomes are recalculated from validated history
rather than stored as conclusions.

The first point-in-time A-share financial benchmark is stored in
`data/verified/moutai_financial_history.csv`. It records both the original
2022 figures and the later restated vintage, so a historical cut-off never sees
an accounting revision before its publication date.

The second audited benchmark is stored in
`data/verified/catl_financial_history.csv`. It covers CATL's 2022-2024 complete
annual reports, records the source unit conversion to RMB, and retains the
official CNINFO report date plus the summary and consolidated-liability pages.

The Wuliangye benchmark is stored in
`data/verified/wuliangye_financial_history.csv`. It covers 2022-2025, preserves
the original and later restated 2022 vintages, and records the 2025 annual
report's revenue-recognition and quarterly-data comparability note. Together
with Guizhou Moutai, it forms the first annual-report-backed baijiu peer-group
candidate; this status is not a valuation or investment conclusion.

The Luzhou Laojiao benchmark is stored in
`data/verified/luzhou_laojiao_financial_history.csv`. It covers 2022-2025,
records the official CNINFO summary and consolidated-liability pages, and
confirms that none of the four annual reports restates the preceding-year
figures. Together with Guizhou Moutai and Wuliangye, it expands the audited
baijiu peer-group candidate from two companies to three.
