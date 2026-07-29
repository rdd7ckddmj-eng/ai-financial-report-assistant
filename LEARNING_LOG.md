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
