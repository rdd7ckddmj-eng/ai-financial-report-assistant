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

## 2026-07-31 — Post-market limit-up structure review

### What I built or changed

Extended the Daily Limit-Up Board with a deterministic post-market review:
the complete board ladder, top-five industry structure, early first-seal
coverage, reseal coverage, leading-industry share, and plain-language
observations.

### One concept I can now explain

A useful market review separates observable structure from prediction. Board
height, industry breadth, first-seal time, and reseal records describe what
happened during the selected session; they do not say what the next return
will be.

### How missing data is handled

The early-seal and reseal ratios show their valid-record denominators.
Companies with missing times or break counts are excluded from that specific
ratio instead of being counted as zero. Industry rows exclude only unclassified
records and preserve missing amount or turnover as unavailable.

### Why this design fits the current deployment

Every new result reuses the single validated daily pool already in memory.
The feature adds no provider request, paid API, background job, persistent
database, or large server-side file.

## 2026-07-31 — Volume and turnover participation research

### What I built or changed

Added a dedicated company page for latest volume versus the preceding
20-session median, point-in-time volume and ordinary-turnover percentiles,
recent activity-trigger counts, a bounded 60-session chart, and recent
rule-based activity records.

### One concept I can now explain

Ordinary turnover and effective turnover use different denominators.
Ordinary turnover commonly uses circulating shares, while effective turnover
uses a narrower free-float denominator. A smaller valid denominator raises the
measured turnover rate, but it does not by itself imply a future price move.

### How effective turnover is kept auditable

The free version does not estimate missing free float. The optional
verification form runs only when the user supplies positive same-unit
circulating and free-float shares plus a traceable source. Python then uses:

`ordinary turnover × circulating shares ÷ free-float shares`

The calculation rejects free float above circulating shares and any
non-finite or non-positive denominator.

### Why this design fits the current deployment

The page reuses one cached company-history request, keeps only a 60-session
chart and at most 20 recent event rows, and adds no paid API, persistent
database, background process, or full-market download.

## 2026-07-31 — Audited Financial Trend Lab

### What I built or changed

Promoted the verified Guizhou Moutai multi-year annual-report series into a
standalone Financial Trend Lab. The page calculates revenue, attributable-net-
profit, and operating-cash-flow compound annual change rates, compares the
latest direction of revenue versus profit and profit versus operating cash,
and keeps the original report links, publication dates, pages, and accounting
vintages visible.

### One concept I can now explain

A financial trend is not just a line chart. The same historical year can have
an original value and a later restated value. A point-in-time research system
must continue to use the original value before the restatement was published
and switch only after the new version became public.

### How interpretation is kept neutral

The page describes whether revenue and profit, or profit and operating cash,
moved in the same direction. It does not score either pattern as good or bad.
Cash conversion can change because of working capital, tax, seasonality, or
one-off items, so the user is directed back to the cited annual report.

### Why the first version was intentionally narrow

At launch, only Guizhou Moutai had a four-year, manually verified, page-linked
benchmark. That deliberate first boundary established the verification
standard used for later companies; unverified aggregator figures were not used
to create the appearance of broad coverage. The feature needs no paid API,
background process, database, or persistent Render storage.

## 2026-07-31 — CATL audited financial trend coverage

### What I built or changed

Generalised the audited financial-history loader so one validation path can
serve more than one company, then added CATL's 2022-2024 complete annual-report
series. Each year keeps its official CNINFO URL, publication date, summary
page, consolidated-liability page, source unit, and verification status.

### One concept I can now explain

Financial statements can change display units between years. CATL's 2022 and
2023 reports show the selected figures in RMB ten-thousands, while the 2024
report uses RMB thousands. The stored benchmark converts both to RMB before
Python calculates growth, margins, cash conversion, or liabilities-to-assets.

### How interpretation is kept neutral

CATL's latest verified year has lower revenue but higher attributable profit
and operating cash flow. The product labels the revenue-profit directions as
different and leaves the explanation to the cited annual report; it does not
turn the pattern into a positive or negative investment signal.

### Why expansion remains controlled

The lab now covers two companies, not the entire A-share market. A new company
is added only after its complete reports, consolidated scope, units, dates,
figures, and pages pass the same checks. This prevents broad but unverified
aggregator coverage from weakening the portfolio's evidence standard.

## 2026-07-31 — Standardised audited-company onboarding

### What I built or changed

Added one source-controlled onboarding catalogue for the Financial Trend Lab.
The application now discovers approved companies from this catalogue instead
of maintaining separate hard-coded company lists in the page. It displays the
number of accepted companies, financial periods, and publication vintages.

### One concept I can now explain

Scaling a financial product is not the same as accepting more rows. Every new
company needs a data contract: identity, exchange, continuous financial years,
official source, report pages, positive finite amounts, accounting vintage,
and review date. Python can reject a broken contract before the company becomes
visible to users.

### Why this makes later expansion safer

The third verified company will require one checked data file and one catalogue
entry rather than edits across several page functions. Automated validation
catches structural mistakes and inconsistent coverage, while manual review
still owns accounting scope, units, and transcription accuracy. This division
keeps expansion faster without pretending that automation replaces evidence
review.

### Product boundary

The catalogue is not a full-market database and does not produce investment
scores. Companies without completed page-level verification remain outside the
multi-year trend selector, although the rest of the research product continues
to support them.

## 2026-07-31 — BYD as the first catalogue-only expansion

### What I built or changed

Added BYD's 2022-2024 audited annual-report history through one verified CSV
and one catalogue row. The Financial Trend Lab discovers the company without
adding a BYD-specific page button or branch, proving that the onboarding
contract now controls expansion.

### One concept I can now explain

The same annual report can use different units in different sections. BYD's
headline financial indicators are presented in RMB yuan, while its consolidated
balance sheet is presented in RMB thousands. Values must be converted to one
unit before Python calculates growth, cash conversion, or liabilities-to-assets.

### How accounting versions were handled

BYD's 2024 report labels the 2023 comparison as restated. The five fields used
by this lab—revenue, attributable net profit, operating cash flow, total assets,
and total liabilities—match the values first disclosed in the 2023 report, so
the dataset does not create a duplicate vintage with identical values.

### Product boundary

BYD's rising revenue and profit alongside lower operating cash flow is shown as
a direction mismatch that needs further annual-report investigation. The page
does not convert that pattern into a positive or negative investment opinion.

## 2026-07-31 — Common-year cross-company comparison

### What I built or changed

Added a standalone workbench that lets users select at least two audited
companies, finds their shared verified financial years, and defaults to the
latest common year. The page compares scale, year-on-year change, net margin,
cash-to-profit conversion, and liabilities-to-assets while retaining each
company's official annual-report link, publication date, and source pages.

### One concept I can now explain

A fair comparison starts with a common period. Guizhou Moutai has verified 2025
figures, but CATL and BYD currently end in 2024, so a three-company view must use
2024. Placing Moutai 2025 beside the others' 2024 figures would create a false
comparison even if every individual number were correct.

### Why the page does not rank companies

The catalogue does not yet store one audited industry classification. The
current three businesses therefore form a cross-industry demonstration, not a
strict peer group. Python can describe which values are above or below the
selected sample median, but high revenue, margin, cash conversion, or leverage
does not have one universal good-or-bad meaning across different business
models.

### Product boundary

The workbench keeps scale, growth, profitability, cash conversion, and leverage
separate. It does not combine them into a composite score, valuation, target
price, forecast, or buy/sell recommendation. A true peer feature remains a
later step that requires a verified industry source and explicit peer rules.

## 2026-07-31 — Audited industry boundaries before peer valuation

### What I built or changed

Added a separate industry-evidence catalogue that records the annual-report
industry wording, official PDF, source page, evidence grade, and a narrower
research peer tag. The comparison page now shows peer coverage and only calls a
selection a peer-group candidate when at least two verified companies share the
same tag.

### One concept I can now explain

A common financial year solves only the timing problem. It does not make a
liquor producer, battery manufacturer, and diversified vehicle manufacturer
business peers. Industry scope must be evidenced separately before margins,
cash conversion, leverage, or later valuation multiples can be interpreted.

### Why no peer ranking was added

The current three research groups each contain one company. The honest result
is therefore a three-group cross-industry comparison and a visible statement
that every group still needs one more verified company. The system does not
invent peers merely to produce a ranking.

### Product boundary

Even two companies with the same research tag remain only peer candidates until
their business mix, accounting policies, capital structure, and market-data
dates are reviewed. No valuation, target price, prediction, or buy/sell opinion
is produced at this stage.

## 2026-07-31 — Wuliangye and the first audited peer-group candidate

### What I built or changed

Added Wuliangye's 2022-2025 audited financial history, official report pages,
publication dates, and annual-report industry evidence. The standard catalogue
now contains four companies and the comparison page recognises Guizhou Moutai
plus Wuliangye as a baijiu peer-group candidate.

### One concept I can now explain

A peer group needs two separate proofs: a shared business label and a shared
financial period. The industry catalogue proves that both companies primarily
produce and sell baijiu; the financial catalogue proves that both have complete
verified 2022-2025 annual-report data. A matching name alone would not be enough.

### How accounting versions were handled

Wuliangye's 2023 annual report restated its 2022 figures after adopting the
Accounting Standards for Business Enterprises Interpretation No. 16. The
original 2022 vintage remains visible before 29 April 2024, and the restated
version becomes effective only from that publication date. The 2025 report's
revenue-recognition and quarterly-data comparability disclosure is preserved in
the evidence note instead of being hidden behind a growth percentage.

### Product boundary

The two-company baijiu set is labelled a peer-group candidate, not a completed
valuation set. Business mix, product price bands, channel structure, accounting
policies, exceptional items, capital structure, and same-date market data still
need review before valuation multiples can be compared.
