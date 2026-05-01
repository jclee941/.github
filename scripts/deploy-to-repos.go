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
	prTitle    = "chore: add standard automation workflows"
	prBody     = "## Summary\n- add standardized automation workflows from github-bot\n- includes PR checks, issue management, and docs sync\n- targets the self-hosted homelab runner configuration"
	branchName = "chore/add-pr-review-bot-workflow"
)

var defaultRepos = []string{
	"resume",
	"safetywallet",
	"tmux",
	"hycu_fsds",
	"splunk",
	"blacklist",
	"opencode",
	"terraform",
	".github",
}

var workflowFiles = []string{}

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
	for _, wf := range workflowFiles {
		src := filepath.Join(rootDir, wf)
		dst := filepath.Join(workDir, wf)
		if err := copyWorkflow(r, src, dst); err != nil {
			return fmt.Errorf("copy workflow %s for %s: %w", wf, repo, err)
		}
		fileChanged, err := hasFileDiff(r, workDir, wf)
		if err != nil {
			return fmt.Errorf("check diff for %s in %s: %w", wf, repo, err)
		}
		if fileChanged {
			changed = true
		}
	}

	if !changed {
		fmt.Fprintf(r.out, "[%s] all workflows already match source; skipping PR creation\n", repo)
		return nil
	}

	for _, wf := range workflowFiles {
		if err := runLogged(r, workDir, "git", "add", wf); err != nil {
			return fmt.Errorf("git add %s for %s: %w", wf, repo, err)
		}
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
	if err := runLogged(r, workDir, "gh", "auth", "setup-git"); err != nil {
		return fmt.Errorf("gh auth setup-git for %s: %w", repo, err)
	}
	if err := runLogged(r, workDir, "git", "push", "-u", "origin", branchName); err != nil {
		return fmt.Errorf("git push for %s: %w", repo, err)
	}
	if err := runLogged(r, workDir, "gh", "pr", "create", "--base", baseBranch, "--head", branchName, "--title", prTitle, "--body", prBody); err != nil {
		return fmt.Errorf("gh pr create for %s: %w", repo, err)
	}

	return nil
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
