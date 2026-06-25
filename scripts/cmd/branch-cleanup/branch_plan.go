package main

import "strings"

type remoteBranch struct {
	name            string
	mergedToDefault bool
}

func cleanupCandidates(branches []remoteBranch, openPRHeads map[string]struct{}, defaultBranch string) []string {
	candidates := make([]string, 0, len(branches))
	for _, branch := range branches {
		if protectedBranch(branch.name, defaultBranch) {
			continue
		}
		if _, ok := openPRHeads[branch.name]; ok {
			continue
		}
		if branch.mergedToDefault {
			candidates = append(candidates, branch.name)
		}
	}
	return candidates
}

func protectedBranch(branch, defaultBranch string) bool {
	switch {
	case branch == "":
		return true
	case branch == defaultBranch:
		return true
	case branch == "master" || branch == "main" || branch == "develop":
		return true
	case branch == "release" || strings.HasPrefix(branch, "release/"):
		return true
	default:
		return false
	}
}
