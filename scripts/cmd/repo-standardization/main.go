package main

import (
	"errors"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"

	"github.com/jclee941/jclee-bot/scripts/internal/repos"
)

const defaultWorkDir = "/tmp/repo-standardization"

func main() {
	defaultRepos := repos.Names(repos.DeployableRepos())
	reposFlag := flag.String("repos", strings.Join(defaultRepos, ","), "comma-separated downstream managed repo names")
	owner := flag.String("owner", "jclee941", "GitHub owner/org")
	workDir := flag.String("work-dir", defaultWorkDir, "working directory for cloned repos")
	localDir := flag.String("local-dir", "", "scan one local repository instead of cloning managed repos")
	dryRun := flag.Bool("dry-run", false, "preview validation without mutating repos; this command never mutates")
	printDefaultRepos := flag.Bool("print-default-repos", false, "print default downstream repo list and exit")
	normalizeReposOnly := flag.Bool("normalize-repos", false, "validate --repos against downstream inventory, print normalized repo list, and exit")
	flag.Parse()

	if *printDefaultRepos {
		fmt.Println(strings.Join(defaultRepos, ","))
		return
	}

	if *localDir != "" {
		if err := runLocalScan(*localDir); err != nil {
			fmt.Fprintf(os.Stderr, "error: %v\n", err)
			os.Exit(1)
		}
		return
	}

	repoList, err := normalizeRepoList(*reposFlag, defaultRepos)
	if err != nil {
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(64)
	}
	if *normalizeReposOnly {
		fmt.Println(strings.Join(repoList, ","))
		return
	}

	if _, err := exec.LookPath("gh"); err != nil {
		fmt.Fprintln(os.Stderr, "error: gh CLI not on PATH")
		os.Exit(66)
	}

	if err := os.MkdirAll(*workDir, 0o755); err != nil {
		fmt.Fprintf(os.Stderr, "error: create work dir: %v\n", err)
		os.Exit(1)
	}

	mode := "validate"
	if *dryRun {
		mode = "dry-run"
	}
	fmt.Printf("repo-standardization starting (%s)\n", mode)
	fmt.Printf("  repos=%s\n", strings.Join(repoList, ","))
	fmt.Println()

	failures := 0
	for _, repo := range repoList {
		if err := validateManagedRepo(*owner, repo, *workDir); err != nil {
			fmt.Fprintf(os.Stderr, "::warning::%s/%s failed standardization: %v\n", *owner, repo, err)
			failures++
			continue
		}
		fmt.Printf("- %s/%s: passed\n", *owner, repo)
	}

	fmt.Println()
	fmt.Printf("repo-standardization finished. failures=%d\n", failures)
	if failures > 0 {
		os.Exit(1)
	}
}

func runLocalScan(root string) error {
	findings, err := scanRepoDocs(root)
	if err != nil {
		return fmt.Errorf("scan local repo %s: %w", root, err)
	}
	if len(findings) > 0 {
		return fmt.Errorf("documentation standardization failed: %s", formatFindings(findings))
	}
	fmt.Printf("- %s: passed\n", root)
	return nil
}

func validateManagedRepo(owner, repo, workDir string) error {
	repoDir := filepath.Join(workDir, repo)
	if err := os.RemoveAll(repoDir); err != nil {
		return fmt.Errorf("remove previous clone: %w", err)
	}
	if err := cloneRepo(owner, repo, repoDir); err != nil {
		return fmt.Errorf("clone repo: %w", err)
	}
	findings, err := scanRepoDocs(repoDir)
	if err != nil {
		return fmt.Errorf("scan docs: %w", err)
	}
	if len(findings) > 0 {
		return fmt.Errorf("documentation standardization failed: %s", formatFindings(findings))
	}
	return nil
}

func cloneRepo(owner, repo, repoDir string) error {
	cmd := exec.Command("gh", "repo", "clone", fmt.Sprintf("%s/%s", owner, repo), repoDir, "--", "--depth", "1")
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("gh repo clone %s/%s: %w", owner, repo, err)
	}
	return nil
}

func normalizeRepoList(raw string, allowedRepoNames []string) ([]string, error) {
	allowed := make(map[string]struct{}, len(allowedRepoNames))
	for _, repo := range allowedRepoNames {
		allowed[repo] = struct{}{}
	}
	parts := strings.Split(raw, ",")
	seen := make(map[string]struct{}, len(parts))
	repoList := make([]string, 0, len(parts))
	for _, part := range parts {
		repo := strings.TrimSpace(part)
		if repo == "" {
			continue
		}
		if strings.ContainsAny(repo, `/\`) || strings.Contains(repo, "..") {
			return nil, fmt.Errorf("repo %q must be a managed repo name, not a path", repo)
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
		repoList = append(repoList, repo)
	}
	if len(repoList) == 0 {
		return nil, errors.New("no repos selected")
	}
	return repoList, nil
}
