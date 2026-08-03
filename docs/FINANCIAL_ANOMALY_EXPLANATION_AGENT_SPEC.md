# Financial Anomaly Explanation Agent

## Objective

Turn a verified financial-direction mismatch into an auditable research task.
The first controlled case is Midea Group's 2025 pattern: revenue and
attributable net profit increased while operating cash flow decreased.

The feature does not ask an LLM to invent a narrative. Python identifies the
signal, reconciles the cash-flow bridge, ranks the year-on-year contribution of
each annual-report adjustment, and keeps unsupported business explanations in
a separate verification list.

## Evidence contract

- Trend values come from the publication-aware verified financial-history
  catalogue.
- Bridge values come from Midea Group's 2025 annual report, cash-flow statement
  supplementary information, page 233.
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

## Confirmed finding and unresolved cause

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

## Product boundary

The page is a research-explanation and audit tool. It does not predict future
cash flow, score the company, estimate value, or issue buy, sell, or hold advice.
The portable HTML report reuses only verified local evidence and makes no new
network request.
