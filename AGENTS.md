# Codex project instructions

## User profile
The project owner is a Finance and Investment postgraduate who is learning Python from zero.
Explain changes in plain Chinese and avoid assuming prior software-engineering knowledge.

## Project goal
Build a portfolio-quality AI financial-report assistant for graduate recruitment in AI + Finance roles.

## Working rules
- Make one small, reviewable change at a time.
- Before editing, explain the objective and files involved.
- Do not replace working code with a large framework without a clear reason.
- Prefer simple Python and explicit functions over unnecessary abstraction.
- Add comments for financial logic and non-obvious code.
- Separate deterministic calculations from LLM-generated explanations.
- Financial numbers and ratios must be calculated in Python.
- Report answers must preserve document/page provenance where possible.
- Do not generate investment recommendations.
- Do not use private banking data or personal customer information.
- Never store secrets in source code. Use environment variables and `.env`.
- After each change, run relevant tests and explain the result.
- When an error occurs, explain the cause, the fix, and what the user should learn from it.

## Definition of done for a task
A task is complete only when:
1. the code runs;
2. relevant tests pass;
3. the user can explain the main logic;
4. README or task notes are updated where needed.
