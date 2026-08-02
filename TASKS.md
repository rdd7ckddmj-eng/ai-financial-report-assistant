# Current task board

## Now
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
- [ ] Add comparable-company valuation only after business-mix, accounting, and same-date market checks.
- [ ] Expand the 贵州茅台 flagship set from three to five events after review.
- [x] GitHub publication and public Render website.
- [ ] Complete recruitment materials.
- [ ] Complete any remaining standalone Python exercises if useful.
