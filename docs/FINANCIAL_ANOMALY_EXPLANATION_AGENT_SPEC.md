# Financial Anomaly Explanation Agent

## Objective

Turn verified financial-direction mismatches into auditable research tasks.
The controlled catalogue currently covers Midea Group's 2025 pattern and
BYD's 2024 pattern: revenue and attributable net profit increased while
operating cash flow decreased in both cases.

The feature does not ask an LLM to invent a narrative. Python identifies the
signal, reconciles the cash-flow bridge, ranks the year-on-year contribution of
each annual-report adjustment, and keeps unsupported business explanations in
a separate verification list.

## Evidence contract

- Trend values come from the publication-aware verified financial-history
  catalogue.
- Midea bridge values come from its 2025 annual report, cash-flow statement
  supplementary information, page 233: 14 rows reconcile 2025 and 2024.
- BYD bridge values come from its 2024 annual report, cash-flow statement
  supplementary information, page 239: 18 rows reconcile 2024 and 2023.
- The original report unit is RMB thousand; controlled data is stored in RMB.
- Every bridge row keeps the same official HTTPS source, report, page, A-grade
  evidence status, and manual-verification status.
- The sum of all bridge rows must equal operating cash flow in both years.
- The year-on-year sum of all row changes must equal the verified change in
  operating cash flow.

## Deterministic rule

The initial signal is triggered only when all three conditions are true:

1. revenue growth is positive;
2. attributable net-profit growth is positive; and
3. operating cash-flow growth is negative.

The cash-flow reconciliation starts from consolidated net profit, as required
by the report's supplementary statement. This is not the same accounting scope
as attributable net profit used in the trend signal, so the product states the
distinction explicitly.

## Confirmed findings and unresolved causes

The strongest negative bridge contribution is the lower increase in operating
payables. Its contribution moved from RMB 50.346 billion in 2024 to RMB 11.317
billion in 2025, a year-on-year change of negative RMB 39.029 billion. Inventory,
operating receivables, and consolidated net profit provide the largest positive
offsets.

This arithmetic does not prove why operating payables changed. Supplier payment
timing, bills payable, contract liabilities, business mix, consolidation scope,
or settlement policy remain questions until the relevant notes and management
discussion are checked. The interface therefore labels them "to verify" rather
than confirmed causes.

For BYD, the largest negative bridge contribution is also the lower increase
in operating payables: the contribution fell from RMB 112.737 billion in 2023
to RMB 67.560 billion in 2024, reducing the year-on-year bridge by RMB 45.178
billion. The larger inventory increase reduces the bridge by a further RMB
23.646 billion. Fixed-asset depreciation and consolidated net profit are the
largest positive offsets. The system dynamically asks for inventory and
receivables evidence when those working-capital contributions worsen, instead
of copying Midea-specific wording.

## Product boundary

The page is a research-explanation and audit tool. It does not predict future
cash flow, score the company, estimate value, or issue buy, sell, or hold advice.
The portable HTML report reuses only verified local evidence and makes no new
network request.
