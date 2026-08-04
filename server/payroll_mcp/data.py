"""In-memory demo data for the Contoso Payroll MCP demo.

Contoso Payroll is a *fictional* payroll-processing ISV (think of the category, not
any real brand). A customer tenant ("Contoso Ltd") installs the agent; a payroll
admin runs pay periods from a timesheet they keep in Excel. These fixtures let the
demo run end-to-end without a live Excel file, and back the smoke test.
"""

from __future__ import annotations

from typing import Any

# The ISV (who ships the agent) and the customer (who installs & runs payroll).
PROVIDER_NAME = "Contoso Payroll"
CUSTOMER = {
    "name": "Contoso Ltd",
    "state": "CA",
    "frequency": "biweekly",
    "payDate": "2026-07-17",
    "periodLabel": "Jun 29 – Jul 12, 2026",
}


def employer() -> dict[str, Any]:
    return dict(CUSTOMER)


def sample_timesheet() -> list[dict[str, Any]]:
    """A clean, valid biweekly timesheet (one row flags a benign high-OT heads-up)."""
    return [
        {"name": "Ava Chen", "type": "hourly", "rate": 32.0, "hours": 80, "overtime_hours": 4,
         "retirement_pct": 5, "state": "CA"},
        {"name": "Marcus Bell", "type": "hourly", "rate": 22.50, "hours": 80, "overtime_hours": 12,
         "health_premium": 85, "state": "CA"},
        {"name": "Priya Nair", "type": "salary", "annual_salary": 145000, "retirement_pct": 6,
         "health_premium": 120, "state": "CA"},
        {"name": "Diego Santos", "type": "hourly", "rate": 18.0, "hours": 80, "overtime_hours": 22,
         "garnishment": 150, "state": "CA"},
        {"name": "Sarah Kim", "type": "salary", "annual_salary": 98000, "retirement_pct": 4,
         "state": "CA"},
        {"name": "Tom Rivera", "type": "hourly", "rate": 28.0, "hours": 76, "overtime_hours": 0,
         "state": "CA"},
    ]


def messy_timesheet() -> list[dict[str, Any]]:
    """A deliberately problematic timesheet for the pre-flight anomaly-check demo."""
    return [
        {"name": "Ava Chen", "type": "hourly", "rate": 32.0, "hours": 80, "overtime_hours": 4, "state": "CA"},
        {"name": "Ava Chen", "type": "hourly", "rate": 32.0, "hours": 80, "state": "CA"},  # duplicate
        {"name": "Ben Ortiz", "type": "hourly", "rate": 6.0, "hours": 80, "state": "CA"},   # below min wage
        {"name": "Chloe Park", "type": "hourly", "rate": 25.0, "hours": 0, "state": "CA"},  # no hours
        {"name": "Dan Wu", "type": "hourly", "rate": 20.0, "hours": 80, "overtime_hours": 30, "state": "CA"},  # high OT
        {"name": "Erin Vance", "type": "hourly", "rate": 24.0, "hours": 80, "health_premium": 2200, "state": "CA"},  # negative net
    ]


def filings_due() -> list[dict[str, str]]:
    """Illustrative payroll tax filings a US employer tracks (not tax advice)."""
    return [
        {"form": "Form 941", "what": "Quarterly federal income + FICA withholding", "cadence": "Quarterly"},
        {"form": "Form 940", "what": "Annual federal unemployment (FUTA)", "cadence": "Annual"},
        {"form": "State withholding", "what": "State income tax remittance", "cadence": "Per state schedule"},
        {"form": "State UI (SUTA)", "what": "State unemployment insurance", "cadence": "Quarterly"},
        {"form": "Form W-2", "what": "Employee annual wage & tax statement", "cadence": "Annual (by Jan 31)"},
    ]
