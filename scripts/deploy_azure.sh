#!/usr/bin/env bash
# Deploy the reference MCP server to Azure Container Apps with authentication
# and MCP transport protections enabled.
#
# Required:
#   RG=<resource-group>
#   ACR=<registry-server>
#   ENTRA_TENANT_ID=<tenant-guid|organizations>
#   ENTRA_AUDIENCES=<client-guid,api://client-guid,application-id-uri>
#
# Optional:
#   APP=contoso-payroll-mcp
#   ENTRA_REQUIRED_SCOPE=access_as_user
#   ENTRA_ALLOWED_TENANTS=<comma-separated customer tenant GUIDs>
set -euo pipefail

: "${RG:?Set RG to the Azure resource group}"
: "${ACR:?Set ACR to the Azure Container Registry server}"
: "${ENTRA_TENANT_ID:?Set ENTRA_TENANT_ID to a tenant GUID or organizations}"
: "${ENTRA_AUDIENCES:?Set ENTRA_AUDIENCES to accepted API token audiences}"

APP="${APP:-contoso-payroll-mcp}"
ENTRA_REQUIRED_SCOPE="${ENTRA_REQUIRED_SCOPE:-access_as_user}"
ENTRA_ALLOWED_TENANTS="${ENTRA_ALLOWED_TENANTS:-}"

cd "$(dirname "$0")/../server"

echo "== Deploying $APP to $RG =="
az containerapp up \
  --name "$APP" \
  --resource-group "$RG" \
  --registry-server "$ACR" \
  --source . \
  --ingress external \
  --target-port 8000

FQDN="$(az containerapp show -g "$RG" -n "$APP" --query properties.configuration.ingress.fqdn -o tsv)"

echo "== Enabling fail-closed Entra auth and transport security =="
az containerapp update -g "$RG" -n "$APP" \
  --min-replicas 1 --max-replicas 1 \
  --set-env-vars \
    PAYROLL_MCP_REQUIRE_AUTH=true \
    PAYROLL_MCP_AUTH_MODE=entra \
    PAYROLL_MCP_ENTRA_TENANT_ID="$ENTRA_TENANT_ID" \
    PAYROLL_MCP_ENTRA_AUDIENCES="$ENTRA_AUDIENCES" \
    PAYROLL_MCP_ENTRA_REQUIRED_SCOPE="$ENTRA_REQUIRED_SCOPE" \
    PAYROLL_MCP_ENTRA_ALLOWED_TENANTS="$ENTRA_ALLOWED_TENANTS" \
    PAYROLL_MCP_TRANSPORT_SECURITY_ENABLED=true \
    PAYROLL_MCP_ALLOWED_HOSTS="$FQDN" \
    PAYROLL_MCP_DEBUG_TOOL_PAYLOADS=false \
  -o none

echo "== Deployed: https://$FQDN/mcp =="
echo "healthz: $(curl -sS -o /dev/null -w '%{http_code}' "https://$FQDN/healthz")"
echo "mcp without token (expect 401): $(curl -sS -o /dev/null -w '%{http_code}' \
  -H 'Content-Type: application/json' -X POST "https://$FQDN/mcp")"
