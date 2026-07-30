# WFZ Chinese Listed Company Research Agent

A Chinese-first portfolio product combining listed-company research,
financial analysis, public market data, annual-report evidence, and auditable
Agent workflows.

## Project objective

Build a web application that can:

1. identify a mainland listed company from its name or six-digit code;
2. show source-linked official disclosures that refresh on demand;
3. display validated daily K-lines and deterministic market-risk statistics;
4. locate and temporarily load the latest official annual report;
5. extract and calculate key financial indicators;
6. answer questions using retrieved report evidence and PDF pages;
7. show source references, limitations, and the Agent audit trail;
8. revisit a past date without leaking later information into the snapshot;
9. avoid presenting AI output as investment advice.

## Product specifications

- [Company Research Engine](docs/COMPANY_RESEARCH_ENGINE_SPEC.md) defines the
  current-company research scope, evidence grades, verification states, and
  division between Python and AI.
- [Historical Lens](docs/HISTORICAL_LENS_SPEC.md) defines the point-in-time
  boundary, publication-date filtering, and separate later-outcome reveal.

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

- Provide a multi-page product structure: home, company research centre,
  K-line and market evidence, Historical Lens, annual-report evidence, and
  methodology/audit.
- Resolve mainland listed-company names or six-digit stock codes to a
  code-plus-exchange identity shared across all pages.
- Synchronise official CNINFO disclosures on demand with a one-hour cache,
  source links, topic classification, and a neutral attention level instead of
  unsupported bullish/bearish labels.
- Find the latest complete annual report while excluding summaries, inquiry
  letters, cancellations, and replies.
- Temporarily load a validated CNINFO annual-report PDF on the server and feed
  it into the existing evidence workflow, with manual upload as a fallback.
- Display daily candlesticks, volume, MA5/MA20/MA60, 20/60/250-trading-day
  returns, annualised historical volatility, and maximum drawdown.
- Show a deterministic market-activity evidence panel with the latest daily
  return, volume versus the preceding 20-session median, ordinary turnover
  availability, and a board-rule-based limit-up candidate label.  Effective
  turnover remains unavailable until a verified point-in-time free-float
  denominator is connected.
- Scan the latest 250 trading sessions for limit-up candidates and days whose
  volume is at least twice the preceding 20-session median, then carry a
  selected date into Historical Lens without weakening its publication-date
  boundary.
- Build an auditable abnormal-day evidence chain from official disclosures
  published on the selected date or within the preceding six calendar days.
  Later disclosures are excluded, links and date gaps remain visible, and
  time proximity is never presented as proof of market causation.
- Rebuild a historical market snapshot at a user-selected cut-off, using only
  earlier observations and disclosures, then reveal the subsequent 20/60/120
  trading-day outcomes in a separate user-controlled step.
- Offer three manually verified Guizhou Moutai flagship dates with direct
  Shanghai Stock Exchange or company-source links, while keeping free date
  selection available.
- Show a verified Guizhou Moutai multi-year financial trend with revenue,
  attributable net profit, operating cash flow, assets, liabilities, annual
  report pages, publication vintages, net margin, cash-to-profit conversion,
  and liabilities-to-assets. A later restatement replaces the original figure
  only after the restatement has actually been published.
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
- Upload a public annual-report PDF and preview page-level text.
- Preserve the PDF filename and page number as evidence.
- Automatically extract revenue and profit totals from a supported group
  income-statement layout.
- Compare current and previous reported results and flag unequal period lengths.
- Reconcile balance-sheet current resources and liabilities before calculating
  current ratios.
- Reconcile total assets, total liabilities, and net assets before calculating
  liabilities-to-assets ratios.
- Reconcile operating, investing, and financing cash flows to opening and
  ending cash.
- Calculate net profit margin, revenue growth, current ratio, and
  liabilities-to-assets ratio with deterministic Python functions.
- Check 20 extracted figures against a manually verified Tesco 2026 answer
  key, including source statement, PDF page, row label, unit, and sign.
- Split the report into searchable text segments without losing PDF-page
  provenance.
- Search for report evidence with transparent hybrid ranking: direct
  keywords, common Chinese-to-English mappings, auditable financial
  concept groups, and a small local sentence-embedding model. Report vectors
  are cached locally and the interface shows the retrieval method and semantic
  similarity score.
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
  key-page retrieval is 100%. The previously missed total-liabilities case
  now finds the group balance sheet through hybrid semantic retrieval.

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
