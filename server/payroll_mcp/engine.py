"""Payroll calculation engine — pure Python, zero compiled deps.

Turns a normalized list of employee timesheet rows (the kind a payroll admin keeps
in an Excel sheet) into a fully calculated **payroll register**: gross pay, pre-tax
deductions, federal/state/FICA withholding, post-tax deductions, net pay, and the
employer-side tax burden — plus a pre-flight anomaly/compliance check.

Every tax figure here is an **illustrative demo approximation**, not tax advice:
flat/simplified brackets, no YTD accumulators, current-ish rates. It is designed to
look and behave like a real payroll run for a Copilot demo, not to file taxes.
"""

from __future__ import annotations

from typing import Any

# ── Pay frequency ─────────────────────────────────────────────────────────────
PERIODS_PER_YEAR: dict[str, int] = {
    "weekly": 52,
    "biweekly": 26,
    "semimonthly": 24,
    "monthly": 12,
}
STANDARD_PERIOD_HOURS: dict[str, float] = {
    "weekly": 40.0,
    "biweekly": 80.0,
    "semimonthly": 86.67,
    "monthly": 173.33,
}

# ── FICA (illustrative current-year figures) ───────────────────────────────────
SS_RATE = 0.062
SS_WAGE_BASE = 168_600.0        # annual Social Security wage cap
MEDICARE_RATE = 0.0145
ADDL_MEDICARE_RATE = 0.009      # on annual wages over the threshold
ADDL_MEDICARE_THRESHOLD = 200_000.0

# ── Employer unemployment taxes (illustrative) ─────────────────────────────────
FUTA_RATE = 0.006
FUTA_WAGE_BASE = 7_000.0
SUTA_RATE = 0.027               # blended demo rate
SUTA_WAGE_BASE = 7_000.0

OT_MULTIPLIER = 1.5

# ── Illustrative flat state income-tax rates (demo only) ───────────────────────
STATE_TAX_RATES: dict[str, float] = {
    "CA": 0.060, "NY": 0.065, "MA": 0.050, "IL": 0.0495, "NJ": 0.056,
    "PA": 0.0307, "GA": 0.0549, "NC": 0.045, "AZ": 0.025, "CO": 0.044,
    "TX": 0.0, "WA": 0.0, "FL": 0.0, "NV": 0.0, "TN": 0.0, "WY": 0.0,
}
DEFAULT_STATE_TAX_RATE = 0.05

# ── Minimum wage (illustrative) ────────────────────────────────────────────────
FEDERAL_MIN_WAGE = 7.25
STATE_MIN_WAGE: dict[str, float] = {
    "CA": 16.00, "NY": 16.00, "WA": 16.28, "MA": 15.00, "NJ": 15.13,
    "IL": 14.00, "CO": 14.42, "AZ": 14.35,
}

# 2024 single-filer federal brackets (illustrative), (upper_bound, marginal_rate).
_FED_BRACKETS_SINGLE: list[tuple[float, float]] = [
    (11_600, 0.10),
    (47_150, 0.12),
    (100_525, 0.22),
    (191_950, 0.24),
    (243_725, 0.32),
    (609_350, 0.35),
    (float("inf"), 0.37),
]
_STANDARD_DEDUCTION_SINGLE = 14_600.0


def _round(x: float) -> float:
    return round(float(x) + 1e-9, 2)


def federal_income_tax_annual(annual_taxable: float) -> float:
    """Progressive federal income tax on annualized taxable wages (illustrative)."""
    taxable = max(0.0, annual_taxable - _STANDARD_DEDUCTION_SINGLE)
    tax = 0.0
    lower = 0.0
    for upper, rate in _FED_BRACKETS_SINGLE:
        if taxable <= lower:
            break
        band = min(taxable, upper) - lower
        if band > 0:
            tax += band * rate
        lower = upper
    return max(0.0, tax)


def _f(row: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    """First present numeric field among ``keys`` (tolerant of strings/blanks)."""
    for k in keys:
        if k in row and row[k] not in (None, ""):
            try:
                return float(row[k])
            except (TypeError, ValueError):
                continue
    return default


def _worker_type(row: dict[str, Any]) -> str:
    t = str(row.get("type") or row.get("worker_type") or "").strip().lower()
    if t in ("salary", "salaried", "exempt"):
        return "salary"
    if t in ("hourly", "non-exempt", "nonexempt"):
        return "hourly"
    # Infer: an annual salary present and no hourly rate → salary.
    if _f(row, "annual_salary", "salary") > 0 and _f(row, "rate", "hourly_rate") <= 0:
        return "salary"
    return "hourly"


def compute_employee(row: dict[str, Any], frequency: str) -> dict[str, Any]:
    """Compute one employee's paycheck for a single pay period."""
    periods = PERIODS_PER_YEAR.get(frequency, 26)
    name = str(row.get("name") or row.get("employee") or "Unknown").strip() or "Unknown"
    state = str(row.get("state") or "").strip().upper()
    wtype = _worker_type(row)

    rate = _f(row, "rate", "hourly_rate", "pay_rate")
    hours = _f(row, "hours", "regular_hours", "reg_hours")
    ot_hours = _f(row, "overtime_hours", "ot_hours", "ot")
    annual_salary = _f(row, "annual_salary", "salary")
    bonus = _f(row, "bonus", "commission")

    if wtype == "salary":
        base = (annual_salary / periods) if annual_salary else 0.0
        regular_pay = _round(base)
        ot_pay = 0.0
    else:
        regular_pay = _round(hours * rate)
        ot_pay = _round(ot_hours * rate * OT_MULTIPLIER)

    gross = _round(regular_pay + ot_pay + bonus)

    # Pre-tax deductions.
    retirement_pct = _f(row, "retirement_pct", "k401_pct", "four01k_pct")
    retirement = _round(gross * retirement_pct / 100.0)
    health = _f(row, "health_premium", "health", "medical")
    pretax = _round(retirement + health)

    taxable_period = max(0.0, gross - pretax)
    annual_taxable = taxable_period * periods

    # Employee withholding.
    fed = _round(federal_income_tax_annual(annual_taxable) / periods)
    state_rate = STATE_TAX_RATES.get(state, DEFAULT_STATE_TAX_RATE)
    state_tax = _round(taxable_period * state_rate)
    ss = _round(gross * SS_RATE)
    medicare = _round(gross * MEDICARE_RATE)
    ee_taxes = _round(fed + state_tax + ss + medicare)

    # Post-tax deductions.
    garnishment = _f(row, "garnishment", "garnishments")
    posttax = _round(garnishment)

    net = _round(gross - pretax - ee_taxes - posttax)

    # Employer-side burden.
    er_ss = _round(gross * SS_RATE)
    er_medicare = _round(gross * MEDICARE_RATE)
    er_futa = _round(gross * FUTA_RATE)      # ignores YTD wage base (illustrative)
    er_suta = _round(gross * SUTA_RATE)
    employer_tax = _round(er_ss + er_medicare + er_futa + er_suta)
    employer_cost = _round(gross + employer_tax)

    return {
        "name": name,
        "type": wtype,
        "state": state or "—",
        "regularPay": regular_pay,
        "overtimePay": ot_pay,
        "bonus": _round(bonus),
        "gross": gross,
        "preTax": {"retirement": retirement, "health": health, "total": pretax},
        "taxes": {
            "federal": fed,
            "state": state_tax,
            "socialSecurity": ss,
            "medicare": medicare,
            "total": ee_taxes,
        },
        "postTax": {"garnishment": posttax, "total": posttax},
        "net": net,
        "employer": {
            "socialSecurity": er_ss,
            "medicare": er_medicare,
            "futa": er_futa,
            "suta": er_suta,
            "tax": employer_tax,
            "totalCost": employer_cost,
        },
        "hours": _round(hours),
        "overtimeHours": _round(ot_hours),
        "rate": _round(rate),
    }


def process(employees: list[dict[str, Any]], frequency: str = "biweekly") -> dict[str, Any]:
    """Run payroll for a list of timesheet rows → register + totals."""
    freq = (frequency or "biweekly").strip().lower()
    if freq not in PERIODS_PER_YEAR:
        freq = "biweekly"
    register = [compute_employee(r, freq) for r in employees if _has_content(r)]

    def s(path: list[str]) -> float:
        total = 0.0
        for e in register:
            node: Any = e
            for p in path:
                node = node.get(p, 0) if isinstance(node, dict) else 0
            total += float(node or 0)
        return _round(total)

    totals = {
        "employees": len(register),
        "gross": s(["gross"]),
        "preTax": s(["preTax", "total"]),
        "employeeTaxes": s(["taxes", "total"]),
        "postTax": s(["postTax", "total"]),
        "net": s(["net"]),
        "employerTax": s(["employer", "tax"]),
        "employerCost": s(["employer", "totalCost"]),
    }
    # Cash the employer must move: net pay to employees + all taxes (EE withheld + ER).
    totals["taxDeposit"] = _round(totals["employeeTaxes"] + totals["employerTax"])
    totals["fundingTotal"] = _round(totals["net"] + totals["taxDeposit"])

    return {"frequency": freq, "periodsPerYear": PERIODS_PER_YEAR[freq],
            "register": register, "totals": totals}


def _has_content(row: dict[str, Any]) -> bool:
    if not isinstance(row, dict):
        return False
    name = str(row.get("name") or row.get("employee") or "").strip()
    return bool(name)


# ── Pre-flight anomaly / compliance checks ─────────────────────────────────────

def check(employees: list[dict[str, Any]], frequency: str = "biweekly") -> dict[str, Any]:
    """Pre-run validation: flag likely errors and compliance risks before funding."""
    freq = (frequency or "biweekly").strip().lower()
    issues: list[dict[str, Any]] = []
    seen: dict[str, int] = {}

    def add(sev: str, name: str, code: str, message: str) -> None:
        issues.append({"severity": sev, "employee": name, "code": code, "message": message})

    for r in employees:
        if not _has_content(r):
            continue
        name = str(r.get("name") or r.get("employee")).strip()
        seen[name] = seen.get(name, 0) + 1
        wtype = _worker_type(r)
        rate = _f(r, "rate", "hourly_rate", "pay_rate")
        hours = _f(r, "hours", "regular_hours", "reg_hours")
        ot = _f(r, "overtime_hours", "ot_hours", "ot")
        state = str(r.get("state") or "").strip().upper()

        if wtype == "hourly":
            if rate <= 0:
                add("high", name, "missing_rate", "Hourly worker has no pay rate.")
            if hours <= 0 and ot <= 0:
                add("high", name, "no_hours", "Hourly worker has zero hours this period.")
            min_wage = STATE_MIN_WAGE.get(state, FEDERAL_MIN_WAGE)
            if 0 < rate < min_wage:
                add("high", name, "below_minimum_wage",
                    f"Rate ${rate:.2f} is below the {state or 'federal'} minimum wage ${min_wage:.2f}.")
            std = STANDARD_PERIOD_HOURS.get(freq, 80.0)
            if hours > std * 1.25:
                add("medium", name, "high_hours",
                    f"{hours:.0f} regular hours exceeds a normal {freq} period (~{std:.0f}).")
            if ot > 20:
                add("medium", name, "high_overtime", f"{ot:.0f} overtime hours is unusually high.")
        else:  # salary
            if _f(r, "annual_salary", "salary") <= 0:
                add("high", name, "missing_salary", "Salaried worker has no annual salary.")

        comp = compute_employee(r, freq)
        if comp["net"] <= 0 and comp["gross"] > 0:
            add("high", name, "negative_net",
                "Deductions and taxes exceed gross pay — net is zero or negative.")
        if comp["gross"] <= 0:
            add("medium", name, "zero_gross", "Gross pay computes to zero.")

    for name, n in seen.items():
        if n > 1:
            add("high", name, "duplicate", f"Appears {n} times in the timesheet — possible double pay.")

    order = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda i: order.get(i["severity"], 3))
    counts = {
        "high": sum(1 for i in issues if i["severity"] == "high"),
        "medium": sum(1 for i in issues if i["severity"] == "medium"),
        "low": sum(1 for i in issues if i["severity"] == "low"),
    }
    return {"issues": issues, "counts": counts, "ok": len(issues) == 0,
            "employeesChecked": sum(1 for r in employees if _has_content(r))}
