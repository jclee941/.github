package main

import (
	"errors"
	"fmt"
	"sort"
	"strings"
)

func normalizeRepos(raw string, allowedRepoNames []string) ([]string, error) {
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
