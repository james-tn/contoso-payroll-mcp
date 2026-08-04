#!/usr/bin/env bash
# Build the Microsoft 365 Copilot sideload package (ContosoPayroll.zip) by
# substituting ${{...}} env tokens into the appPackage manifest files.
#
# Tokens (from env/.env.<env>):
#   ${{TEAMS_APP_ID}}          - Teams app GUID
#   ${{APP_NAME_SUFFIX}}       - name suffix (e.g. "dev"; emptied for prod)
#   ${{MCP_ENDPOINT_URL}}      - public https URL of the MCP server (+ /mcp)
#   ${{OAUTH_REGISTRATION_ID}} - Teams Dev Portal OAuth client registration id
#
# Auth: OAUTH_REGISTRATION_ID empty -> auth forced to {"type":"None"}; set -> OAuthPluginVault.
#
# Usage:
#   ./scripts/build_package.sh            # uses env/.env.dev
#   APP_ENV=prod ./scripts/build_package.sh
set -euo pipefail

cd "$(dirname "$0")/.."

APP_ENV="${APP_ENV:-dev}"
ENV_FILE="env/.env.${APP_ENV}"
[ -f "$ENV_FILE" ] || { echo "ERROR: $ENV_FILE not found" >&2; exit 1; }

_OAUTH_OVERRIDE="${OAUTH_REGISTRATION_ID:-}"
set -a; . "$ENV_FILE"; set +a
[ -n "$_OAUTH_OVERRIDE" ] && OAUTH_REGISTRATION_ID="$_OAUTH_OVERRIDE"
: "${APP_NAME_SUFFIX:=}"
: "${OAUTH_REGISTRATION_ID:=}"
[ -n "${TEAMS_APP_ID:-}" ]     || { echo "ERROR: TEAMS_APP_ID not set in $ENV_FILE" >&2; exit 1; }
[ -n "${MCP_ENDPOINT_URL:-}" ] || { echo "ERROR: MCP_ENDPOINT_URL not set in $ENV_FILE" >&2; exit 1; }

OUT_DIR="appPackage/build"
PKG_DIR="$OUT_DIR/pkg"
rm -rf "$OUT_DIR"
mkdir -p "$PKG_DIR"

for f in manifest.json declarativeAgent.json ai-plugin.json instruction.txt; do
  sed -e "s#\${{TEAMS_APP_ID}}#${TEAMS_APP_ID}#g" \
      -e "s#\${{APP_NAME_SUFFIX}}#${APP_NAME_SUFFIX}#g" \
      -e "s#\${{MCP_ENDPOINT_URL}}#${MCP_ENDPOINT_URL}#g" \
      -e "s#\${{OAUTH_REGISTRATION_ID}}#${OAUTH_REGISTRATION_ID}#g" \
      "appPackage/$f" > "$PKG_DIR/$f"
done

if [ -z "$OAUTH_REGISTRATION_ID" ]; then
  python3 - "$PKG_DIR/ai-plugin.json" <<'PY'
import json, sys
p = sys.argv[1]
m = json.load(open(p))
for rt in m.get("runtimes", []):
    auth = rt.get("auth") or {}
    if auth.get("type") == "OAuthPluginVault" and not (auth.get("reference_id") or "").strip():
        rt["auth"] = {"type": "None"}
json.dump(m, open(p, "w"), indent=4)
open(p, "a").write("\n")
PY
  echo "auth: None (OAUTH_REGISTRATION_ID empty)"
else
  echo "auth: OAuthPluginVault (reference_id set)"
fi

cp appPackage/color.png appPackage/outline.png "$PKG_DIR/"

# Agent Skills (preview): each entry in declarativeAgent.json `agent_skills` points at a
# folder, relative to the manifest, that must contain a SKILL.md. Copy the tree verbatim
# and zip with paths preserved. Set SKIP_SKILLS=1 to build the control package.
ZIP_ENTRIES=(manifest.json declarativeAgent.json ai-plugin.json instruction.txt color.png outline.png)
if [ -d appPackage/skills ] && [ -z "${SKIP_SKILLS:-}" ]; then
  cp -R appPackage/skills "$PKG_DIR/"
  while IFS= read -r folder; do
    [ -f "$PKG_DIR/$folder/SKILL.md" ] || { echo "ERROR: $folder/SKILL.md missing" >&2; exit 1; }
    echo "skill: $folder"
  done < <(python3 -c "
import json
m = json.load(open('$PKG_DIR/declarativeAgent.json'))
for s in m.get('agent_skills', []):
    print(s['folder'])
")
  ZIP_ENTRIES+=(skills)
else
  python3 - "$PKG_DIR/declarativeAgent.json" <<'PY'
import json, sys
p = sys.argv[1]
m = json.load(open(p))
if m.pop("agent_skills", None) is not None:
    json.dump(m, open(p, "w"), indent=4)
    open(p, "a").write("\n")
    print("skills: OMITTED (control build)")
PY
fi

if grep -rlE '\$\{\{' "$PKG_DIR"/*.json "$PKG_DIR"/*.txt 2>/dev/null; then
  echo "ERROR: unsubstituted \${{...}} tokens remain (see above)" >&2
  exit 1
fi

( cd "$PKG_DIR" && zip -r -q "../ContosoPayroll.zip" "${ZIP_ENTRIES[@]}" )

echo "PACKAGE ready: $PWD/$OUT_DIR/ContosoPayroll.zip"
