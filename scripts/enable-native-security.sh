#!/usr/bin/env bash
#
# enable-native-security.sh — enable GitHub-native security features across the
# jclee941 fleet, replacing the removed per-repo CI workflows (06_codeql,
# 07_dependency-review, 08_scorecard) with platform features that need no
# per-repo workflow files.
#
# Enables, per repo (from config/repos.yaml):
#   - CodeQL "default setup" (code scanning)            [replaces 06_codeql.yml]
#   - Secret scanning + push protection                 [supplements jclee-bot/secret-scan]
#   - Dependabot security updates + vulnerability alerts [replaces 07_dependency-review]
#
# The jclee-bot GitHub App provides the required merge-gate checks
# (jclee-bot / pr-metadata, jclee-bot / secret-scan). This script covers the
# platform-owned security features that the App cannot run itself.
#
# Idempotent. Requires a token with admin on the repos (the repo PAT has it).
#
# Usage:
#   ./enable-native-security.sh            # dry-run (prints the gh api calls)
#   ./enable-native-security.sh --apply    # apply
#   ./enable-native-security.sh --apply --repos="account,bug"   # subset

set -euo pipefail

APPLY="false"
ONLY_REPOS=""
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPOS_YAML="$ROOT/config/repos.yaml"
OWNER="jclee941"

while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY="true"; shift ;;
    --repos) ONLY_REPOS="$2"; shift 2 ;;
    --repos=*) ONLY_REPOS="${1#--repos=}"; shift ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

run() {
  if [ "$APPLY" = "true" ]; then
    echo "+ $*"
    "$@" || echo "::warning:: command failed (continuing): $*"
  else
    echo "[dry-run] $*"
  fi
}

# Parse repo names from config/repos.yaml (the canonical inventory). pr-agent is
# an upstream fork (excluded); .github is the source repo (still gets native
# security). Honor --repos filter if provided.
mapfile -t REPOS < <(
  python3 - "$REPOS_YAML" "$ONLY_REPOS" <<'PY'
import sys, yaml
path, only = sys.argv[1], sys.argv[2]
allow = {r.strip() for r in only.split(",") if r.strip()} if only else None
doc = yaml.safe_load(open(path))
for r in doc.get("repositories", []):
    name = r["name"]
    if name == "pr-agent":   # upstream fork — do not manage
        continue
    if allow is not None and name not in allow:
        continue
    print(name)
PY
)

echo "=== GitHub-native security enablement ==="
echo "  owner: $OWNER"
echo "  repos: ${REPOS[*]}"
echo "  mode:  $([ "$APPLY" = true ] && echo APPLY || echo DRY-RUN)"
echo

for repo in "${REPOS[@]}"; do
  full="$OWNER/$repo"
  echo "--- $full ---"

  # 1. Vulnerability alerts (Dependabot alerts) — PUT returns 204.
  run gh api -X PUT "repos/$full/vulnerability-alerts" --silent

  # 2. Dependabot security updates (auto-PRs for vulnerable deps).
  run gh api -X PUT "repos/$full/automated-security-fixes" --silent

  # 3. Secret scanning + push protection (security_and_analysis).
  run gh api -X PATCH "repos/$full" \
    -F 'security_and_analysis[secret_scanning][status]=enabled' \
    -F 'security_and_analysis[secret_scanning_push_protection][status]=enabled' \
    --silent

  # 4. CodeQL default setup (code scanning) — replaces 06_codeql.yml.
  run gh api -X PUT "repos/$full/code-scanning/default-setup" \
    -F 'state=configured' -F 'query_suite=default' --silent
done

echo
echo "Done. The jclee-bot App provides the required merge-gate checks"
echo "(jclee-bot / pr-metadata, jclee-bot / secret-scan); this script covers the"
echo "GitHub-native security features that replace the removed per-repo workflows."
