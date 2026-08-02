# Comprehensive Research Agent 1.0

## Product purpose

The Comprehensive Research Agent turns the existing company-research modules
into one bounded workflow. A user selects one mainland listed company and runs
one research task. The product then checks five independent evidence lanes:

1. listed-company identity;
2. validated market history and latest-session activity;
3. official disclosures;
4. the latest complete annual report;
5. manually verified multi-year financial history, when available.

The output is an auditable research brief, not a valuation, price forecast, or
investment recommendation.

## Radar-triggered entry

The bounded Watchlist Market Radar can open this page with a lightweight
session-only research context. The context explains the queue priority,
triggered market signals, task reasons, market date, and latest validated
official-disclosure clue for the same company.

Navigation alone never starts external requests. The user must explicitly run
the Comprehensive Research Agent. That run independently refreshes its five
evidence lanes and does not treat the radar context as a verified conclusion.
A context whose company code does not match the currently selected company is
not displayed. Opening a new radar-triggered task also clears any previously
rendered brief while retaining the bounded one-hour source cache.

## Deterministic boundary

- Python calculates every price return, volume multiple, percentile,
  volatility, drawdown, margin, cash-conversion ratio, and leverage ratio.
- The coordinator only organises existing results. It does not fetch data and
  does not call an LLM.
- Missing values remain unavailable. They are never replaced by zero, copied
  from another company, or completed from an AI guess.
- A failure in one evidence lane does not erase results from other lanes.
- Only official disclosure URLs that pass the existing domain allow-list can
  appear as evidence links.

## Evidence coverage

Each lane has one of three states:

- `verified`: the expected source and calculation are available;
- `partial`: some useful evidence is available, but the lane is incomplete;
- `unavailable`: the run could not obtain the required source.

For interface display, verified contributes 1 point, partial contributes 0.5,
and unavailable contributes 0. The total is divided by five and shown as an
evidence coverage ratio.

This ratio measures how much evidence the current run obtained. It is not a
company-quality score, confidence probability, expected-return score, or
investment ranking.

## Research observations

The first version may display:

- latest close, 20-session return, annualised historical volatility, and
  maximum drawdown;
- latest daily return, volume versus the preceding 20-session median, ordinary
  turnover percentile, and a board-rule-based limit-up candidate;
- the newest validated official disclosure;
- the latest complete official annual-report entry;
- the latest page-linked financial snapshot for companies already present in
  the verified financial-history catalogue.

Every observation retains its calculation basis or official source. Ordinary
turnover remains separate from effective turnover.

## Agent trace

The interface records six steps:

1. Identity Agent;
2. Market Evidence Agent;
3. Disclosure Agent;
4. Report Agent;
5. Financial Audit Agent;
6. Research Coordinator.

Each step exposes its task, status, and output summary. The final coordinator
does not rewrite failed steps as successful.

## Export

The page can export a self-contained Chinese HTML brief. The export includes:

- company identity and generation date;
- the matching Market Radar trigger context, when the workflow started from a
  radar candidate, including queue priority, dates, signals, task reasons, and
  the validated latest-disclosure clue;
- five evidence-lane states;
- deterministic observations and their bases;
- next verification tasks;
- the complete Agent trace;
- source links and explicit limitations.

Dynamic company and source text is HTML-escaped. The export can be opened
offline or printed to PDF without a server-side document dependency.
Untrusted radar disclosure URLs are omitted, and context for another company
is never written into the report. The trigger section is explicitly separated
from evidence coverage and deterministic findings.

## Free-server boundary

One run makes bounded, cached requests for a single company. It does not
pre-download the full market, persist annual-report PDFs, or store a user's
research history. User accounts and persistent watchlists remain a later
database-backed phase.

The identity fast path resolves a valid six-digit code or a verified flagship
name locally before considering the full live company directory. Market and
official-disclosure requests run concurrently because neither depends on the
other, and their combined result is cached for one hour. Each lane still keeps
its own error state, so a speed optimisation cannot turn a failed source into
verified evidence.
