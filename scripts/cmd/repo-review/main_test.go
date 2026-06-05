package main

import (
	"os"
	"path/filepath"
	"testing"
)

// resolveReviewScript must find repo_review.py regardless of how the binary is
// launched. Under `go run`, os.Args[0] is a /tmp/go-build.../exe path, so the
// old os.Args[0]-relative logic failed with Errno 2. The resolver must prefer
// an explicit env var, then the current working directory (the workflow does
// `cd scripts && go run ./cmd/repo-review`, so repo_review.py is ./repo_review.py).
func TestResolveReviewScript_PrefersEnvVar(t *testing.T) {
	dir := t.TempDir()
	script := filepath.Join(dir, "repo_review.py")
	if err := os.WriteFile(script, []byte("# stub"), 0o644); err != nil {
		t.Fatal(err)
	}
	t.Setenv("REPO_REVIEW_SCRIPT", script)
	got := resolveReviewScript()
	if got != script {
		t.Fatalf("expected env-var path %q, got %q", script, got)
	}
}

func TestResolveReviewScript_FindsInCwd(t *testing.T) {
	dir := t.TempDir()
	script := filepath.Join(dir, "repo_review.py")
	if err := os.WriteFile(script, []byte("# stub"), 0o644); err != nil {
		t.Fatal(err)
	}
	t.Setenv("REPO_REVIEW_SCRIPT", "")
	old, _ := os.Getwd()
	defer os.Chdir(old)
	if err := os.Chdir(dir); err != nil {
		t.Fatal(err)
	}
	got := resolveReviewScript()
	abs, _ := filepath.Abs("repo_review.py")
	if got != abs && got != "repo_review.py" && got != script {
		t.Fatalf("expected cwd-relative repo_review.py, got %q", got)
	}
	if _, err := os.Stat(got); err != nil {
		t.Fatalf("resolved path does not exist: %q (%v)", got, err)
	}
}
