// main_test.go — invariant tests for deploy-to-repos.go's allowlist-driven
// deployment configuration. Network-bound helpers (gh CLI calls, git push,
// PR creation) are out of scope.

package main

import (
	"os"
	"path/filepath"
	"slices"
	"sort"
	"strings"
	"testing"

	"github.com/jclee941/.github/scripts/internal/repos"
)

// allowed extensions for deployable files. Anything outside this set
// (e.g. .env, .secrets.toml, raw secrets) MUST never be deployed.
var allowedDeployExtensions = map[string]struct{}{
	".yml":  {},
	".yaml": {},
	".md":   {},
	".json": {},
	".js":   {},
	"":      {}, // CODEOWNERS has no extension
}

func TestDefaultReposIsDownstreamOnly(t *testing.T) {
	defaultRepos := repos.Names(repos.DeployableRepos())
	for _, r := range canaryRepos {
		if slices.Contains(defaultRepos, r) {
			t.Errorf("defaultRepos must NOT include canary repo %q; use --canary-repos for live e2e validation", r)
		}
	}

	for _, r := range defaultRepos {
		if r == ".github" {
			t.Errorf("defaultRepos must NOT include source repo %q (would create recursive sync PRs against itself)", r)
		}
		if r == "" {
			t.Errorf("defaultRepos contains an empty entry")
		}
	}

	const expected = 14
	if got := len(defaultRepos); got != expected {
		t.Errorf("defaultRepos has %d entries; expected %d (deployable repos from config/repos.yaml)", got, expected)
	}

	seen := make(map[string]struct{}, len(defaultRepos))
	for _, r := range defaultRepos {
		if _, dup := seen[r]; dup {
			t.Errorf("defaultRepos duplicate entry: %q", r)
		}
		seen[r] = struct{}{}
	}
}

func TestNormalizeReposAllowsExplicitCanaryOnly(t *testing.T) {
	defaultRepos := repos.Names(repos.DeployableRepos())
	repos, err := normalizeRepos("automation-e2e-public", canaryRepos)
	if err != nil {
		t.Fatalf("normalize canary repo: %v", err)
	}
	if len(repos) != 1 || repos[0] != "automation-e2e-public" {
		t.Fatalf("unexpected canary repos: %#v", repos)
	}

	if _, err := normalizeRepos("automation-e2e-public", defaultRepos); err == nil {
		t.Fatal("default repo selection must reject canary repositories")
	}
}

func TestDownstreamAllowlistContainsRequired(t *testing.T) {
	required := []string{
		".github/workflows/04_actionlint.yml",
		".github/workflows/14_bot-auto-fix.yml",
		".github/workflows/06_codeql.yml",
		".github/workflows/06_codeql.yml",
		".github/workflows/12_dependabot-auto-merge.yml",
		".github/workflows/21_docs-sync.yml",
		".github/workflows/05_gitleaks.yml",
		".github/workflows/03_pr-checks.yml",
		".github/workflows/10_pr-review.yml",
		".github/workflows/security/11_pr-review.yml",
		".github/workflows/91_issue-classification.yml",
	}

	for _, w := range required {
		if _, ok := downstreamWorkflowAllowlist[w]; !ok {
			t.Errorf("downstreamWorkflowAllowlist missing required workflow: %q", w)
		}
	}
}

func TestAllowlistExcludesForkOnly(t *testing.T) {
	forkOnly := []string{
		".github/workflows/90_sanity.yml",
	}
	for _, w := range forkOnly {
		if _, ok := downstreamWorkflowAllowlist[w]; ok {
			t.Errorf("downstreamWorkflowAllowlist must NOT contain fork-only workflow: %q", w)
		}
	}
}

func TestAllowlistEntriesPathSafety(t *testing.T) {
	for path := range downstreamWorkflowAllowlist {
		if !strings.HasPrefix(path, ".github/workflows/") {
			t.Errorf("allowlist entry %q must be under .github/workflows/", path)
		}
		if strings.Contains(path, "..") || strings.HasPrefix(path, "/") {
			t.Errorf("allowlist entry %q has unsafe path traversal", path)
		}
		if !strings.HasSuffix(path, ".yml") && !strings.HasSuffix(path, ".yaml") {
			t.Errorf("allowlist entry %q must be a .yml or .yaml file", path)
		}
	}
}

func TestExtraFilesAreSafePaths(t *testing.T) {
	if len(extraFiles) == 0 {
		t.Fatal("extraFiles must include at least dependabot.yml, CODEOWNERS, PULL_REQUEST_TEMPLATE.md")
	}

	required := map[string]struct{}{
		".github/dependabot.yml":                              {},
		".github/CODEOWNERS":                                  {},
		".github/PULL_REQUEST_TEMPLATE.md":                    {},
		".github/ISSUE_TEMPLATE/1-bug-report.yml":             {},
		".github/ISSUE_TEMPLATE/2-feature-request.yml":        {},
		".github/ISSUE_TEMPLATE/3-security-vulnerability.yml": {},
		".github/ISSUE_TEMPLATE/config.yml":                   {},
		".github/scripts/issue-classifier.js":                 {},
	}

	seen := make(map[string]struct{}, len(extraFiles))
	for _, f := range extraFiles {
		if strings.Contains(f, "..") || strings.HasPrefix(f, "/") {
			t.Errorf("extraFile %q has unsafe path traversal", f)
		}
		if !strings.HasPrefix(f, ".github/") {
			t.Errorf("extraFile %q must live under .github/ for downstream sync", f)
		}
		ext := ""
		if i := strings.LastIndex(f, "."); i > strings.LastIndex(f, "/") {
			ext = f[i:]
		}
		if _, ok := allowedDeployExtensions[ext]; !ok {
			t.Errorf("extraFile %q has unexpected extension %q", f, ext)
		}
		if _, dup := seen[f]; dup {
			t.Errorf("extraFile duplicate entry: %q", f)
		}
		seen[f] = struct{}{}
	}
	for r := range required {
		if _, ok := seen[r]; !ok {
			t.Errorf("extraFiles missing required entry: %q", r)
		}
	}
}

func TestRemovedWorkflowsNotAlsoInAllowlist(t *testing.T) {
	for _, removed := range removedWorkflows {
		if _, stillAllowed := downstreamWorkflowAllowlist[removed]; stillAllowed {
			t.Errorf("workflow %q is in BOTH removedWorkflows and downstreamWorkflowAllowlist (contradiction)", removed)
		}
	}
}

func TestAllowlistAndRemovedDisjoint(t *testing.T) {
	allowed := make([]string, 0, len(downstreamWorkflowAllowlist))
	for k := range downstreamWorkflowAllowlist {
		allowed = append(allowed, k)
	}
	sort.Strings(allowed)
	sort.Strings(removedWorkflows)

	for _, r := range removedWorkflows {
		for _, a := range allowed {
			if r == a {
				t.Errorf("workflow %q in both lists", r)
			}
		}
	}
}

func TestDependabotAutoMergeDoesNotSwallowErrors(t *testing.T) {
	workflowPath := filepath.Join("..", "..", "..", ".github", "workflows", "12_dependabot-auto-merge.yml")
	content, err := os.ReadFile(workflowPath)
	if err != nil {
		t.Fatalf("read dependabot-auto-merge workflow: %v", err)
	}

	text := string(content)
	if strings.Contains(text, "|| echo") {
		t.Fatal("12_dependabot-auto-merge.yml must not use `|| echo` error swallowing")
	}

	for _, want := range []string{
		"set -euo pipefail",
		"autoMergeRequest",
		"repos/$REPO/pulls/$PR_NUMBER/reviews",
		"dependabot-auto-merge:manual-review:major",
		"dependabot-auto-merge:manual-review:unknown-update-type",
	} {
		if !strings.Contains(text, want) {
			t.Fatalf("12_dependabot-auto-merge.yml missing expected safety pattern %q", want)
		}
	}

	// The update-branch self-heal must SURFACE genuine failures (exit 1), not
	// swallow them. Require both the explicit failure exit and the benign-case
	// guard so a real auth/5xx error fails the job.
	for _, want := range []string{
		"::error::update-branch failed",
		"exit 1",
		"HTTP 422",
	} {
		if !strings.Contains(text, want) {
			t.Fatalf("12_dependabot-auto-merge.yml must surface update-branch failures; missing %q", want)
		}
	}
}

func TestDeploymentNamingConstants(t *testing.T) {
	if branchName != "chore/sync-automation-workflows" {
		t.Errorf("branchName = %q; want %q", branchName, "chore/sync-automation-workflows")
	}
	wantTitle := "chore: sync automation workflows, dependabot, and templates"
	if prTitle != wantTitle {
		t.Errorf("prTitle = %q; want %q", prTitle, wantTitle)
	}
}
