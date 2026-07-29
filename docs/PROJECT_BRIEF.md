# Project brief

## Problem
Chinese listed-company information is scattered across official announcements,
annual reports, and market-data pages. Annual reports are long, repetitive,
and difficult to analyse quickly, while generic AI answers can hide weak
sources or invent financial figures.

## Target user
A retail investor, junior financial analyst, credit analyst, or finance
student who needs a traceable first-pass research workspace for a mainland
listed company.

## Product proposition
The assistant combines:
- one company-name or stock-code entry shared across focused subpages;
- public official disclosures and historical market data;
- deterministic Python calculations for financial figures and ratios;
- evidence retrieval from annual reports;
- an LLM for explanation and summarisation;
- citations and warnings to support human review.

## Non-goals
- no autonomous investment decisions;
- no prediction of short-term stock-price direction;
- no personalised financial advice;
- no use of confidential customer data;
- no claim that generated output replaces professional judgement.

## Initial success criteria
- all displayed ratios reproduce manually checked calculations;
- answers cite relevant report pages;
- the system says when evidence is insufficient;
- a new user can run the project from the README;
- the owner can explain the architecture and key code during an interview.
