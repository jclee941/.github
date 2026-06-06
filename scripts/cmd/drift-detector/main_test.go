// main_test.go — offline tests for drift-detector pure logic.
// Network-bound helpers (gh clone, git diff) are out of scope; we test the
// text-extraction logic of getManagedFiles, which is the brittle part.

package main

import (
	"os"
	"path/filepath"
	"slices"
	"testing"
)

// writeDeployFixture creates a fake repo root with a
// scripts/cmd/deploy-to-repos/main.go containing the given content.
func writeDeployFixture(t *testing.T, content string) string {
	t.Helper()
	root := t.TempDir()
	dir := filepath.Join(root, "scripts", "cmd", "deploy-to-repos")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	if err := os.WriteFile(filepath.Join(dir, "main.go"), []byte(content), 0o644); err != nil {
		t.Fatalf("write: %v", err)
	}
	return root
}

func TestGetManagedFiles_ExtractsAllowlistAndExtraFiles(t *testing.T) {
	fixture := `package main

var downstreamWorkflowAllowlist = []string{
	".github/workflows/03_pr-checks.yml",
	".github/workflows/05_gitleaks.yml",
}

var extraFiles = []string{
	".github/dependabot.yml",
	".github/CODEOWNERS",
}
`
	root := writeDeployFixture(t, fixture)
	got, err := getManagedFiles(root)
	if err != nil {
		t.Fatalf("getManagedFiles: %v", err)
	}

	want := []string{
		".github/workflows/03_pr-checks.yml",
		".github/workflows/05_gitleaks.yml",
		".github/dependabot.yml",
		".github/CODEOWNERS",
	}
	for _, w := range want {
		if !slices.Contains(got, w) {
			t.Errorf("expected managed file %q in %v", w, got)
		}
	}
	if len(got) != len(want) {
		t.Errorf("expected %d managed files, got %d: %v", len(want), len(got), got)
	}
}

func TestGetManagedFiles_IgnoresNonGithubLines(t *testing.T) {
	fixture := `package main

var downstreamWorkflowAllowlist = []string{
	".github/workflows/03_pr-checks.yml",
}

var extraFiles = []string{
	".github/dependabot.yml",
}

// a stray quoted path that is not under .github must be ignored
var somethingElse = "scripts/cmd/x/main.go"
`
	root := writeDeployFixture(t, fixture)
	got, err := getManagedFiles(root)
	if err != nil {
		t.Fatalf("getManagedFiles: %v", err)
	}
	for _, g := range got {
		if g == "scripts/cmd/x/main.go" {
			t.Errorf("non-.github path leaked into managed files: %v", got)
		}
	}
}

func TestGetManagedFiles_MissingDeployFileErrors(t *testing.T) {
	root := t.TempDir() // no scripts/cmd/deploy-to-repos/main.go
	if _, err := getManagedFiles(root); err == nil {
		t.Fatal("expected error when deploy-to-repos/main.go is missing")
	}
}

// Guard against drift in the REAL deploy-to-repos source: getManagedFiles must
// extract a non-empty set from the actual repo, proving the extraction logic
// stays compatible with the real allowlist structure.
func TestGetManagedFiles_RealSourceNonEmpty(t *testing.T) {
	root, err := findRepoRoot()
	if err != nil {
		t.Skipf("repo root not found: %v", err)
	}
	got, err := getManagedFiles(root)
	if err != nil {
		t.Fatalf("getManagedFiles on real source: %v", err)
	}
	if len(got) == 0 {
		t.Fatal("getManagedFiles returned no files from real deploy-to-repos source; extraction logic drifted")
	}
}
