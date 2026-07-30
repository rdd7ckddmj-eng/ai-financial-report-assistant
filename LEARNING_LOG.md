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

## 2026-07-30 — Free-server memory protection

### Error I encountered

Render restarted the free instance after the annual-report workflow exceeded
its memory limit.

### How I fixed it

Made local embeddings an explicit opt-in, reduced their batch and in-memory
index sizes, and limited PDF and report-text caches to the latest report for
thirty minutes. The default lexical/concept retriever, deterministic financial
calculations, statement checks, evidence citations, and optional OpenAI
synthesis remain available.

## 2026-07-30 — Chinese-to-Chinese evidence retrieval

### Error I encountered

The live product extracted and reconciled all three Guizhou Moutai statements,
but a Chinese question such as “营业收入是多少？” found no evidence because
the original retriever translated Chinese questions only into English terms.

### How I fixed it

Added auditable Chinese statement labels and financial phrases to the same
deterministic ranking path. Chinese questions can now retrieve Chinese income
statement, balance-sheet, cash-flow, and narrative evidence without loading an
embedding model.

## 2026-07-30 — Ordinary-turnover fallback

### What I built or changed

Added a small fallback that fills missing ordinary turnover from Sina's
documented daily traded-volume and circulating-share fields when Tencent is
already serving as the backup price source.

### One concept I can now explain

Ordinary turnover is traded shares divided by circulating shares. Effective
turnover uses a narrower investable free-float denominator, so the two figures
must not be presented as interchangeable.

### Error I encountered

The Tencent daily-history fallback kept price and volume available but did not
provide historical turnover, leaving the third anomaly signal unavailable.

### How I fixed it

The program requests only the selected company's bounded date range, calculates
ordinary turnover in Python, merges it by trading date, and keeps the rest of
the product available if the supplemental source also fails.

## 2026-07-30 — Downloadable anomaly research report

### What I built or changed

Added a self-contained Chinese HTML report for the anomaly date selected by
the user. It preserves deterministic market metrics, ordinary-turnover labels,
official-disclosure links, excluded future evidence, sources, and limitations.

### One concept I can now explain

An export should reuse the evidence already verified on the page. It should not
silently fetch different data or ask an LLM to recreate financial facts.

### Why this design fits the current deployment

The browser can open the file offline and print it to PDF. The Render service
does not need a PDF-generation package, persistent file storage, or a second
copy of the market data, so the feature adds little memory pressure.

## 2026-07-30 — Rule-based historical anomaly analogs

### What I built or changed

Added a historical-analog layer to the Market Anomaly Agent. A selected event
can now be compared with strictly earlier anomaly candidates using signal
overlap, daily return, volume multiple, and ordinary-turnover percentile.

### One concept I can now explain

Similarity is not prediction. It can help select a disciplined comparison
date, but the later outcome must remain hidden until Historical Lens reveals
it through a separate point-in-time workflow.

### How missing data is handled

Missing dimensions are excluded and the remaining weights are renormalised.
The program does not silently convert missing turnover or volume evidence to
zero. Very weak matches are rejected instead of being presented as useful
analogs.

### Why this design fits the current deployment

The comparison reuses the bounded market-event list already in memory. It
does not call a paid API, download a second dataset, or create persistent
files on the Render server.

## 2026-07-30 — Historical analogs in the offline report

### What I built or changed

Extended the downloadable anomaly report so it also preserves up to three
strictly earlier historical analogs, their rule scores, shared signals,
comparable-dimension counts, and a Historical Lens replay entry.

### One concept I can now explain

A useful export should preserve the reasoning trail, not just the final
numbers. The reader can see why two anomaly dates were considered similar and
then choose whether to conduct a separate point-in-time replay.

### How future leakage is prevented

The report receives only the analog fields already computed on the page. It
does not request later prices or embed subsequent returns, and it states this
boundary beside the comparison results.

### Why this design fits the current deployment

The extra section is plain self-contained HTML. It adds no paid API call,
server-side PDF dependency, persistent file storage, or second market-data
request.

## 2026-07-30 — Historical Lens deep links

### What I built or changed

Each analog in the downloadable anomaly report now has a dedicated replay
link carrying its six-digit company code and historical date. Historical Lens
validates the parameters and applies them only on the first page load.

### One concept I can now explain

A deep link stores the minimum page state needed to reproduce a view. Here it
removes repeated company and date selection without changing the underlying
research calculation.

### How safety and user control are preserved

The page accepts only a six-digit code and an ISO date inside its five-year
window. The same link is consumed once, so later Streamlit reruns do not reset
the date after the user changes it.

### Why this design fits the current deployment

The feature uses a short URL and deterministic validation. It requires no paid
API, database, persistent Render storage, or extra market-data request.

## 2026-07-30 — Bounded watchlist market radar

### What I built or changed

Added a dedicated page that accepts up to five A-share codes, retrieves each
company's latest public daily history on demand, and compares limit-up
candidacy, volume expansion, and ordinary-turnover historical position.

### One concept I can now explain

A market radar does not need to predict prices. It can rank the strength and
completeness of observable anomaly evidence so the user knows what to research
next.

### How missing data and failures are handled

Each company is isolated: one failed source does not cancel the others.
Missing volume or turnover evidence stays unavailable instead of becoming
zero. The ranking uses triggered-signal count and visible deterministic
tie-breakers, not an opaque AI score.

### Why this design fits the current deployment

The scan is user-triggered and limited to five companies. Only compact results
remain in the session; the product does not preload or permanently store a
full-market dataset, and it needs no paid API.

## 2026-07-30 — Daily limit-up board

### What I built or changed

Added a dedicated page that retrieves one recent Eastmoney public limit-up
pool on demand and displays limit-up count, first-board and consecutive-board
counts, maximum streak, amount, ordinary turnover, seal time, break count,
seal funds, and industry concentration.

### One concept I can now explain

A useful market wall can organise already-published trading facts without
predicting tomorrow's price. Deterministic ranking tells the user what evidence
was prioritised and makes the research order reproducible.

### How data quality is handled

Codes, percentages, non-negative amounts, board counts, and seal times are
validated independently. Missing values remain unavailable. Ordinary turnover
is explicitly kept separate from effective turnover because a verified
point-in-time investable free-float denominator is not available in the free
source.

### Why this design fits the current deployment

The page makes one bounded pool request only after the user chooses a date. A
ten-minute cache holds at most two dates, the interface shows at most thirty
table rows, and no full-market history or persistent Render file is created.
