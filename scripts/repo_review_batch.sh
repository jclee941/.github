#!/usr/bin/env bash
# Whole-repo automated review + GitHub issue filing for every repo in
# the inventory. Each repo is cloned to a tmp dir, its master/main HEAD
# is reviewed via pr-agent's LocalGitProvider, and the review markdown
# is filed as a GitHub issue (or appended as a comment if a previous
# bot-review issue is still open).
#
# Required env:
#   GITHUB_TOKEN or GH_TOKEN   issues:write on every target repo
#   CLIPROXY_API_KEY           via OPENAI__KEY for pr-agent
#   plus the standard pr-agent settings already exported by the workflow
#
# Usage:
#   ./scripts/repo_review_batch.sh [--repos=a,b,c] [--dry-run] [--since-commits=N]
#
# Exits non-zero only on infrastructure failures; per-repo review failures
# are logged and reported as warning issues so the batch can finish.

set -euo pipefail

# --- defaults ---
DEFAULT_REPOS=".github,resume,safetywallet,tmux,hycu_fsds,splunk,blacklist,opencode,terraform,account,idle-outpost,bug"
REPOS="$DEFAULT_REPOS"
DRY_RUN="false"
SINCE_COMMITS="50"
DIFF_SIZE_LIMIT="150000"
MODEL="kimi-k2.6"
WORK_DIR="${WORK_DIR:-/tmp/repo-review}"
OWNER="jclee941"

# --- arg parsing ---
for arg in "$@"; do
	case "$arg" in
	--repos=*) REPOS="${arg#*=}" ;;
	--dry-run | --dry-run=true) DRY_RUN="true" ;;
	--dry-run=false) DRY_RUN="false" ;;
	--since-commits=*) SINCE_COMMITS="${arg#*=}" ;;
	--diff-size-limit=*) DIFF_SIZE_LIMIT="${arg#*=}" ;;
	--model=*) MODEL="${arg#*=}" ;;
	--work-dir=*) WORK_DIR="${arg#*=}" ;;
	--owner=*) OWNER="${arg#*=}" ;;
	-h | --help)
		grep '^#' "$0" | sed 's/^#//'
		exit 0
		;;
	*)
		echo "unknown arg: $arg" >&2
		exit 64
		;;
	esac
done

# --- prereq checks ---
: "${GITHUB_TOKEN:=${GH_TOKEN:-}}"
if [ -z "${GITHUB_TOKEN:-}" ]; then
	echo "::error::GITHUB_TOKEN/GH_TOKEN not set" >&2
	exit 65
fi
export GH_TOKEN="$GITHUB_TOKEN"

if ! command -v gh >/dev/null 2>&1; then
	echo "::error::gh CLI not on PATH" >&2
	exit 66
fi

if [ -z "${PR_AGENT_PYTHON:-}" ] || [ ! -x "$PR_AGENT_PYTHON" ]; then
	if [ -x "$(pwd)/.venv/bin/python" ]; then
		PR_AGENT_PYTHON="$(pwd)/.venv/bin/python"
	elif [ -x "$(pwd)/pr-agent-src/.venv/bin/python" ]; then
		PR_AGENT_PYTHON="$(pwd)/pr-agent-src/.venv/bin/python"
	elif [ -x "/tmp/pr-agent-venv/bin/python" ]; then
		PR_AGENT_PYTHON="/tmp/pr-agent-venv/bin/python"
	else
		echo "::error::pr-agent python venv not found; set PR_AGENT_PYTHON" >&2
		exit 67
	fi
fi
export PR_AGENT_PYTHON

mkdir -p "$WORK_DIR"
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
DATE=$(date -u +%Y-%m-%d)

ensure_labels() {
	local repo="$1"
	gh label create bot-review --repo "$OWNER/$repo" --color 5319E7 --description "Automated whole-repo code review" 2>/dev/null || true
	gh label create automated --repo "$OWNER/$repo" --color BFD4F2 --description "Auto-managed by jclee-bot" 2>/dev/null || true
}

review_one_repo() {
	local repo="$1"
	local repo_dir="$WORK_DIR/$repo"
	echo "=== $repo ==="

	# Step 1: detect default branch
	local default_branch
	default_branch=$(gh repo view "$OWNER/$repo" --json defaultBranchRef --jq .defaultBranchRef.name 2>/dev/null || echo "master")
	echo "  default_branch=$default_branch"

	# Step 2: clone fresh (always wipe old to keep idempotent)
	rm -rf "$repo_dir"
	if ! git clone --quiet --depth 200 \
		"https://x-access-token:${GITHUB_TOKEN}@github.com/$OWNER/$repo.git" \
		"$repo_dir" 2>&1 | tail -5; then
		echo "  ::warning::clone failed for $repo; skipping" >&2
		return 1
	fi
	git -C "$repo_dir" config user.email "bot@jclee.me"
	git -C "$repo_dir" config user.name "jclee-bot"

	# Step 3: run review via pr-agent (writes review.md inside repo dir)
	local review_path="$repo_dir/review.md"
	rm -f "$review_path"
	local rc=0
	if ! "$PR_AGENT_PYTHON" "$(dirname "$0")/repo_review.py" \
		--repo-path "$repo_dir" \
		--review-path "$review_path" \
		--since-commits "$SINCE_COMMITS" \
		--diff-size-limit "$DIFF_SIZE_LIMIT" \
		--model "$MODEL" \
		--response-language ko \
		2>&1 | sed "s/^/  [pr-agent] /"; then
		rc=$?
		echo "  ::warning::pr-agent exited rc=$rc for $repo" >&2
	fi

	local review_failed=0
	if [ ! -s "$review_path" ]; then
		echo "  ::warning::no review.md produced for $repo; filing warning issue" >&2
		review_failed=1
		cat >"$review_path" <<EOF
## Bot Review: failed

The repo-review batch could not produce a review for this repository.

- **Workflow:** repo-review-batch.yml
- **Executed at:** $TIMESTAMP
- **pr-agent exit code:** $rc

Inspect the workflow run log for details.
EOF
	elif head -1 "$review_path" | grep -qE 'Bot Review: (skipped|failed)'; then
		echo "  ::warning::review.md is a stub for $repo" >&2
		review_failed=1
	fi

	# Step 4: ensure labels exist
	if [ "$DRY_RUN" = "false" ]; then
		ensure_labels "$repo"
	fi

	# Step 5: dedupe — find any open bot-review issue
	local existing
	existing=$(gh issue list --repo "$OWNER/$repo" --state open --label bot-review \
		--json number,title --jq '.[] | select(.title | startswith("[bot-review]")) | .number' 2>/dev/null |
		head -1 || true)

	local title="[bot-review] ${default_branch} HEAD review (${DATE})"
	if [ "$DRY_RUN" = "true" ]; then
		if [ -n "$existing" ]; then
			echo "  DRY-RUN: would comment on existing issue #$existing"
		else
			echo "  DRY-RUN: would create new issue: $title"
		fi
		echo "  DRY-RUN: review.md preview (first 500 chars):"
		head -c 500 "$review_path" | sed 's/^/    /'
		echo
		return 0
	fi

	# Step 6: file or update issue
	if [ -n "$existing" ]; then
		if gh issue comment "$existing" --repo "$OWNER/$repo" --body-file "$review_path" >/dev/null 2>&1; then
			echo "  appended comment to existing issue #$existing"
		else
			echo "  ::warning::failed to comment on issue #$existing for $repo" >&2
		fi
	else
		if gh issue create --repo "$OWNER/$repo" \
			--title "$title" \
			--body-file "$review_path" \
			--label bot-review,automated >/dev/null 2>&1; then
			local new_num
			new_num=$(gh issue list --repo "$OWNER/$repo" --state open --label bot-review --limit 1 --json number --jq '.[0].number' 2>/dev/null || echo "?")
			echo "  created new issue #$new_num"
		else
			echo "  ::warning::failed to create issue for $repo" >&2
		fi
	fi

	# Return non-zero so main()'s failure counter increments when the
	# review itself failed (not when issue posting failed).
	if [ "$review_failed" = "1" ]; then
		return 1
	fi
}

main() {
	echo "repo-review batch starting at $TIMESTAMP"
	echo "  repos=$REPOS"
	echo "  dry_run=$DRY_RUN"
	echo "  since_commits=$SINCE_COMMITS"
	echo "  diff_size_limit=$DIFF_SIZE_LIMIT"
	echo "  model=$MODEL"
	echo "  python=$PR_AGENT_PYTHON"
	echo

	local failed=0
	IFS=',' read -ra REPO_LIST <<<"$REPOS"
	for repo in "${REPO_LIST[@]}"; do
		repo="$(echo "$repo" | xargs)" # trim
		[ -z "$repo" ] && continue
		if ! review_one_repo "$repo"; then
			failed=$((failed + 1))
		fi
	done

	echo
	echo "repo-review batch finished. failures=$failed"
	return 0
}

main "$@"
