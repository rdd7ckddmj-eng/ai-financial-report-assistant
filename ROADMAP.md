# 12-week roadmap

Assumption: 10–12 focused hours per week.

## Phase 0 — Baseline and setup

### Week 1: Environment and Python basics
Learn variables, strings, lists, dictionaries, conditions, loops, functions, paths, and error messages.

Deliverables:
- working Python environment;
- first Git repository;
- five small Python exercises;
- learning log.

### Week 2: Finance refresh I
Rebuild the three financial statements, working capital, operating cash flow, free cash flow, and key links between statements.

Deliverables:
- one-page explanation of the three statements;
- a manually checked ratio sheet;
- a three-minute verbal company analysis.

## Phase 1 — Data and deterministic finance engine

### Week 3: pandas and financial data
Read CSV/Excel, clean missing values, filter, group, merge, and calculate ratios.

Deliverables:
- `financial_ratios.py`;
- a clean sample dataset;
- unit tests for at least five ratios.

### Week 4: Finance refresh II
Cover profitability, liquidity, leverage, interest coverage, cash conversion, growth, and basic credit analysis.

Deliverables:
- a simple credit memo;
- rule-based risk flags;
- documented ratio definitions.

### Week 5: V1 dashboard
Build a Streamlit dashboard for uploaded CSV/Excel data.

Deliverables:
- file upload;
- ratio table;
- trend charts;
- rule-based commentary;
- smoke tests.

## Phase 2 — Annual-report processing

### Week 6: PDF extraction
Read annual-report PDFs, preserve page numbers, clean text, and inspect extraction quality.

Deliverables:
- PDF parser;
- page-level text output;
- extraction-quality checklist.

### Week 7: Document structure
Split text into sections/chunks and identify financial statements, risk factors, and management discussion.

Deliverables:
- chunking module;
- metadata structure;
- ten manually verified chunks.

## Phase 3 — LLM and retrieval

### Week 8: LLM foundations
Understand prompts, APIs, context limits, hallucination, privacy, and structured output.

Deliverables:
- one safe API call;
- `.env` configuration;
- three tested prompts;
- no secret keys committed.

### Week 9: Retrieval-augmented Q&A
Retrieve relevant passages before generating an answer.

Deliverables:
- question-to-passage retrieval;
- answers grounded in retrieved passages;
- page/source display;
- refusal when evidence is insufficient.

### Week 10: Financial-analysis integration
Combine deterministic metrics with report evidence and LLM explanations.

Deliverables:
- profitability analysis;
- cash-flow analysis;
- liquidity/leverage analysis;
- risk summary;
- separation between calculated facts and generated interpretation.

## Phase 4 — Portfolio quality

### Week 11: Evaluation and reliability
Create a benchmark question set, compare answers with source documents, and record failures.

Deliverables:
- at least 25 benchmark questions;
- accuracy/evidence checklist;
- known-limitations document;
- regression tests.

### Week 12: Presentation and recruitment
Polish the interface, README, architecture diagram, demo script, CV bullets, and interview answers.

Deliverables:
- runnable application;
- GitHub-ready repository;
- two-minute demo;
- Chinese and English project descriptions;
- STAR interview story;
- next-step plan for an AI credit assistant.
