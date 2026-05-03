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
)

const (
	prTitle    = "chore: standardize automation workflows + dependabot config"
	prBody     = "## Summary\n\nSync standard automation from `jclee941/.github`:\n\n- **PR checks** (size, title, branch name, description, large files, sensitive files) - 2 enforcing + 4 advisory contexts.\n- **Auto-review** via cli_proxy on every non-draft PR (Dependabot PRs are reviewed by `dependabot-auto-merge.yml` instead).\n- **Dependabot auto-merge** for patch + minor + github_actions updates; majors and unknown update-types are commented for manual review.\n- **CodeQL** (Python SAST), **Gitleaks** (secret scanning), **actionlint** (workflow YAML linter).\n- **`.github/dependabot.yml`** schedules weekly `github-actions` + `pip` ecosystem updates. (`pip` will warn 'no manifest found' on non-Python repos; safe to ignore until Python is added.)\n- **`.github/CODEOWNERS`** + **`.github/PULL_REQUEST_TEMPLATE.md`** - per-repo files (org-level CODEOWNERS does NOT propagate).\n- **Issue management + docs sync** workflows.\n\nDeployed by `scripts/deploy-to-repos.go` from `jclee941/.github`. See [AGENTS.md § GIT FLOW AUTOMATION](https://github.com/jclee941/.github/blob/master/AGENTS.md#git-flow-automation) for the inventory and policy.\n\n## Rollout sequence (REQUIRED ORDER - do not skip)\n\n1. **Merge this PR** — the new workflows (`gitleaks.yml`, `codeql.yml`, `actionlint.yml`) start running on subsequent PRs as **advisory** checks. They are NOT yet required.\n2. **Confirm `Gitleaks / scan` is green** — open one trivial test PR (or wait for the next real PR) and verify the Gitleaks job passes. If the repo has historical leaks, `gitleaks` will fail. In that case add a `.gitleaksignore` (one fingerprint per line) or a repo-local `.gitleaks.toml` allowlist, commit it, and re-run.\n3. **Apply branch protection** — only after step 2 succeeds, run from `jclee941/.github`:\n   ```\n   go run ./scripts/cmd/branch-protection --repos=<this-repo>\n   ```\n   This registers `Gitleaks / scan` as a third required status check (alongside the two existing `pr-checks` contexts). Skipping step 2 will deadlock all subsequent PRs (including Dependabot) on a missing required check.\n"
	branchName = "chore/add-pr-review-bot-workflow"
)

// defaultRepos lists DOWNSTREAM target repos. Only public repos here —
// auto-merge is not supported on personal-account private repos under
// GitHub Free. The source repo (.github) is intentionally excluded to
// avoid recursive PRs against its own master.
var defaultRepos = []string{
	"resume",
	"safetywallet",
	"tmux",
	"hycu_fsds",
	"splunk",
	"blacklist",
	"opencode",
	"terraform",
	"account",
	"idle-outpost",
	"bug",
}

var workflowFiles = []string{}

var downstreamWorkflowAllowlist = map[string]struct{}{
	".github/workflows/actionlint.yml":                {},
	".github/workflows/codeql.yml":                   {},
	".github/workflows/dependabot-auto-merge.yml":     {},
	".github/workflows/docs-sync.yml":                 {},
	".github/workflows/gitleaks.yml":                  {},
	".github/workflows/issue-management.yml":          {},
	".github/workflows/pr-checks.yml":                 {},
	".github/workflows/pr-review.yml":                 {},
	".github/workflows/reusable-docs-sync.yml":        {},
	".github/workflows/reusable-issue-management.yml": {},
	".github/workflows/reusable-pr-checks.yml":        {},
	// sanity.yml is fork-specific (imports pr_agent); not deployed downstream.
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
}

// removedWorkflows lists workflows that were previously deployed but are no longer
// in the allowlist. They will be deleted from downstream repos during deployment.
var removedWorkflows = []string{
	".github/workflows/pr-review-security.yml",
}

type config struct {
	dryRun     bool
	repos      []string
	baseBranch string
}

type repoResult struct {
	name   string
	status string
	err    error
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

		if err := deployRepo(r, rootDir, repo, cfg.baseBranch); err != nil {
			result.status = "failed"
			result.err = err
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

	flag.BoolVar(&cfg.dryRun, "dry-run", false, "preview deployment steps without making changes")
	flag.StringVar(&cfg.baseBranch, "base-branch", "", "target base branch override (auto-detected if empty)")
	flag.StringVar(&reposFlag, "repos", strings.Join(defaultRepos, ","), "comma-separated repo names: resume,safetywallet,youtube")
	flag.Parse()

	repos, err := normalizeRepos(reposFlag)
	if err != nil {
		return config{}, err
	}
	cfg.repos = repos
	return cfg, nil
}

func normalizeRepos(raw string) ([]string, error) {
	allowed := make(map[string]struct{}, len(defaultRepos))
	for _, repo := range defaultRepos {
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
			valid := append([]string(nil), defaultRepos...)
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
		candidate := filepath.Join(current, ".github/workflows/pr-checks.yml")
		if _, err := os.Stat(candidate); err == nil {
			return current, nil
		}

		parent := filepath.Dir(current)
		if parent == current {
			break
		}
		current = parent
	}

	return "", fmt.Errorf("could not find repo root containing .github/workflows/pr-checks.yml from %s", wd)
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
	remoteURL := fmt.Sprintf("https://x-access-token:%s@github.com/jclee941/%s.git", os.Getenv("GITHUB_TOKEN"), repo)
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
		return nil
	}
	if err := runLogged(r, workDir, "gh", "pr", "create", "--base", baseBranch, "--head", branchName, "--title", prTitle, "--body", prBody); err != nil {
		return fmt.Errorf("gh pr create for %s: %w", repo, err)
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

func printSummary(w io.Writer, dryRun bool, results []repoResult) {
	mode := "apply"
	if dryRun {
		mode = "dry-run"
	}
	fmt.Fprintf(w, "\nSummary (%s):\n", mode)
	for _, result := range results {
		if result.err != nil {
			fmt.Fprintf(w, "- %s: %s - %v\n", fullRepoName(result.name), result.status, result.err)
			continue
		}
		fmt.Fprintf(w, "- %s: %s\n", fullRepoName(result.name), result.status)
	}
}

func fullRepoName(repo string) string {
	return "jclee941/" + repo
}
