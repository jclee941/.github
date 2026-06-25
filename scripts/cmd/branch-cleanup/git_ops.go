package main

import (
	"bytes"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

func cleanupRepo(repo, defaultBranch string, dryRun bool) ([]cleanupResult, error) {
	workDir, err := os.MkdirTemp("", "jclee-branch-cleanup-*")
	if err != nil {
		return nil, fmt.Errorf("create temp dir: %w", err)
	}
	defer os.RemoveAll(workDir)

	repoDir := filepath.Join(workDir, repo)
	fullRepo := "jclee941/" + repo
	if err := runGit("", "gh", "repo", "clone", fullRepo, repoDir, "--", "--filter=blob:none", "--no-checkout", "--quiet"); err != nil {
		return nil, fmt.Errorf("clone repo: %w", err)
	}
	if err := runGit(repoDir, "git", "fetch", "--prune", "origin", "--quiet"); err != nil {
		return nil, fmt.Errorf("fetch repo: %w", err)
	}

	openPRHeads, err := listOpenPRHeads(fullRepo)
	if err != nil {
		return nil, fmt.Errorf("list open PR heads: %w", err)
	}
	branches, err := listRemoteBranches(repoDir, defaultBranch)
	if err != nil {
		return nil, fmt.Errorf("list remote branches: %w", err)
	}

	candidates := cleanupCandidates(branches, openPRHeads, defaultBranch)
	results := make([]cleanupResult, 0, len(candidates))
	for _, branch := range candidates {
		status := "would-delete"
		if !dryRun {
			if err := deleteBranch(fullRepo, branch); err != nil {
				results = append(results, cleanupResult{repo: repo, branch: branch, status: "failed", message: err.Error()})
				continue
			}
			status = "deleted"
		}
		results = append(results, cleanupResult{repo: repo, branch: branch, status: status})
	}
	if len(results) == 0 {
		return []cleanupResult{{repo: repo, status: "clean", message: "no merged stale branches"}}, nil
	}
	return results, nil
}

func listRemoteBranches(repoDir, defaultBranch string) ([]remoteBranch, error) {
	output, err := gitOutput(repoDir, "git", "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin")
	if err != nil {
		return nil, err
	}

	var branches []remoteBranch
	for _, line := range strings.Split(output, "\n") {
		ref := strings.TrimSpace(line)
		if ref == "" || ref == "origin" || ref == "origin/HEAD" {
			continue
		}
		branch := strings.TrimPrefix(ref, "origin/")
		merged, err := branchMerged(repoDir, branch, defaultBranch)
		if err != nil {
			return nil, err
		}
		branches = append(branches, remoteBranch{name: branch, mergedToDefault: merged})
	}
	return branches, nil
}

func branchMerged(repoDir, branch, defaultBranch string) (bool, error) {
	cmd := exec.Command("git", "merge-base", "--is-ancestor", "origin/"+branch, "origin/"+defaultBranch)
	cmd.Dir = repoDir
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	err := cmd.Run()
	if err == nil {
		return true, nil
	}
	if exitErr, ok := err.(*exec.ExitError); ok && exitErr.ExitCode() == 1 {
		return false, nil
	}
	if stderr.Len() > 0 {
		return false, fmt.Errorf("%s: %s", err, strings.TrimSpace(stderr.String()))
	}
	return false, err
}

func gitOutput(dir string, name string, args ...string) (string, error) {
	cmd := exec.Command(name, args...)
	cmd.Dir = dir
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		if stderr.Len() > 0 {
			return "", fmt.Errorf("%s: %s", err, strings.TrimSpace(stderr.String()))
		}
		return "", err
	}
	return stdout.String(), nil
}

func runGit(dir string, name string, args ...string) error {
	_, err := gitOutput(dir, name, args...)
	return err
}
