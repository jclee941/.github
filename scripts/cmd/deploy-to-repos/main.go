package main

import (
	"bytes"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/jclee941/.github/scripts/internal/repos"
)

const (
	prTitle    = "chore: sync automation workflows, dependabot, and templates"
	prBody     = "## Summary\n\nSync standard automation from `jclee941/.github`:\n\n- **PR checks** (size, title, branch name, description, large files, sensitive files) - 2 enforcing + 4 advisory contexts.\n- **Auto-review** via cli_proxy on every non-draft PR (Dependabot PRs are reviewed by `12_dependabot-auto-merge.yml` instead).\n- **Dependabot auto-merge** for patch + minor + github_actions updates; majors and unknown update-types are commented for manual review.\n- **CodeQL** (Python SAST), **Gitleaks** (secret scanning), **actionlint** (workflow YAML linter).\n- **`.github/dependabot.yml`** schedules weekly `github-actions` + `pip` ecosystem updates. (`pip` will warn 'no manifest found' on non-Python repos; safe to ignore until Python is added.)\n- **`.github/CODEOWNERS`** + **`.github/PULL_REQUEST_TEMPLATE.md`** - per-repo files (org-level CODEOWNERS does NOT propagate).\n- **`.github/ISSUE_TEMPLATE/`** — standardized bug reports, feature requests, and security vulnerability templates.\n- **Issue management + docs sync** workflows — markdown lint, link check, README sync validation, API docs check.\n- **README generator** (`20_readme-gen.yml`) — auto-generates README.md via CLIProxyAPI (minimax-m2.7 → gpt-5.5 fallback).\n- **Template sync** (`template-sync.yml`) — deploys standard `README.md`, `CONTRIBUTING.md`, `LICENSE` templates.\n\nDeployed by `scripts/deploy-to-repos.go` from `jclee941/.github`. See [AGENTS.md § GIT FLOW AUTOMATION](https://github.com/jclee941/.github/blob/master/AGENTS.md#git-flow-automation) for the inventory and policy.\n\n## Rollout sequence (REQUIRED ORDER - do not skip)\n\n1. **Merge this PR** — the new workflows (`05_gitleaks.yml`, `06_codeql.yml`, `04_actionlint.yml`) start running on subsequent PRs as **advisory** checks. They are NOT yet required.\n2. **Confirm `Gitleaks / scan` is green** — open one trivial test PR (or wait for the next real PR) and verify the Gitleaks job passes. If the repo has historical leaks, `gitleaks` will fail. In that case add a `.gitleaksignore` (one fingerprint per line) or a repo-local `.gitleaks.toml` allowlist, commit it, and re-run.\n3. **Apply branch protection** — only after step 2 succeeds, run from `jclee941/.github`:\n   ```\n   go run ./scripts/cmd/branch-protection --repos=<this-repo>\n   ```\n   This registers `Gitleaks / scan` as a third required status check (alongside the two existing `pr-checks` contexts). Skipping step 2 will deadlock all subsequent PRs (including Dependabot) on a missing required check.\n"
	branchName = "chore/sync-automation-workflows"
)

// downstreamNpmEcosystem is appended to dependabot.yml ONLY when deploying to
// downstream repos. The source repo (.github) is Python-only and omits npm to
// avoid a guaranteed weekly Dependabot failure (no package.json). Dependabot
// silently skips this ecosystem in repos that have no package.json.
const downstreamNpmEcosystem = `
  # JavaScript/TypeScript dependencies (package.json + package-lock.json).
  # Injected downstream by deploy-to-repos; Dependabot skips repos without a
  # package.json, so this is safe everywhere it lands.
  - package-ecosystem: "npm"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
    labels:
      - "dependencies"
      - "javascript"
    commit-message:
      prefix: "chore"
      include: "scope"
    groups:
      npm-minor-patch:
        update-types:
          - "minor"
          - "patch"
`

// canaryRepos lists dedicated live-test repositories that may be mutated only
// when explicitly selected with --canary-repos. Keep these out of deployableRepos
// so normal deploy runs cannot create PRs in test canaries by accident.
var canaryRepos = []string{
	"automation-e2e-public",
}

var workflowFiles = []string{}

var downstreamWorkflowAllowlist = map[string]struct{}{
	".github/workflows/20_readme-gen.yml":                {},
	".github/workflows/08_scorecard.yml":                 {},
	".github/workflows/24_release-notes.yml":             {},
	".github/workflows/07_dependency-review.yml":         {},
	".github/workflows/04_actionlint.yml":                {},
	".github/workflows/01_branch-to-pr.yml":              {},
	".github/workflows/14_bot-auto-fix.yml":              {},
	".github/workflows/37_ci-failure-issues.yml":         {},
	".github/workflows/06_codeql.yml":                    {},
	".github/workflows/12_dependabot-auto-merge.yml":     {},
	".github/workflows/21_docs-sync.yml":                 {},
	".github/workflows/29_downstream-health-check.yml":   {},
	".github/workflows/05_gitleaks.yml":                  {},
	".github/workflows/19_issue-backfill.yml":            {},
	".github/workflows/18_issue-management.yml":          {},
	".github/workflows/02_issue-to-branch.yml":           {},
	".github/workflows/15_merged-pr-cleanup.yml":         {},
	".github/workflows/13_pr-auto-merge.yml":             {},
	".github/workflows/03_pr-checks.yml":                 {},
	".github/workflows/10_pr-review.yml":                 {},
	".github/workflows/09_semantic-pr.yml":               {},
	".github/workflows/25_release-publish.yml":           {},
	".github/workflows/42_reusable-docs-sync.yml":        {},
	".github/workflows/43_reusable-issue-management.yml": {},
	".github/workflows/44_reusable-pr-checks.yml":        {},
	".github/workflows/45_reusable-gitleaks.yml":         {},
	".github/workflows/60_ci-auto-heal.yml":              {},
	".github/workflows/11_security-pr-review.yml":        {},
	".github/workflows/91_issue-classification.yml":      {},
	// sanity.yml + auto-hardcode-scan + auto-deploy + release-drafter are fork-specific.
}

// extraFiles lists non-workflow files (relative to repo root) to deploy alongside workflows.
// Scope: per-repo files that GitHub does NOT inherit from the org-level .github repo.
//   - dependabot.yml: must live in each repo's .github/ directory.
//   - CODEOWNERS: must live in each repo's .github/ directory; the org-level
//     .github CODEOWNERS does NOT propagate (only community health files do).
//   - PULL_REQUEST_TEMPLATE.md: per-repo template (the org-level template
//     applies to repos that lack their own, but per-repo wins).
var extraFiles = []string{
	".github/dependabot.yml",
	".github/CODEOWNERS",
	".github/PULL_REQUEST_TEMPLATE.md",
	".github/ISSUE_TEMPLATE/1-bug-report.yml",
	".github/ISSUE_TEMPLATE/2-feature-request.yml",
	".github/ISSUE_TEMPLATE/3-security-vulnerability.yml",
	".github/ISSUE_TEMPLATE/config.yml",
	".github/renovate.json",
	".github/scripts/issue-classifier.cjs",
}

// removedWorkflows lists workflows that were previously deployed but are no longer
// in the allowlist. They will be deleted from downstream repos during deployment.
var removedWorkflows = []string{
	// Renamed to issue-classifier.cjs (CommonJS, works in type:module repos);
	// delete the stale .js so downstream ESM repos don't keep the broken copy.
	".github/scripts/issue-classifier.js",
	".github/workflows/branch-to-pr.yml",
	".github/workflows/issue-to-branch.yml",
	".github/workflows/pr-checks.yml",
	".github/workflows/actionlint.yml",
	".github/workflows/gitleaks.yml",
	".github/workflows/codeql.yml",
	".github/workflows/dependency-review.yml",
	".github/workflows/scorecard.yml",
	".github/workflows/semantic-pr.yml",
	".github/workflows/pr-review.yml",
	".github/workflows/security/pr-review.yml",
	".github/workflows/security/11_pr-review.yml", // moved to top-level 11_security-pr-review.yml (GitHub ignores subdir workflows)
	".github/workflows/dependabot-auto-merge.yml",
	".github/workflows/pr-auto-merge.yml",
	".github/workflows/bot-auto-fix.yml",
	".github/workflows/merged-pr-cleanup.yml",
	".github/workflows/stale-repo-identifier.yml",
	".github/workflows/pr-stale-bot.yml",
	".github/workflows/issue-management.yml",
	".github/workflows/issue-backfill.yml",
	".github/workflows/readme-gen.yml",
	".github/workflows/docs-sync.yml",
	".github/workflows/template-sync.yml",
	".github/workflows/release-drafter.yml",
	".github/workflows/release-notes.yml",
	".github/workflows/release-publish.yml",
	".github/workflows/elk-health-check.yml",
	".github/workflows/elk-setup.yml",
	".github/workflows/bot-health-monitor.yml",
	".github/workflows/downstream-health-check.yml",
	".github/workflows/runtime-health-check.yml",
	".github/workflows/repo-health.yml",
	".github/workflows/org-health-report.yml",
	".github/workflows/drift-detector.yml",
	".github/workflows/auto-deploy.yml",
	".github/workflows/auto-hardcode-scan.yml",
	".github/workflows/build-and-push-app.yml",
	".github/workflows/ci-failure-issues.yml",
	".github/workflows/e2e.yml",
	".github/workflows/e2e-live.yml",
	".github/workflows/repo-review-batch.yml",
	".github/workflows/reusable-ci.yml",
	".github/workflows/reusable-docs-sync.yml",
	".github/workflows/reusable-issue-management.yml",
	".github/workflows/reusable-pr-checks.yml",
	".github/workflows/_auto-merge.yml",
	".github/workflows/_issue-label.yml",
	".github/workflows/_issue-lifecycle.yml",
	".github/workflows/_labeler.yml",
	".github/workflows/_pr-normalize.yml",
	".github/workflows/_pr-review-security.yml",
	".github/workflows/_pr-size.yml",
	".github/workflows/_stale.yml",
	".github/workflows/_welcome.yml",
	".github/workflows/sanity.yml",
}

type config struct {
	dryRun     bool
	repos      []string
	baseBranch string
}

type repoResult struct {
	name     string
	status   string
	err      error
	attempts int
}

type runner struct {
	dryRun bool
	out    io.Writer
	errOut io.Writer
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}
}

func run() error {
	cfg, err := parseFlags()
	if err != nil {
		return err
	}

	rootDir, err := findRepoRoot()
	if err != nil {
		return err
	}

	workflowFiles, err = getWorkflowFiles(rootDir)
	if err != nil {
		return fmt.Errorf("list workflow files: %w", err)
	}
	if len(workflowFiles) == 0 {
		return errors.New("no workflow files found in .github/workflows/")
	}

	r := runner{dryRun: cfg.dryRun, out: os.Stdout, errOut: os.Stderr}
	results := make([]repoResult, 0, len(cfg.repos))

	for _, repo := range cfg.repos {
		result := repoResult{name: repo}

		var err error
		const maxAttempts = 3
		for attempt := 1; attempt <= maxAttempts; attempt++ {
			result.attempts = attempt
			err = deployRepo(r, rootDir, repo, cfg.baseBranch)
			if err == nil {
				break
			}
			if attempt < maxAttempts {
				delay := time.Duration(1<<(attempt-1)) * time.Second
				fmt.Fprintf(os.Stdout, "[%s] attempt %d failed: %v; retrying in %v...\n", repo, attempt, err, delay)
				time.Sleep(delay)
			}
		}

		if err != nil {
			result.status = "failed"
			result.err = err
			if !cfg.dryRun {
				if issueErr := createFailureIssue(repo, err); issueErr != nil {
					fmt.Fprintf(os.Stderr, "[%s] warning: failed to create failure issue: %v\n", repo, issueErr)
				}
			}
		} else if cfg.dryRun {
			result.status = "previewed"
		} else {
			result.status = "prepared"
		}

		results = append(results, result)
	}

	printSummary(os.Stdout, cfg.dryRun, results)

	failures := 0
	for _, result := range results {
		if result.err != nil {
			failures++
		}
	}
	if failures > 0 {
		return fmt.Errorf("%d repo(s) failed", failures)
	}

	return nil
}

func parseFlags() (config, error) {
	var cfg config
	var reposFlag string
	var canaryReposFlag string
	defaultRepos := repos.Names(repos.DeployableRepos())
	defaultReposCSV := strings.Join(defaultRepos, ",")

	flag.BoolVar(&cfg.dryRun, "dry-run", false, "preview deployment steps without making changes")
	flag.StringVar(&cfg.baseBranch, "base-branch", "", "target base branch override (auto-detected if empty)")
	flag.StringVar(&reposFlag, "repos", defaultReposCSV, "comma-separated repo names: resume,safetywallet,youtube")
	flag.StringVar(&canaryReposFlag, "canary-repos", "", "comma-separated canary repo names for live deployment-path validation; excludes production defaults")
	flag.Parse()

	if canaryReposFlag != "" && reposFlag != defaultReposCSV {
		return config{}, errors.New("--canary-repos cannot be combined with --repos")
	}

	allowedRepos := defaultRepos
	selectedRepos := reposFlag
	if canaryReposFlag != "" {
		allowedRepos = canaryRepos
		selectedRepos = canaryReposFlag
	}

	repos, err := normalizeRepos(selectedRepos, allowedRepos)
	if err != nil {
		return config{}, err
	}
	cfg.repos = repos
	return cfg, nil
}

func normalizeRepos(raw string, allowedRepoNames []string) ([]string, error) {
	allowed := make(map[string]struct{}, len(allowedRepoNames))
	for _, repo := range allowedRepoNames {
		allowed[repo] = struct{}{}
	}

	parts := strings.Split(raw, ",")
	seen := make(map[string]struct{}, len(parts))
	repos := make([]string, 0, len(parts))

	for _, part := range parts {
		repo := strings.TrimSpace(part)
		if repo == "" {
			continue
		}
		if _, ok := allowed[repo]; !ok {
			valid := append([]string(nil), allowedRepoNames...)
			sort.Strings(valid)
			return nil, fmt.Errorf("unsupported repo %q (allowed: %s)", repo, strings.Join(valid, ", "))
		}
		if _, ok := seen[repo]; ok {
			continue
		}
		seen[repo] = struct{}{}
		repos = append(repos, repo)
	}

	if len(repos) == 0 {
		return nil, errors.New("no repos selected")
	}

	return repos, nil
}

func findRepoRoot() (string, error) {
	wd, err := os.Getwd()
	if err != nil {
		return "", fmt.Errorf("get working directory: %w", err)
	}

	current := wd
	for {
		candidate := filepath.Join(current, ".github/workflows/03_pr-checks.yml")
		if _, err := os.Stat(candidate); err == nil {
			return current, nil
		}

		parent := filepath.Dir(current)
		if parent == current {
			break
		}
		current = parent
	}

	return "", fmt.Errorf("could not find repo root containing .github/workflows/03_pr-checks.yml from %s", wd)
}

func getWorkflowFiles(rootDir string) ([]string, error) {
	var files []string
	walkDir := filepath.Join(rootDir, ".github", "workflows")
	err := filepath.Walk(walkDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if !info.IsDir() && (strings.HasSuffix(path, ".yml") || strings.HasSuffix(path, ".yaml")) {
			rel, err := filepath.Rel(rootDir, path)
			if err != nil {
				return err
			}
			if _, ok := downstreamWorkflowAllowlist[rel]; !ok {
				return nil
			}
			files = append(files, rel)
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	return files, nil
}

func getDefaultBranch(repo string) (string, error) {
	fullRepo := fullRepoName(repo)
	cmd := exec.Command("gh", "api", fmt.Sprintf("repos/%s", fullRepo), "--jq", ".default_branch")
	var stdout bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	err := cmd.Run()
	if err != nil {
		if stderr.Len() > 0 {
			return "", fmt.Errorf("gh api: %s", strings.TrimSpace(stderr.String()))
		}
		return "", fmt.Errorf("gh api: %w", err)
	}

	branch := strings.TrimSpace(stdout.String())
	if branch == "" {
		return "master", nil
	}
	return branch, nil
}

func deployRepo(r runner, rootDir, repo, baseBranchOverride string) error {
	fullRepo := fullRepoName(repo)
	workDir := filepath.Join(os.TempDir(), "deploy-to-repos", repo)

	baseBranch := baseBranchOverride
	if baseBranch == "" {
		var err error
		baseBranch, err = getDefaultBranch(repo)
		if err != nil {
			return fmt.Errorf("detect default branch for %s: %w", repo, err)
		}
	}

	if !r.dryRun {
		if err := os.RemoveAll(workDir); err != nil {
			return fmt.Errorf("remove temp dir for %s: %w", repo, err)
		}
		if err := os.MkdirAll(workDir, 0o755); err != nil {
			return fmt.Errorf("create temp dir for %s: %w", repo, err)
		}
	}

	if err := runLogged(r, "", "gh", "repo", "clone", fullRepo, workDir, "--", "--branch", baseBranch, "--single-branch"); err != nil {
		return fmt.Errorf("clone %s: %w", fullRepo, err)
	}

	if err := runLogged(r, workDir, "git", "checkout", "-B", branchName, baseBranch); err != nil {
		return fmt.Errorf("create branch for %s: %w", repo, err)
	}

	changed := false
	managedFiles := append(append([]string(nil), workflowFiles...), extraFiles...)
	for _, mf := range managedFiles {
		src := filepath.Join(rootDir, mf)
		dst := filepath.Join(workDir, mf)
		if err := copyWorkflow(r, src, dst); err != nil {
			return fmt.Errorf("copy %s for %s: %w", mf, repo, err)
		}
		fileChanged, err := hasFileDiff(r, workDir, mf)
		if err != nil {
			return fmt.Errorf("check diff for %s in %s: %w", mf, repo, err)
		}
		if fileChanged {
			changed = true
		}
	}

	// Remove workflows that are no longer in the allowlist
	for _, wf := range removedWorkflows {
		dst := filepath.Join(workDir, wf)
		if _, err := os.Stat(dst); err == nil {
			if r.dryRun {
				fmt.Fprintf(r.out, "[dry-run] remove %s from %s\n", wf, repo)
			} else {
				if err := os.Remove(dst); err != nil {
					return fmt.Errorf("remove old workflow %s for %s: %w", wf, repo, err)
				}
				fmt.Fprintf(r.out, "[%s] removed old workflow %s\n", repo, wf)
			}
			changed = true
		}
	}

	if !changed {
		fmt.Fprintf(r.out, "[%s] all managed files already match source; skipping PR creation\n", repo)
		return nil
	}

	for _, mf := range managedFiles {
		if err := runLogged(r, workDir, "git", "add", mf); err != nil {
			return fmt.Errorf("git add %s for %s: %w", mf, repo, err)
		}
	}
	// Stage removal of old workflows
	for _, wf := range removedWorkflows {
		_ = runLogged(r, workDir, "git", "add", wf)
	}
	if err := runLogged(r, workDir, "git", "config", "user.email", "bot@jclee.me"); err != nil {
		return fmt.Errorf("git config user.email for %s: %w", repo, err)
	}
	if err := runLogged(r, workDir, "git", "config", "user.name", "github-bot"); err != nil {
		return fmt.Errorf("git config user.name for %s: %w", repo, err)
	}
	if err := runLogged(r, workDir, "git", "commit", "-m", prTitle); err != nil {
		return fmt.Errorf("git commit for %s: %w", repo, err)
	}
	// Configure gh as git credential helper so GH_TOKEN is used without embedding in URL
	if err := runLogged(r, workDir, "gh", "auth", "setup-git"); err != nil {
		return fmt.Errorf("gh auth setup-git for %s: %w", repo, err)
	}
	remoteURL := fmt.Sprintf("https://github.com/jclee941/%s.git", repo)
	if err := runLogged(r, workDir, "git", "remote", "set-url", "origin", remoteURL); err != nil {
		return fmt.Errorf("git remote set-url for %s: %w", repo, err)
	}
	if r.dryRun {
		if err := runLogged(r, workDir, "git", "push", "-u", "origin", branchName); err != nil {
			return fmt.Errorf("git push for %s: %w", repo, err)
		}
		return nil
	}
	pushArgs, err := pushArgsWithLease(workDir, branchName)
	if err != nil {
		return fmt.Errorf("prepare push lease for %s: %w", repo, err)
	}
	if err := runLogged(r, workDir, "git", pushArgs...); err != nil {
		return fmt.Errorf("git push for %s: %w", repo, err)
	}
	if existing, err := existingPullRequest(workDir, branchName); err != nil {
		return fmt.Errorf("check existing PR for %s: %w", repo, err)
	} else if existing != "" {
		fmt.Fprintf(r.out, "[%s] existing PR %s already tracks %s; skipping PR creation\n", repo, existing, branchName)
		// Enable auto-merge on existing PR in case it was disabled
		if err := runLogged(r, workDir, "gh", "pr", "ready", existing); err != nil {
			fmt.Fprintf(r.out, "[%s] warning: failed to mark PR %s as ready: %v\n", repo, existing, err)
		}
		if err := runLogged(r, workDir, "gh", "pr", "merge", existing, "--auto", "--squash"); err != nil {
			fmt.Fprintf(r.out, "[%s] warning: failed to enable auto-merge on existing PR %s: %v\n", repo, existing, err)
		}
		return nil
	}
	if err := runLogged(r, workDir, "gh", "pr", "create", "--base", baseBranch, "--head", branchName, "--title", prTitle, "--body", prBody); err != nil {
		return fmt.Errorf("gh pr create for %s: %w", repo, err)
	}
	// Enable auto-merge on newly created PR
	prNum, _ := existingPullRequest(workDir, branchName)
	if prNum != "" {
		if err := runLogged(r, workDir, "gh", "pr", "merge", prNum, "--auto", "--squash"); err != nil {
			fmt.Fprintf(r.out, "[%s] warning: failed to enable auto-merge on new PR %s: %v\n", repo, prNum, err)
		}
	}

	return nil
}

func pushArgsWithLease(workDir, branch string) ([]string, error) {
	args := []string{"push", "-u", "origin", branch}
	remoteSHA, err := remoteBranchSHA(workDir, branch)
	if err != nil {
		return nil, err
	}
	if remoteSHA == "" {
		return args, nil
	}
	return []string{"push", "--force-with-lease=refs/heads/" + branch + ":" + remoteSHA, "-u", "origin", branch}, nil
}

func remoteBranchSHA(workDir, branch string) (string, error) {
	cmd := exec.Command("git", "ls-remote", "--heads", "origin", branch)
	cmd.Dir = workDir
	var stdout bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		if stderr.Len() > 0 {
			return "", fmt.Errorf("git ls-remote: %s", strings.TrimSpace(stderr.String()))
		}
		return "", fmt.Errorf("git ls-remote: %w", err)
	}
	fields := strings.Fields(stdout.String())
	if len(fields) == 0 {
		return "", nil
	}
	return fields[0], nil
}

func existingPullRequest(workDir, branch string) (string, error) {
	cmd := exec.Command("gh", "pr", "list", "--head", branch, "--state", "open", "--json", "url", "--jq", ".[0].url // \"\"")
	cmd.Dir = workDir
	var stdout bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		if stderr.Len() > 0 {
			return "", fmt.Errorf("gh pr list: %s", strings.TrimSpace(stderr.String()))
		}
		return "", fmt.Errorf("gh pr list: %w", err)
	}
	return strings.TrimSpace(stdout.String()), nil
}

func copyWorkflow(r runner, src, dst string) error {
	if r.dryRun {
		fmt.Fprintf(r.out, "[dry-run] copy %s -> %s\n", src, dst)
		return nil
	}

	if err := os.MkdirAll(filepath.Dir(dst), 0o755); err != nil {
		return fmt.Errorf("create workflow directory: %w", err)
	}

	input, err := os.ReadFile(src)
	if err != nil {
		return fmt.Errorf("read source workflow: %w", err)
	}
	// Downstream repos may contain JS manifests; the source repo (.github) is
	// Python-only and intentionally omits the npm ecosystem (it would fail every
	// weekly run). Re-append npm only for downstream dependabot.yml deployments.
	if filepath.Base(dst) == "dependabot.yml" && strings.HasSuffix(filepath.Dir(dst), ".github") {
		if !strings.Contains(string(input), "package-ecosystem: \"npm\"") {
			input = append(input, []byte(downstreamNpmEcosystem)...)
		}
	}
	if err := os.WriteFile(dst, input, 0o644); err != nil {
		return fmt.Errorf("write target workflow: %w", err)
	}
	return nil
}

func hasFileDiff(r runner, workDir, filePath string) (bool, error) {
	if r.dryRun {
		fmt.Fprintf(r.out, "[dry-run] inspect diff for %s in %s\n", filePath, workDir)
		return true, nil
	}

	cmd := exec.Command("git", "status", "--short", "--", filePath)
	cmd.Dir = workDir
	var stdout bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	err := cmd.Run()
	if err != nil {
		if stderr.Len() > 0 {
			return false, fmt.Errorf("git status: %s", strings.TrimSpace(stderr.String()))
		}
		return false, fmt.Errorf("git status: %w", err)
	}

	return strings.TrimSpace(stdout.String()) != "", nil
}

func runLogged(r runner, dir, name string, args ...string) error {
	fmt.Fprintf(r.out, "%s\n", formatCommand(dir, name, args...))
	if r.dryRun {
		return nil
	}

	cmd := exec.Command(name, args...)
	if dir != "" {
		cmd.Dir = dir
	}
	output, err := cmd.CombinedOutput()
	if len(output) > 0 {
		fmt.Fprint(r.out, string(output))
	}
	if err != nil {
		return fmt.Errorf("%s: %w", formatCommand(dir, name, args...), err)
	}
	return nil
}

func formatCommand(dir, name string, args ...string) string {
	parts := make([]string, 0, len(args)+1)
	parts = append(parts, shellQuote(name))
	for _, arg := range args {
		parts = append(parts, shellQuote(arg))
	}
	command := strings.Join(parts, " ")
	if dir == "" {
		return command
	}
	return fmt.Sprintf("(cd %s && %s)", shellQuote(dir), command)
}

func shellQuote(value string) string {
	if value == "" {
		return "''"
	}
	if !strings.ContainsAny(value, " \t\n'\"\\$`!&*()[]{}|;<>?") {
		return value
	}
	return "'" + strings.ReplaceAll(value, "'", "'\"'\"'") + "'"
}

func createFailureIssue(repo string, deployErr error) error {
	title := fmt.Sprintf("[deploy-failure] %s: automation sync failed", repo)
	body := fmt.Sprintf("## Deploy Failure Report\n\n**Repository:** jclee941/%s\n\n**Error:** %s\n\n**Timestamp:** %s\n\nAll 3 retry attempts with exponential backoff have been exhausted.\n\n## Manual Recovery\n\nTo retry deployment manually, run:\n\n```bash\ncd /home/jclee/dev/.github\n(cd scripts && go run ./cmd/deploy-to-repos) --repos=%s\n```\n\nOr run with dry-run first to preview:\n\n```bash\n(cd scripts && go run ./cmd/deploy-to-repos) --repos=%s --dry-run\n```\n\n**Labels:** deploy-failure, bot",
		repo, deployErr, time.Now().Format(time.RFC3339), repo, repo)
	args := []string{"issue", "create", "--repo", "jclee941/.github", "--title", title, "--body", body, "--label", "deploy-failure", "--label", "bot"}
	cmd := exec.Command("gh", args...)
	output, err := cmd.CombinedOutput()
	if len(output) > 0 {
		fmt.Fprintf(os.Stdout, "%s", string(output))
	}
	if err != nil {
		return fmt.Errorf("gh issue create: %w", err)
	}
	return nil
}

func printSummary(w io.Writer, dryRun bool, results []repoResult) {
	mode := "apply"
	if dryRun {
		mode = "dry-run"
	}
	fmt.Fprintf(w, "\nSummary (%s):\n", mode)
	for _, result := range results {
		if result.err != nil {
			if result.attempts > 1 {
				fmt.Fprintf(w, "- %s: %s (after %d attempts) - %v\n", fullRepoName(result.name), result.status, result.attempts, result.err)
			} else {
				fmt.Fprintf(w, "- %s: %s - %v\n", fullRepoName(result.name), result.status, result.err)
			}
			continue
		}
		fmt.Fprintf(w, "- %s: %s\n", fullRepoName(result.name), result.status)
	}
}

func fullRepoName(repo string) string {
	return "jclee941/" + repo
}
