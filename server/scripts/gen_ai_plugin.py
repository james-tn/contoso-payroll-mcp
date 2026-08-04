"""Generate appPackage/ai-plugin.json from the running Contoso Payroll MCP server.

Introspects the live server's tools and writes the Microsoft 365 Copilot plugin
manifest with a RemoteMCPServer runtime. The URL is left as the
``${{MCP_ENDPOINT_URL}}`` token so the packaging step substitutes the real URL.

Usage (server running on http://localhost:3978/mcp)::

    OAUTH_TEMPLATE=1 python scripts/gen_ai_plugin.py
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = "http://localhost:3978/mcp"
REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "appPackage" / "ai-plugin.json"

NAME = "Contoso Payroll${{APP_NAME_SUFFIX}}"
DESCRIPTION = (
    "Contoso Payroll for Microsoft 365 Copilot: process a pay period from your open "
    "timesheet — compute gross, taxes and deductions to net pay, run pre-flight "
    "compliance checks, and summarize employer taxes. Illustrative demo, not tax advice."
)
NAMESPACE = "contosopayroll"


async def main() -> None:
    async with streamablehttp_client(URL) as (read, write, *_):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools

    functions, tool_descriptors, run_for = [], [], []
    for t in tools:
        functions.append({"name": t.name, "description": t.description})
        run_for.append(t.name)
        tool_descriptors.append({
            "name": t.name,
            "description": t.description,
            "inputSchema": t.inputSchema,
            "annotations": {"readOnlyHint": True},
            "execution": {"taskSupport": "forbidden"},
        })

    reg_id = os.environ.get("OAUTH_REGISTRATION_ID", "").strip()
    if reg_id:
        auth_block: dict = {"type": "OAuthPluginVault", "reference_id": reg_id}
    elif os.environ.get("OAUTH_TEMPLATE", "").strip().lower() in ("1", "true", "yes"):
        auth_block = {"type": "OAuthPluginVault", "reference_id": "${{OAUTH_REGISTRATION_ID}}"}
    else:
        auth_block = {"type": "None"}

    manifest = {
        "$schema": "https://developer.microsoft.com/json-schemas/copilot/plugin/v2.4/schema.json",
        "schema_version": "v2.4",
        "name_for_human": NAME,
        "description_for_human": DESCRIPTION,
        "namespace": NAMESPACE,
        "functions": functions,
        "runtimes": [
            {
                "type": "RemoteMCPServer",
                "spec": {
                    "url": "${{MCP_ENDPOINT_URL}}",
                    "x-mcp_tool_description": {"tools": tool_descriptors},
                },
                "run_for_functions": run_for,
                "auth": auth_block,
            }
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(manifest, indent=4) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({len(functions)} functions)")


if __name__ == "__main__":
    asyncio.run(main())
