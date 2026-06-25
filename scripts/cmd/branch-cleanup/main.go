package main

import (
	"flag"
	"fmt"
	"os"
	"strings"

	repoinventory "github.com/jclee941/.github/scripts/internal/repos"
)

type cleanupResult struct {
	repo    string
	branch  string
	status  string
	message string
}

func main() {
	defaultRepos := repoinventory.Names(repoinventory.ProtectedRepos())
	dryRun := flag.Bool("dry-run", false, "preview merged branch deletes without mutating repositories")
	reposFlag := flag.String("repos", strings.Join(defaultRepos, ","), "comma-separated managed repo names")
	flag.Parse()

	repoList, err := normalizeRepos(*reposFlag, defaultRepos)
	if err != nil {
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}

	defaultBranches := defaultBranchByRepo(repoinventory.ProtectedRepos())
	var results []cleanupResult
	failures := 0
	for _, repo := range repoList {
		repoResults, err := cleanupRepo(repo, defaultBranches[repo], *dryRun)
		if err != nil {
			failures++
			results = append(results, cleanupResult{repo: repo, status: "failed", message: err.Error()})
			continue
		}
		results = append(results, repoResults...)
	}

	mode := "apply"
	if *dryRun {
		mode = "dry-run"
	}
	fmt.Printf("\nSummary (%s):\n", mode)
	deleted := 0
	for _, result := range results {
		if result.branch == "" {
			fmt.Printf("- jclee941/%s: %s - %s\n", result.repo, result.status, result.message)
			continue
		}
		fmt.Printf("- jclee941/%s:%s: %s\n", result.repo, result.branch, result.status)
		if result.status == "deleted" || result.status == "would-delete" {
			deleted++
		}
	}
	fmt.Printf("Total %s branches: %d\n", branchActionNoun(*dryRun), deleted)
	if failures > 0 {
		os.Exit(1)
	}
}

func branchActionNoun(dryRun bool) string {
	if dryRun {
		return "merge-cleanup candidate"
	}
	return "deleted"
}

func defaultBranchByRepo(repos []repoinventory.Repo) map[string]string {
	defaultBranches := make(map[string]string, len(repos))
	for _, repo := range repos {
		defaultBranches[repo.Name] = repo.DefaultBranch
	}
	return defaultBranches
}
