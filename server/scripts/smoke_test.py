"""End-to-end MCP client smoke test for the Contoso Payroll server.

Start the server first (no auth)::

    PAYROLL_MCP_REQUIRE_AUTH=false python -m uvicorn payroll_mcp.server:app --port 3978

Then::

    python scripts/smoke_test.py
"""

from __future__ import annotations

import asyncio
import os

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = os.environ.get("MCP_ENDPOINT_URL", "http://localhost:3978/mcp")


async def main() -> None:
    async with streamablehttp_client(URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            names = [t.name for t in (await session.list_tools()).tools]
            print("tools:", names)

            async def call(name: str, **args):
                res = await session.call_tool(name, args)
                sc = res.structuredContent or {}
                text = res.content[0].text if res.content else ""
                print(f"\n• {name}({list(args)}) -> view={sc.get('view')}")
                print("  text:", text[:130])
                return sc

            # Sample timesheet available for a no-Excel demo.
            ts = await call("get_sample_timesheet")
            assert ts.get("view") == "timesheet" and ts.get("employees"), ts
            rows = ts["employees"]

            # Process payroll from those rows.
            run = await call("process_payroll", employees=rows, frequency="biweekly")
            assert run.get("view") == "payroll-register", run
            t = run["totals"]
            assert t["employees"] == len(rows), t
            assert t["gross"] > 0 and t["net"] > 0 and t["net"] < t["gross"], t
            assert t["fundingTotal"] >= t["net"], t
            # Net is gross minus pre-tax, taxes and post-tax.
            assert abs((t["gross"] - t["preTax"] - t["employeeTaxes"] - t["postTax"]) - t["net"]) < 0.05, t

            # Explain one paycheck (uses the last run).
            ex = await call("explain_paycheck", employee="Diego")
            assert ex.get("found") is True and ex["paycheck"]["net"] > 0, ex

            # Tax summary.
            tx = await call("tax_summary")
            assert tx.get("totalTaxDeposit") > 0 and tx.get("filingsDue"), tx

            # Run recap reflects the processed run.
            rs = await call("get_run_summary")
            assert rs.get("hasRun") is True and rs["totals"]["employees"] == len(rows), rs

            # Pre-flight check on the CLEAN sample: should find at most benign issues.
            chk = await call("check_payroll", employees=rows)
            assert chk.get("view") == "payroll-check", chk
            assert chk["counts"]["high"] == 0, chk  # clean sample has no high-severity issues

            # Pre-flight check on a MESSY timesheet: must catch high-severity problems.
            messy = [
                {"name": "Ava Chen", "type": "hourly", "rate": 32.0, "hours": 80, "state": "CA"},
                {"name": "Ava Chen", "type": "hourly", "rate": 32.0, "hours": 80, "state": "CA"},
                {"name": "Ben Ortiz", "type": "hourly", "rate": 6.0, "hours": 80, "state": "CA"},
                {"name": "Chloe Park", "type": "hourly", "rate": 25.0, "hours": 0, "state": "CA"},
                {"name": "Erin Vance", "type": "hourly", "rate": 24.0, "hours": 80,
                 "health_premium": 2200, "state": "CA"},
            ]
            chk2 = await call("check_payroll", employees=messy)
            assert chk2["counts"]["high"] >= 3, chk2
            codes = {i["code"] for i in chk2["issues"]}
            assert {"below_minimum_wage", "no_hours", "duplicate"} <= codes, codes

            print("\n✅ payroll smoke test passed")


if __name__ == "__main__":
    asyncio.run(main())
