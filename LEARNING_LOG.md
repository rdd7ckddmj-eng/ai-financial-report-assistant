# Learning log

Use one entry after each study session.

## Date

### What I studied

### What I built or changed

### One concept I can now explain

### Error I encountered

### How I fixed it

### What I still do not understand

### Next action

## 2026-07-29

### What I studied

The difference between deterministic Python calculations and LLM-generated
explanations, and why an API key alone does not provide API billing quota.

### What I built or changed

Added an optional LLM Synthesis Agent that runs only after the local Verifier
approves report evidence.

### One concept I can now explain

Python remains the source of financial figures. The LLM receives only approved
evidence and organises it into a readable explanation.

### Error I encountered

The live API check returned `insufficient_quota`.

### How I fixed it

The product now detects that safe error, shows a clear message, and falls back
to the verified extractive answer instead of failing or inventing content.

### What I still do not understand

How API prepaid credits and billing limits should be configured.

### Next action

Decide whether to enable a small API budget, then run the first live,
evidence-grounded LLM answer.

## 2026-07-30

### What I studied

Why extracting a financial statement requires both row recognition and
accounting reconciliation.

### What I built or changed

Added deterministic support for common Chinese A-share consolidated balance
sheets, including current/prior-year figures, RMB units, and Chinese punctuation.

### One concept I can now explain

A recognised number is not automatically a reliable number. The program checks
current plus non-current assets, current plus non-current liabilities, and the
accounting equation before accepting the extraction.

### Error I encountered

The existing interface described the Tesco-specific held-for-sale presentation,
which would be misleading for a Chinese balance sheet.

### How I fixed it

The extraction records the statement format, and the interface now uses the
correct Chinese labels and explains that held-for-sale assets are already
included in current assets.

### What I still do not understand

How many additional layouts are needed for banks, insurers, and image-only PDF
reports.

### Next action

Validate the extractor against a real Chinese annual-report PDF, then adapt the
cash-flow statement without weakening the reconciliation rules.

## 2026-07-30 — Cash-flow extension

### What I studied

The presentation difference between an English cash-flow statement and a
Chinese A-share cash-flow statement.

### What I built or changed

Added deterministic extraction for a common Chinese consolidated cash-flow
statement and updated the interface to show the Chinese reconciliation.

### One concept I can now explain

The Chinese row “现金及现金等价物净增加额” normally already includes the
foreign-exchange effect. Adding that effect again when reconciling opening and
ending cash would double count it.

### Error I encountered

The existing Tesco formula treated the foreign-exchange effect as separate from
the reported net cash change.

### How I fixed it

The extractor records the statement format and applies a dedicated
reconciliation formula to each format for both the current and prior year.

### What I still do not understand

How reliably image-only annual reports can be processed without adding OCR.

### Next action

Run a complete Chinese annual-report case through all three statement
extractors and record any unsupported layout differences.

## 2026-07-30 — Real annual-report selection

### What I studied

Why “latest publication date” and “latest reporting year” are not always the
same selection rule.

### What I built or changed

Changed annual-report selection so the newest reporting year is chosen first,
then the Chinese original is preferred over a later English translation.

### One concept I can now explain

An English translation published later does not make it the primary source for
testing a Chinese financial-statement extractor.

### Error I encountered

The live website selected 贵州茅台2025年年度报告（英文版） because it had a
later announcement date than the Chinese original.

### How I fixed it

The program now compares report years before comparing language and publication
order, while still using English when it is the only version for that year.

### What I still do not understand

Whether every listed company uses a title that includes the four-digit report
year.

### Next action

Deploy the selector fix and automatically load the Chinese original for
three-statement extraction testing.

## 2026-07-30 — Multi-page Chinese statement verification

### What I studied

Why a real annual report cannot be treated as one table per PDF page.

### What I built or changed

Added bounded adjacent-page windows for the Chinese consolidated income
statement, balance sheet, and cash-flow statement. The interface now shows the
verified page range for each statement and defaults optional paid LLM synthesis
to off.

### One concept I can now explain

The program may join nearby pages to read one statement, but it still rejects
the result unless all required rows and accounting reconciliations agree.

### Error I encountered

The 143-page Guizhou Moutai report loaded successfully, but the old extractors
returned no figures because the three statements covered two to four pages.
Chinese Q&A also tried to load an English embedding model on the free server.

### How I fixed it

Added realistic split-page regression cases using Guizhou Moutai statement
values and switched Chinese or very large report searches to the transparent
lexical/concept retriever.

### What I still do not understand

How many bank and insurer statement variants need separate deterministic
templates.

### Next action

Deploy this version and rerun the official Guizhou Moutai PDF through all three
statement checks on the public website.
