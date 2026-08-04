"""MCP tool handlers for the Contoso Payroll agent.

The agent (Copilot) reads the payroll admin's **open timesheet Excel** via its
file-context capability, maps the rows to employees, and calls these tools; the
server does the payroll math, compliance checks and summaries. Tools return
``structuredContent`` (the payroll register / issues / summary) plus a short text
recap Copilot can read aloud or render as a table.

Data-only tools (no inline widget in this version) — the register renders well as
a Copilot table; a Fluent widget is a straightforward next step.
"""

from __future__ import annotations

from collections import OrderedDict
import json
import time
from typing import Any

from mcp import types

from . import data, engine
from .security_context import current_principal
from .settings import get_settings

settings = get_settings()

# Bounded, principal-scoped demo state. Use a durable encrypted store with TTL for
# production workloads that must survive restarts or run across multiple replicas.
_runs: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()


def _get_state() -> dict[str, Any]:
    principal = current_principal()
    item = _runs.get(principal)
    if not item:
        return {}
    created_at, state = item
    if time.time() - created_at > settings.run_state_ttl_seconds:
        _runs.pop(principal, None)
        return {}
    _runs.move_to_end(principal)
    return state


def _save_state(state: dict[str, Any]) -> None:
    principal = current_principal()
    _runs[principal] = (time.time(), state)
    _runs.move_to_end(principal)
    while len(_runs) > settings.max_run_states:
        _runs.popitem(last=False)


def _dbg(tool: str, **fields: Any) -> None:
    """Log argument shapes; raw values require an explicit debug setting."""
    if settings.debug_tool_payloads:
        try:
            payload = json.dumps(fields, default=str)
        except Exception:
            payload = repr(fields)
    else:
        payload = json.dumps({
            key: f"{type(value).__name__}[{len(value)}]" if isinstance(value, (list, dict)) else type(value).__name__
            for key, value in fields.items()
        })
    print(f"[tool-call] {tool} {payload[:4000]}", flush=True)


def _result(text: str, structured: dict[str, Any]) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)],
        structuredContent=structured,
    )


def _coerce_rows(employees: Any) -> list[dict[str, Any]]:
    """Accept a list of row dicts, a JSON string, or None → list of row dicts."""
    if isinstance(employees, str):
        try:
            employees = json.loads(employees)
        except Exception:
            return []
    if isinstance(employees, dict):
        # tolerate {"employees": [...]} or {"rows": [...]}
        employees = employees.get("employees") or employees.get("rows") or []
    if not isinstance(employees, list):
        return []
    return [r for r in employees if isinstance(r, dict)]


def _rows_or_last(employees: Any) -> list[dict[str, Any]]:
    rows = _coerce_rows(employees)
    if rows:
        return rows
    return _get_state().get("input", [])


def _money(x: float) -> str:
    return f"${x:,.2f}"


# ── Tools ──────────────────────────────────────────────────────────────────────

async def get_sample_timesheet() -> types.CallToolResult:
    """Return a realistic sample timesheet + employer, so the demo runs without a real Excel."""
    _dbg("get_sample_timesheet")
    emp = data.employer()
    rows = data.sample_timesheet()
    payload = {
        "view": "timesheet",
        "provider": data.PROVIDER_NAME,
        "employer": emp,
        "columns": ["name", "type", "rate", "hours", "overtime_hours",
                    "annual_salary", "retirement_pct", "health_premium", "garnishment", "state"],
        "employees": rows,
        "note": "Illustrative sample. In the agent, these rows come from the user's open timesheet.",
    }
    text = (f"Sample {emp['frequency']} timesheet for {emp['name']} — {len(rows)} employees "
            f"({data.PROVIDER_NAME} demo). Say 'process this payroll' to run it.")
    return _result(text, payload)


async def process_payroll(employees: Any = None, frequency: str = "",
                          period_label: str = "") -> types.CallToolResult:
    """Run payroll for the given timesheet rows → full payroll register + totals."""
    _dbg("process_payroll", employees_type=type(employees).__name__,
         employees=employees, frequency=frequency, period_label=period_label)
    rows = _coerce_rows(employees)
    if not rows:
        rows = data.sample_timesheet()  # let the demo work even with no Excel/args
        used_sample = True
    else:
        used_sample = False
    emp = data.employer()
    freq = (frequency or emp["frequency"]).strip().lower()
    run = engine.process(rows, freq)
    _save_state({
        "input": rows,
        "run": run,
        "frequency": freq,
        "periodLabel": period_label or emp["periodLabel"],
    })

    t = run["totals"]
    payload = {
        "view": "payroll-register",
        "provider": data.PROVIDER_NAME,
        "employer": emp["name"],
        "state": emp["state"],
        "frequency": run["frequency"],
        "periodLabel": period_label or emp["periodLabel"],
        "register": run["register"],
        "totals": t,
        "usedSample": used_sample,
        "disclaimer": "Illustrative payroll & tax figures for demonstration — not tax advice.",
    }
    text = (
        f"Processed {run['frequency']} payroll for {t['employees']} employees"
        + (" (using the sample timesheet)" if used_sample else "")
        + f": gross {_money(t['gross'])}, employee taxes {_money(t['employeeTaxes'])}, "
        f"net {_money(t['net'])}. Funding total {_money(t['fundingTotal'])} "
        f"(net + {_money(t['taxDeposit'])} tax deposit). Figures are illustrative."
    )
    return _result(text, payload)


async def check_payroll(employees: Any = None, frequency: str = "") -> types.CallToolResult:
    """Pre-flight anomaly & compliance check — run this before funding."""
    _dbg("check_payroll", employees_type=type(employees).__name__, employees=employees, frequency=frequency)
    rows = _rows_or_last(employees) or data.sample_timesheet()
    emp = data.employer()
    state = _get_state()
    freq = (frequency or state.get("frequency") or emp["frequency"]).strip().lower()
    result = engine.check(rows, freq)
    c = result["counts"]
    payload = {
        "view": "payroll-check",
        "provider": data.PROVIDER_NAME,
        "employer": emp["name"],
        **result,
    }
    if result["ok"]:
        text = f"Pre-flight check passed for {result['employeesChecked']} employees — no issues found."
    else:
        head = "; ".join(f"{i['employee']}: {i['message']}" for i in result["issues"][:3])
        text = (f"Found {c['high']} high, {c['medium']} medium, {c['low']} low issue(s) across "
                f"{result['employeesChecked']} employees. Top: {head}")
    return _result(text, payload)


async def explain_paycheck(employee: str = "", employees: Any = None,
                           frequency: str = "") -> types.CallToolResult:
    """Break down one employee's paycheck: gross → pre-tax → taxes → post-tax → net."""
    _dbg("explain_paycheck", employee=employee, employees=employees, frequency=frequency)
    name = (employee or "").strip()
    rows = _rows_or_last(employees)
    state = _get_state()
    run = state.get("run")
    record = None
    if run and name:
        for e in run["register"]:
            if name.lower() in e["name"].lower():
                record = e
                break
    if record is None and rows:
        emp = data.employer()
        freq = (frequency or state.get("frequency") or emp["frequency"]).strip().lower()
        for r in rows:
            rn = str(r.get("name") or r.get("employee") or "")
            if name and name.lower() in rn.lower():
                record = engine.compute_employee(r, freq)
                break
    if record is None:
        avail = ", ".join(e["name"] for e in (run["register"] if run else [])) or "none"
        return _result(
            f"I couldn't find '{name}' in the current run. Available: {avail}.",
            {"view": "paycheck-explain", "found": False, "employee": name},
        )
    tx, pt = record["taxes"], record["preTax"]
    text = (
        f"{record['name']}: gross {_money(record['gross'])} − pre-tax {_money(pt['total'])} "
        f"(401k {_money(pt['retirement'])}, health {_money(pt['health'])}) − taxes {_money(tx['total'])} "
        f"(fed {_money(tx['federal'])}, state {_money(tx['state'])}, SS {_money(tx['socialSecurity'])}, "
        f"Medicare {_money(tx['medicare'])}) − garnishment {_money(record['postTax']['total'])} "
        f"= net {_money(record['net'])}."
    )
    return _result(text, {"view": "paycheck-explain", "found": True, "paycheck": record})


async def tax_summary(employees: Any = None, frequency: str = "") -> types.CallToolResult:
    """Employer tax liability, cash to deposit, and the filings this run feeds."""
    _dbg("tax_summary", employees_type=type(employees).__name__, employees=employees, frequency=frequency)
    rows = _rows_or_last(employees) or data.sample_timesheet()
    emp = data.employer()
    state = _get_state()
    freq = (frequency or state.get("frequency") or emp["frequency"]).strip().lower()
    run = engine.process(rows, freq)
    t = run["totals"]
    payload = {
        "view": "tax-summary",
        "provider": data.PROVIDER_NAME,
        "employer": emp["name"],
        "frequency": run["frequency"],
        "employeeWithholding": t["employeeTaxes"],
        "employerTax": t["employerTax"],
        "totalTaxDeposit": t["taxDeposit"],
        "fundingTotal": t["fundingTotal"],
        "filingsDue": data.filings_due(),
        "disclaimer": "Illustrative — not tax advice.",
    }
    text = (
        f"Tax summary ({run['frequency']}): employee withholding {_money(t['employeeTaxes'])} + "
        f"employer tax {_money(t['employerTax'])} = {_money(t['taxDeposit'])} to deposit. "
        f"Total cash to fund this run: {_money(t['fundingTotal'])}. Feeds Form 941, FUTA/SUTA, W-2."
    )
    return _result(text, payload)


async def get_run_summary() -> types.CallToolResult:
    """Recap the most recently processed payroll run (data only)."""
    _dbg("get_run_summary")
    state = _get_state()
    run = state.get("run")
    emp = data.employer()
    if not run:
        return _result(
            "No payroll has been processed yet this session. Open a timesheet and say "
            "'process this payroll', or ask for the sample timesheet.",
            {"view": "run-summary", "hasRun": False, "provider": data.PROVIDER_NAME},
        )
    t = run["totals"]
    payload = {
        "view": "run-summary", "hasRun": True, "provider": data.PROVIDER_NAME,
        "employer": emp["name"], "frequency": run["frequency"],
        "periodLabel": state.get("periodLabel"), "totals": t,
        "employees": [e["name"] for e in run["register"]],
    }
    text = (f"Last run: {emp['name']} {run['frequency']} — {t['employees']} employees, "
            f"gross {_money(t['gross'])}, net {_money(t['net'])}, funding {_money(t['fundingTotal'])}.")
    return _result(text, payload)


# ── Registry consumed by server.py ──────────────────────────────────────────────

TOOL_SPECS: list[dict[str, Any]] = [
    {"name": "get_sample_timesheet", "handler": get_sample_timesheet, "ui": False,
     "description": (
         "Return a realistic sample biweekly timesheet (employees with hours, rates, salaries, 401k, "
         "health, garnishment) plus the employer, so the demo runs without a real Excel file. Use when "
         "the user has no timesheet open and wants to try it, e.g. 'show a sample timesheet', 'give me "
         "example payroll data'.")},
    {"name": "process_payroll", "handler": process_payroll, "ui": False,
     "description": (
         "Run payroll for a pay period and return the full payroll register (per employee: gross, "
         "overtime, pre-tax deductions, federal/state/Social Security/Medicare withholding, post-tax "
         "deductions, net) plus totals and the funding amount. Pass 'employees' as an array of timesheet "
         "rows read from the user's OPEN EXCEL timesheet; each row: name, type ('hourly' or 'salary'), "
         "rate, hours, overtime_hours, annual_salary, bonus, retirement_pct, health_premium, "
         "garnishment, state. Optional 'frequency' (weekly/biweekly/semimonthly/monthly) and "
         "'period_label'. If no rows are given, the sample timesheet is used. Use for 'process/run this "
         "payroll', 'run payroll from my timesheet'. Figures are illustrative, not tax advice.")},
    {"name": "check_payroll", "handler": check_payroll, "ui": False,
     "description": (
         "Pre-flight anomaly & compliance check on a timesheet BEFORE funding: flags missing hours or "
         "rates, sub-minimum-wage pay, excessive overtime/hours, zero or negative net pay, and duplicate "
         "employees, each with a severity. Pass 'employees' (same shape as process_payroll) or omit to "
         "reuse the last run's rows. Use for 'check this payroll', 'any issues before I run it', "
         "'validate the timesheet'.")},
    {"name": "explain_paycheck", "handler": explain_paycheck, "ui": False,
     "description": (
         "Explain one employee's paycheck as a gross → pre-tax → taxes → post-tax → net breakdown. Pass "
         "'employee' (a name); optionally 'employees' rows and 'frequency' (else the last run is used). "
         "Use for 'why is Maria's net so low', 'break down Diego's pay', 'explain <name>'s paycheck'.")},
    {"name": "tax_summary", "handler": tax_summary, "ui": False,
     "description": (
         "Summarize the employer tax picture for a run: employee withholding, employer-side taxes "
         "(Social Security, Medicare, FUTA, SUTA), total cash to deposit, total funding, and the filings "
         "it feeds (Form 941, FUTA/SUTA, W-2). Pass 'employees' or omit to reuse the last run. Use for "
         "'what's my tax liability', 'how much do I owe / deposit', 'what filings are due'. Illustrative.")},
    {"name": "get_run_summary", "handler": get_run_summary, "ui": False,
     "description": (
         "Recap the most recently processed payroll run (employer, frequency, employee count, gross, net, "
         "funding). Data only. Call this to stay grounded when the user refers to 'this run', 'the "
         "payroll', 'what I just processed'.")},
]

async def run_payroll_prompt() -> list[types.PromptMessage]:
    return [types.PromptMessage(
        role="user",
        content=types.TextContent(type="text", text="Process payroll from my open timesheet."),
    )]


PROMPT_SPECS: list[dict[str, Any]] = [
    {"name": "run_payroll", "handler": run_payroll_prompt,
     "description": "Process payroll from an open timesheet."},
]
