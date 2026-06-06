// main_test.go — offline tests for drift-detector pure logic.
// Network-bound helpers (gh clone, git diff) are out of scope; we test the
// text-extraction logic of getManagedFiles, which is the brittle part.

package main

import (
	"bytes"
	"os"
	"path/filepath"
	"slices"
	"strings"
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

// --- Mermaid output (S1/S2) and existing-format regression (S3) tests ---

func TestPrintMermaid_WithDrift(t *testing.T) {
	repoNames := []string{"account", "blacklist", "resume"}
	drifts := []driftResult{
		{Repo: "account", File: ".github/workflows/03_pr-checks.yml", Status: "missing", Severity: "critical"},
		{Repo: "account", File: ".github/dependabot.yml", Status: "modified", Severity: "warning"},
		{Repo: "blacklist", File: ".github/CODEOWNERS", Status: "modified", Severity: "warning"},
	}
	var buf bytes.Buffer
	renderMermaid(&buf, repoNames, drifts)
	out := buf.String()

	// fenced GitHub-native mermaid block
	if !strings.Contains(out, "```mermaid") {
		t.Errorf("expected fenced ```mermaid block, got:\n%s", out)
	}
	if !strings.Contains(out, "flowchart TB") {
		t.Errorf("expected 'flowchart TB', got:\n%s", out)
	}
	// one node per repo (sanitized id repo_<name>)
	for _, r := range repoNames {
		id := "repo_" + r
		if !strings.Contains(out, id) {
			t.Errorf("expected repo node %q in diagram, got:\n%s", id, out)
		}
	}
	// severity aggregation: account has a critical -> critical class; blacklist only warning;
	// resume has no drift -> clean.
	if !strings.Contains(out, "class repo_account critical") {
		t.Errorf("account should be classed critical, got:\n%s", out)
	}
	if !strings.Contains(out, "class repo_blacklist warning") {
		t.Errorf("blacklist should be classed warning, got:\n%s", out)
	}
	if !strings.Contains(out, "class repo_resume clean") {
		t.Errorf("resume (no drift) should be classed clean, got:\n%s", out)
	}
	// severity classDefs with architecture.md colors
	if !strings.Contains(out, "#e74c3c") || !strings.Contains(out, "#6ba06a") {
		t.Errorf("expected severity colors (#e74c3c critical, #6ba06a clean), got:\n%s", out)
	}
	// drifted file appears as a node under its repo
	if !strings.Contains(out, "03_pr-checks.yml") {
		t.Errorf("expected drifted file node for 03_pr-checks.yml, got:\n%s", out)
	}
	// closing fence
	if strings.Count(out, "```") < 2 {
		t.Errorf("expected opening and closing fence, got:\n%s", out)
	}
}

func TestPrintMermaid_ZeroDrift(t *testing.T) {
	repoNames := []string{"account", "blacklist"}
	var buf bytes.Buffer
	renderMermaid(&buf, repoNames, nil)
	out := buf.String()
	if !strings.Contains(out, "```mermaid") || !strings.Contains(out, "flowchart TB") {
		t.Errorf("zero-drift mermaid must still be a valid diagram, got:\n%s", out)
	}
	// every repo is clean
	for _, r := range repoNames {
		if !strings.Contains(out, "class repo_"+r+" clean") {
			t.Errorf("zero-drift: repo %q must be clean, got:\n%s", r, out)
		}
	}
	if strings.Contains(out, "critical") && !strings.Contains(out, "classDef critical") {
		t.Errorf("zero-drift diagram should not class any repo critical, got:\n%s", out)
	}
}

// sanitizeMermaidID must produce Mermaid-safe identifiers (no '-' or '.').
func TestSanitizeMermaidID(t *testing.T) {
	cases := map[string]string{
		"idle-outpost": "idle_outpost",
		"hycu_fsds":    "hycu_fsds",
		"a.b-c":        "a_b_c",
	}
	for in, want := range cases {
		if got := sanitizeMermaidID(in); got != want {
			t.Errorf("sanitizeMermaidID(%q)=%q, want %q", in, got, want)
		}
	}
}

// captureStdout runs fn and returns everything it wrote to os.Stdout.
func captureStdout(t *testing.T, fn func()) string {
	t.Helper()
	orig := os.Stdout
	r, w, err := os.Pipe()
	if err != nil {
		t.Fatalf("pipe: %v", err)
	}
	os.Stdout = w
	fn()
	_ = w.Close()
	os.Stdout = orig
	var buf bytes.Buffer
	_, _ = buf.ReadFrom(r)
	return buf.String()
}

func sampleDrifts() []driftResult {
	return []driftResult{
		{Repo: "account", File: ".github/workflows/03_pr-checks.yml", Status: "missing", Severity: "critical"},
		{Repo: "blacklist", File: ".github/CODEOWNERS", Status: "modified", Severity: "warning"},
	}
}

func TestExistingFormatsRemainByteIdentical(t *testing.T) {
	drifts := sampleDrifts()

	wantText := "=== DRIFT DETECTED ===\n" +
		"[account] .github/workflows/03_pr-checks.yml: missing (severity: critical)\n" +
		"[blacklist] .github/CODEOWNERS: modified (severity: warning)\n"
	if got := captureStdout(t, func() { printText(drifts) }); got != wantText {
		t.Errorf("printText drifted.\n got=%q\nwant=%q", got, wantText)
	}

	wantMd := "## Downstream Automation Drift Report\n\n" +
		"| Repo | File | Status | Severity |\n" +
		"|------|------|--------|----------|\n" +
		"| account | .github/workflows/03_pr-checks.yml | missing | critical |\n" +
		"| blacklist | .github/CODEOWNERS | modified | warning |\n\n" +
		"**Action required**: Run `(cd scripts && go run ./cmd/deploy-to-repos)` to sync.\n"
	if got := captureStdout(t, func() { printMarkdown(drifts) }); got != wantMd {
		t.Errorf("printMarkdown drifted.\n got=%q\nwant=%q", got, wantMd)
	}
}

func TestPrintJSON_Shape(t *testing.T) {
	drifts := sampleDrifts()
	got := captureStdout(t, func() { printJSON(drifts) })
	if !strings.Contains(got, `"repos":`) || !strings.Contains(got, `"drifts":`) {
		t.Errorf("printJSON shape changed, got:\n%s", got)
	}
	if !strings.Contains(got, `"account"`) || !strings.Contains(got, `"blacklist"`) {
		t.Errorf("printJSON missing repos, got:\n%s", got)
	}
}

// findRepoRoot must locate the repo root via a STABLE marker (config/repos.yaml,
// the single source of truth) — not a specific workflow filename that changes
// when workflows are renamed (e.g. pr-checks.yml -> 03_pr-checks.yml).
func TestFindRepoRoot_UsesStableMarker(t *testing.T) {
	root := t.TempDir()
	if err := os.MkdirAll(filepath.Join(root, ".github", "workflows"), 0o755); err != nil {
		t.Fatalf("mkdir workflows: %v", err)
	}
	// numeric-prefixed workflow only; NO bare pr-checks.yml
	if err := os.WriteFile(filepath.Join(root, ".github", "workflows", "03_pr-checks.yml"), []byte("name: PR Checks\n"), 0o644); err != nil {
		t.Fatalf("write workflow: %v", err)
	}
	if err := os.MkdirAll(filepath.Join(root, "config"), 0o755); err != nil {
		t.Fatalf("mkdir config: %v", err)
	}
	if err := os.WriteFile(filepath.Join(root, "config", "repos.yaml"), []byte("repositories: []\n"), 0o644); err != nil {
		t.Fatalf("write repos.yaml: %v", err)
	}
	sub := filepath.Join(root, "scripts", "cmd", "drift-detector")
	if err := os.MkdirAll(sub, 0o755); err != nil {
		t.Fatalf("mkdir sub: %v", err)
	}
	orig, _ := os.Getwd()
	t.Cleanup(func() { _ = os.Chdir(orig) })
	if err := os.Chdir(sub); err != nil {
		t.Fatalf("chdir: %v", err)
	}
	got, err := findRepoRoot()
	if err != nil {
		t.Fatalf("findRepoRoot failed with stable marker present: %v", err)
	}
	wantResolved, _ := filepath.EvalSymlinks(root)
	gotResolved, _ := filepath.EvalSymlinks(got)
	if gotResolved != wantResolved {
		t.Errorf("findRepoRoot=%q, want %q", gotResolved, wantResolved)
	}
}
