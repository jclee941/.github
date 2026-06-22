package main

import (
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"

	repoinventory "github.com/jclee941/.github/scripts/internal/repos"
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

func TestDefaultReviewRepos_followProtectedRepoInventory(t *testing.T) {
	want := repoinventory.Names(repoinventory.ProtectedRepos())
	got := strings.Split(defaultReviewRepos, ",")
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("defaultReviewRepos = %v, want protected inventory repos %v", got, want)
	}
}

func TestDefaultReviewRepos_includesPrivateProtectedRepos(t *testing.T) {
	for _, repo := range []string{"hycu", "youtube", "propose"} {
		if !strings.Contains(","+defaultReviewRepos+",", ","+repo+",") {
			t.Fatalf("defaultReviewRepos missing private protected repo %q: %s", repo, defaultReviewRepos)
		}
	}
}

func TestNormalizeReviewReposCanonicalizesAllowedRepos(t *testing.T) {
	got, err := normalizeReviewRepos("resume, tmux,resume,hycu")
	if err != nil {
		t.Fatalf("normalizeReviewRepos returned error: %v", err)
	}
	want := []string{"resume", "tmux", "hycu"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("normalizeReviewRepos = %v, want %v", got, want)
	}
}

func TestNormalizeReviewReposRejectsUnsafeNames(t *testing.T) {
	for _, raw := range []string{"../resume", "jclee941/resume", `resume\\x`, "not-managed"} {
		t.Run(raw, func(t *testing.T) {
			if _, err := normalizeReviewRepos(raw); err == nil {
				t.Fatal("expected unsafe or unmanaged repo to be rejected")
			}
		})
	}
}

func TestCloneReviewRepoArgsDoNotExposeToken(t *testing.T) {
	args := cloneReviewRepoArgs("jclee941", "resume", "/tmp/repo-review/resume")
	joined := strings.Join(args, " ")
	tokenMarker := "x-access" + "-token"
	envMarker := "GH" + "_TOKEN"
	if strings.Contains(joined, tokenMarker) || strings.Contains(joined, envMarker) {
		t.Fatalf("clone args must not expose token material: %q", joined)
	}
	want := []string{"repo", "clone", "jclee941/resume", "/tmp/repo-review/resume", "--", "--depth", "200"}
	if !reflect.DeepEqual(args, want) {
		t.Fatalf("clone args = %v, want %v", args, want)
	}
}
