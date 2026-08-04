# Project brief

## Problem
Chinese listed-company information is scattered across official announcements,
annual reports, and market-data pages. Annual reports are long, repetitive,
and difficult to analyse quickly, while generic AI answers can hide weak
sources or invent financial figures.

## User outcome
Starting from one company name or stock code, the user receives a structured
first-pass research workpaper rather than a buy/sell answer. It connects the
available public evidence, shows deterministic calculations, identifies
questions that need deeper investigation, and preserves sources, report pages,
and known evidence gaps for review, comparison, and later reuse.

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

Its advantage is workflow trust rather than database scale: official evidence
is preferred, Python owns the numbers, AI is limited to evidence-grounded
explanation and challenge, point-in-time research excludes future information,
and failed sources remain visible instead of being guessed away.

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
