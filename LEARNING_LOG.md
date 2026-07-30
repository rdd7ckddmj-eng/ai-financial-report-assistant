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
