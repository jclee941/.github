package main

import (
	"flag"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	repoinventory "github.com/jclee941/jclee-bot/scripts/internal/repos"
)

var (
	defaultReviewRepos = strings.Join(repoinventory.Names(repoinventory.ProtectedRepos()), ",")
	repos              = flag.String("repos", defaultReviewRepos, "Comma-separated repo names (no owner)")
	dryRun             = flag.Bool("dry-run", false, "If true, no issues are created/commented")
	sinceCommits       = flag.Int("since-commits", 50, "Commits back from HEAD to use as review base")
	diffSizeLimit      = flag.Int("diff-size-limit", 150000, "Max diff char count before skipping a repo")
	model              = flag.String("model", "minimax-m3", "Primary LLM model")
	workDir            = flag.String("work-dir", "/tmp/repo-review", "Working directory for clones")
	owner              = flag.String("owner", "jclee941", "GitHub owner/org")
	printDefaultRepos  = flag.Bool("print-default-repos", false, "print default repo list and exit")
	normalizeReposOnly = flag.Bool("normalize-repos", false, "validate --repos against protected inventory, print normalized repo list, and exit")
)

func main() {
	flag.Parse()
	if *printDefaultRepos {
		fmt.Println(defaultReviewRepos)
		return
	}
	repoList, err := normalizeReviewRepos(*repos)
	if err != nil {
		fmt.Fprintf(os.Stderr, "::error::invalid repos: %v\n", err)
		os.Exit(64)
	}
	if *normalizeReposOnly {
		fmt.Println(strings.Join(repoList, ","))
		return
	}

	timestamp := time.Now().UTC().Format(time.RFC3339)
	date := time.Now().UTC().Format("2006-01-02")

	// --- prereq checks ---
	githubToken := os.Getenv("GITHUB_TOKEN")
	if githubToken == "" {
		githubToken = os.Getenv("GH_TOKEN")
	}
	if githubToken == "" {
		fmt.Fprintln(os.Stderr, "::error::GITHUB_TOKEN/GH_TOKEN not set")
		os.Exit(65)
	}
	_ = os.Setenv("GH_TOKEN", githubToken)

	if _, err := exec.LookPath("gh"); err != nil {
		fmt.Fprintln(os.Stderr, "::error::gh CLI not on PATH")
		os.Exit(66)
	}

	prAgentPython := os.Getenv("PR_AGENT_PYTHON")
	if prAgentPython == "" || !isExecutable(prAgentPython) {
		candidates := []string{
			filepath.Join(".", ".venv", "bin", "python"),
			filepath.Join(".", "pr-agent-src", ".venv", "bin", "python"),
			"/tmp/pr-agent-venv/bin/python",
		}
		found := false
		for _, c := range candidates {
			if isExecutable(c) {
				prAgentPython = c
				found = true
				break
			}
		}
		if !found {
			fmt.Fprintln(os.Stderr, "::error::pr-agent python venv not found; set PR_AGENT_PYTHON")
			os.Exit(67)
		}
	}
	_ = os.Setenv("PR_AGENT_PYTHON", prAgentPython)

	_ = os.MkdirAll(*workDir, 0755)

	fmt.Printf("repo-review batch starting at %s\n", timestamp)
	fmt.Printf("  repos=%s\n", *repos)
	fmt.Printf("  dry_run=%t\n", *dryRun)
	fmt.Printf("  since_commits=%d\n", *sinceCommits)
	fmt.Printf("  diff_size_limit=%d\n", *diffSizeLimit)
	fmt.Printf("  model=%s\n", *model)
	fmt.Printf("  python=%s\n", prAgentPython)
	fmt.Println()

	failed := 0
	for _, repo := range repoList {
		if err := reviewOneRepo(repo, timestamp, date, prAgentPython); err != nil {
			fmt.Fprintf(os.Stderr, "  ::warning::review failed for %s: %v\n", repo, err)
			failed++
		}
	}

	fmt.Println()
	fmt.Printf("repo-review batch finished. failures=%d\n", failed)
}

func reviewOneRepo(repo, timestamp, date, prAgentPython string) error {
	repoDir := filepath.Join(*workDir, repo)
	fmt.Printf("=== %s ===\n", repo)

	// Step 1: detect default branch
	defaultBranch := "master"
	out, err := runCmd("gh", "repo", "view", fmt.Sprintf("%s/%s", *owner, repo),
		"--json", "defaultBranchRef", "--jq", ".defaultBranchRef.name")
	if err == nil && strings.TrimSpace(out) != "" {
		defaultBranch = strings.TrimSpace(out)
	}
	fmt.Printf("  default_branch=%s\n", defaultBranch)

	// Step 2: clone fresh (always wipe old to keep idempotent)
	_ = os.RemoveAll(repoDir)
	if err := cloneReviewRepo(repo, repoDir); err != nil {
		fmt.Fprintf(os.Stderr, "  ::warning::clone failed for %s; skipping\n", repo)
		return err
	}
	_, _ = runCmd("git", "-C", repoDir, "config", "user.email", "bot@jclee.me")
	_, _ = runCmd("git", "-C", repoDir, "config", "user.name", "jclee-bot")

	// Step 3: run review via pr-agent
	reviewPath := filepath.Join(repoDir, "review.md")
	_ = os.Remove(reviewPath)

	repoReviewPy := resolveReviewScript()

	rc := 0
	if err := runPythonWithPrefix(prAgentPython, repoReviewPy, repoDir, reviewPath); err != nil {
		rc = 1
		fmt.Fprintf(os.Stderr, "  ::warning::pr-agent exited rc=%d for %s\n", rc, repo)
	}

	reviewFailed := 0
	reviewContent := ""
	info, err := os.Stat(reviewPath)
	if err != nil || info.Size() == 0 {
		fmt.Fprintf(os.Stderr, "  ::warning::no review.md produced for %s; filing warning issue\n", repo)
		reviewFailed = 1
		reviewContent = fmt.Sprintf(
			"## Bot Review: failed\n\n"+
				"The repo-review batch could not produce a review for this repository.\n\n"+
				"- **Workflow:** repo-review-batch.yml\n"+
				"- **Executed at:** %s\n"+
				"- **pr-agent exit code:** %d\n\n"+
				"Inspect the workflow run log for details.\n",
			timestamp, rc,
		)
	} else {
		content, _ := os.ReadFile(reviewPath)
		reviewContent = string(content)
		firstLine := ""
		if idx := strings.Index(reviewContent, "\n"); idx != -1 {
			firstLine = reviewContent[:idx]
		} else {
			firstLine = reviewContent
		}
		if strings.Contains(firstLine, "Bot Review: skipped") || strings.Contains(firstLine, "Bot Review: failed") {
			fmt.Fprintf(os.Stderr, "  ::warning::review.md is a stub for %s\n", repo)
			reviewFailed = 1
		}
	}

	// Step 4: ensure labels exist
	if !*dryRun {
		ensureLabels(repo)
	}

	// Step 5: dedupe — find any open bot-review issue
	existing := ""
	out, _ = runCmd("gh", "issue", "list", "--repo", fmt.Sprintf("%s/%s", *owner, repo),
		"--state", "open", "--label", "bot-review",
		"--json", "number,title",
		"--jq", `.[] | select(.title | startswith("[bot-review]")) | .number`)
	existing = strings.TrimSpace(out)

	title := fmt.Sprintf("[bot-review] %s HEAD review (%s)", defaultBranch, date)
	if *dryRun {
		if existing != "" {
			fmt.Printf("  DRY-RUN: would comment on existing issue #%s\n", existing)
		} else {
			fmt.Printf("  DRY-RUN: would create new issue: %s\n", title)
		}
		preview := reviewContent
		if len(preview) > 500 {
			preview = preview[:500]
		}
		fmt.Println("  DRY-RUN: review.md preview (first 500 chars):")
		for _, line := range strings.Split(preview, "\n") {
			fmt.Printf("    %s\n", line)
		}
		fmt.Println()
		return nil
	}

	// Step 6: file or update issue
	repoFull := fmt.Sprintf("%s/%s", *owner, repo)
	if existing != "" {
		tmpFile := filepath.Join(*workDir, fmt.Sprintf("comment-%s.md", repo))
		_ = os.WriteFile(tmpFile, []byte(reviewContent), 0644)
		_, err := runCmd("gh", "issue", "comment", existing, "--repo", repoFull, "--body-file", tmpFile)
		if err == nil {
			fmt.Printf("  appended comment to existing issue #%s\n", existing)
		} else {
			fmt.Fprintf(os.Stderr, "  ::warning::failed to comment on issue #%s for %s\n", existing, repo)
		}
		_ = os.Remove(tmpFile)
	} else {
		tmpFile := filepath.Join(*workDir, fmt.Sprintf("issue-%s.md", repo))
		_ = os.WriteFile(tmpFile, []byte(reviewContent), 0644)
		_, err := runCmd("gh", "issue", "create", "--repo", repoFull,
			"--title", title,
			"--body-file", tmpFile,
			"--label", "bot-review,automated")
		if err == nil {
			newNum, _ := runCmd("gh", "issue", "list", "--repo", repoFull,
				"--state", "open", "--label", "bot-review", "--limit", "1", "--json", "number", "--jq", ".[0].number")
			fmt.Printf("  created new issue #%s\n", strings.TrimSpace(newNum))
		} else {
			fmt.Fprintf(os.Stderr, "  ::warning::failed to create issue for %s\n", repo)
		}
		_ = os.Remove(tmpFile)
	}

	if reviewFailed == 1 {
		return fmt.Errorf("review failed")
	}
	return nil
}

func cloneReviewRepo(repo, repoDir string) error {
	_, err := runCmd("gh", cloneReviewRepoArgs(*owner, repo, repoDir)...)
	return err
}

func cloneReviewRepoArgs(ownerName, repo, repoDir string) []string {
	return []string{"repo", "clone", fmt.Sprintf("%s/%s", ownerName, repo), repoDir, "--", "--depth", "200"}
}

func ensureLabels(repo string) {
	repoFull := fmt.Sprintf("%s/%s", *owner, repo)
	// Best-effort: ignore errors (labels may already exist)
	_, _ = runCmd("gh", "label", "create", "bot-review", "--repo", repoFull,
		"--color", "5319E7", "--description", "Automated whole-repo code review")
	_, _ = runCmd("gh", "label", "create", "automated", "--repo", repoFull,
		"--color", "BFD4F2", "--description", "Auto-managed by jclee-bot")
}
