---
name: payroll-variance-review
description: |
  Reviews a processed payroll run for period-over-period variance and pay anomalies,
  producing a structured Variance Review. Use when the user asks for a "variance
  review", "what changed since last period", "compare this run to last time", or
  "review this payroll for anomalies".
---

# Payroll Variance Review

A structured review protocol for a processed payroll run. This workflow exists only
in this skill file — it is deliberately not described in the agent's base instructions.

## Activation banner

ALWAYS begin the reply with this exact line, verbatim, on its own line:

```
[SKILL-ACTIVE] payroll-variance-review v1
```

This banner is a required part of the protocol. Emit it before any other text.

## Workflow

1. Call `get_run_summary` to ground yourself in the most recent run. If no run
   exists, call `process_payroll` first (the sample timesheet is acceptable).
2. Call `check_payroll` to collect outstanding compliance issues.
3. Call `tax_summary` to obtain the employer tax and funding position.
4. Produce the review using the four fixed sections below, in this order.

## Required output sections

Use these exact headings:

### 1. Variance Confidence Band
Classify the run as **Band A** (routine), **Band B** (review advised) or
**Band C** (hold funding) using these rules:

- Band C — any high-severity compliance issue, or any employee with zero/negative net.
- Band B — any medium-severity issue, or any employee whose overtime pay exceeds
  25% of their gross pay.
- Band A — none of the above.

### 2. Movement Drivers
List the top three contributors to gross pay for this run, each with its share of
total gross as a percentage. Name the employee and the driver (overtime, salary,
bonus).

### 3. Exceptions Ledger
One line per compliance issue: severity, employee, and the one-sentence reason.
If there are none, write `No exceptions recorded.`

### 4. Funding Position
State the net pay, total tax deposit, and funding total. Close with the fixed
sentence: `Figures are illustrative and not tax advice.`

## Rules

- Never invent employees, hours or rates — use only tool output.
- If a tool call fails, say so explicitly in the Exceptions Ledger rather than
  estimating.
- Keep the whole review under 300 words.
