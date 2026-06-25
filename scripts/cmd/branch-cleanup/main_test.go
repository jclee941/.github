package main

import (
	"reflect"
	"strings"
	"testing"

	repoinventory "github.com/jclee941/.github/scripts/internal/repos"
)

func TestCleanupCandidatesExcludesProtectedBranchesAndOpenPRs(t *testing.T) {
	branches := []remoteBranch{
		{name: "master", mergedToDefault: true},
		{name: "release/v1", mergedToDefault: true},
		{name: "dependabot/npm/pkg", mergedToDefault: true},
		{name: "fix/merged", mergedToDefault: true},
		{name: "fix/not-merged", mergedToDefault: false},
	}
	openPRHeads := map[string]struct{}{"dependabot/npm/pkg": {}}

	got := cleanupCandidates(branches, openPRHeads, "master")
	want := []string{"fix/merged"}

	if !reflect.DeepEqual(got, want) {
		t.Fatalf("cleanupCandidates() = %v, want %v", got, want)
	}
}

func TestProtectedBranch(t *testing.T) {
	cases := []struct {
		branch string
		want   bool
	}{
		{branch: "", want: true},
		{branch: "master", want: true},
		{branch: "main", want: true},
		{branch: "develop", want: true},
		{branch: "release", want: true},
		{branch: "release/2026.06", want: true},
		{branch: "fix/issue-1", want: false},
	}

	for _, tc := range cases {
		t.Run(tc.branch, func(t *testing.T) {
			got := protectedBranch(tc.branch, "master")
			if got != tc.want {
				t.Fatalf("protectedBranch(%q) = %v, want %v", tc.branch, got, tc.want)
			}
		})
	}
}

func TestNormalizeRepos(t *testing.T) {
	allowed := []string{"resume", "terraform", "tmux"}
	got, err := normalizeRepos(" resume,tmux,resume ", allowed)
	if err != nil {
		t.Fatalf("normalizeRepos returned error: %v", err)
	}
	want := []string{"resume", "tmux"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("normalizeRepos() = %v, want %v", got, want)
	}
}

func TestNormalizeReposRejectsUnknownRepo(t *testing.T) {
	_, err := normalizeRepos("resume,unknown", []string{"resume"})
	if err == nil {
		t.Fatal("normalizeRepos accepted an unknown repo")
	}
	if !strings.Contains(err.Error(), `unsupported repo "unknown"`) {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestProtectedInventoryHasDefaultBranches(t *testing.T) {
	defaults := defaultBranchByRepo(repoinventory.ProtectedRepos())
	for _, repo := range repoinventory.ProtectedRepos() {
		if defaults[repo.Name] == "" {
			t.Fatalf("repo %q has empty default branch", repo.Name)
		}
	}
}
