package main

import (
	"os"
	"path/filepath"
)

func resolveReviewScript() string {
	if env := os.Getenv("REPO_REVIEW_SCRIPT"); env != "" {
		return env
	}
	candidates := []string{"repo_review.py"}
	if cwd, err := os.Getwd(); err == nil {
		candidates = append(candidates, filepath.Join(cwd, "repo_review.py"))
	}
	scriptDir := filepath.Dir(os.Args[0])
	candidates = append(candidates,
		filepath.Join(scriptDir, "repo_review.py"),
		filepath.Join(scriptDir, "..", "..", "repo_review.py"),
	)
	for _, candidate := range candidates {
		if _, err := os.Stat(candidate); err == nil {
			return candidate
		}
	}
	return "repo_review.py"
}
