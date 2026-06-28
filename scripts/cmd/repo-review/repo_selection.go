package main

import (
	"fmt"
	"strings"

	repoinventory "github.com/jclee941/jclee-bot/scripts/internal/repos"
)

func normalizeReviewRepos(raw string) ([]string, error) {
	allowed := map[string]struct{}{}
	for _, repo := range repoinventory.ProtectedRepos() {
		allowed[repo.Name] = struct{}{}
	}

	var repos []string
	seen := map[string]struct{}{}
	for _, part := range strings.Split(raw, ",") {
		repo := strings.TrimSpace(part)
		if repo == "" {
			continue
		}
		if strings.Contains(repo, "/") || strings.Contains(repo, "\\") || strings.Contains(repo, "..") {
			return nil, fmt.Errorf("repo %q must be a managed repo name, not a path or owner-qualified name", repo)
		}
		if _, ok := allowed[repo]; !ok {
			return nil, fmt.Errorf("repo %q is not in protected managed inventory", repo)
		}
		if _, ok := seen[repo]; ok {
			continue
		}
		seen[repo] = struct{}{}
		repos = append(repos, repo)
	}
	if len(repos) == 0 {
		return nil, fmt.Errorf("no repos selected")
	}
	return repos, nil
}
