package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestExtractYamlPaths(t *testing.T) {
	// Create temp dir with mock auto-deploy.yml
	tmpDir := t.TempDir()
	yamlContent := `on:
  push:
    branches: [master]
    paths:
      - '.github/workflows/**'
      - '.github/dependabot.yml'
      - '.github/ISSUE_TEMPLATE/**'
  workflow_dispatch:
`
	if err := os.MkdirAll(filepath.Join(tmpDir, ".github", "workflows"), 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	if err := os.WriteFile(filepath.Join(tmpDir, ".github", "workflows", "34_auto-deploy.yml"), []byte(yamlContent), 0o644); err != nil {
		t.Fatalf("write file: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	paths, err := v.extractAutoDeployPaths()
	if err != nil {
		t.Fatalf("extract paths: %v", err)
	}
	want := []string{
		".github/workflows/**",
		".github/dependabot.yml",
		".github/ISSUE_TEMPLATE/**",
	}
	if len(paths) != len(want) {
		t.Fatalf("got %d paths, want %d: %v", len(paths), len(want), paths)
	}
	for i, w := range want {
		if paths[i] != w {
			t.Errorf("path[%d] = %q, want %q", i, paths[i], w)
		}
	}
}

func TestContains(t *testing.T) {
	if !contains([]string{"a", "b", "c"}, "b") {
		t.Error("expected contains to find 'b'")
	}
	if contains([]string{"a", "b", "c"}, "d") {
		t.Error("expected contains to NOT find 'd'")
	}
}

func TestRequiredStatusChecksMatchWorkflowContexts(t *testing.T) {
	rootDir, err := findRepoRoot()
	if err != nil {
		t.Fatalf("find repo root: %v", err)
	}

	v := &validator{rootDir: rootDir}
	if err := v.requiredStatusChecksMatchWorkflowContexts(); err != nil {
		t.Fatalf("required status checks should match workflow contexts: %v", err)
	}
}

func TestNotifyOnFailureRequiresCheckoutDetectsOffender(t *testing.T) {
	tmpDir := t.TempDir()
	// A job that ends with the local composite notify action but has NO
	// default-path checkout (only a custom path: checkout) must be flagged.
	bad := `jobs:
  offender:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout to custom path
        uses: actions/checkout@v6
        with:
          path: src
      - name: Notify on failure
        if: failure()
        uses: ./.github/actions/notify-on-failure
`
	dir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	if err := os.WriteFile(filepath.Join(dir, "99_offender.yml"), []byte(bad), 0o644); err != nil {
		t.Fatalf("write file: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	if err := v.notifyOnFailureRequiresCheckout(); err == nil {
		t.Fatal("expected offender (custom-path checkout only) to be flagged, got nil")
	}

	// Adding a default-path checkout before the notify step must clear it.
	good := `jobs:
  fixed:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout local actions
        uses: actions/checkout@v6
      - name: Notify on failure
        if: failure()
        uses: ./.github/actions/notify-on-failure
`
	if err := os.WriteFile(filepath.Join(dir, "99_offender.yml"), []byte(good), 0o644); err != nil {
		t.Fatalf("write file: %v", err)
	}
	if err := v.notifyOnFailureRequiresCheckout(); err != nil {
		t.Fatalf("default-path checkout before notify should pass, got: %v", err)
	}
}

func TestNotifyOnFailureRequiresCheckoutRepoClean(t *testing.T) {
	rootDir, err := findRepoRoot()
	if err != nil {
		t.Fatalf("find repo root: %v", err)
	}
	v := &validator{rootDir: rootDir}
	if err := v.notifyOnFailureRequiresCheckout(); err != nil {
		t.Fatalf("repo should satisfy notify-on-failure checkout invariant: %v", err)
	}
}

func TestNoOrgEndpointForUserAccountDetectsOffender(t *testing.T) {
	tmpDir := t.TempDir()
	dir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	bad := "jobs:\n  x:\n    steps:\n      - run: gh api orgs/jclee941/repos\n"
	if err := os.WriteFile(filepath.Join(dir, "99_bad.yml"), []byte(bad), 0o644); err != nil {
		t.Fatalf("write file: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	if err := v.noOrgEndpointForUserAccount(); err == nil {
		t.Fatal("expected orgs/jclee941 usage to be flagged")
	}

	good := "jobs:\n  x:\n    steps:\n      - run: gh api users/jclee941/repos\n"
	if err := os.WriteFile(filepath.Join(dir, "99_bad.yml"), []byte(good), 0o644); err != nil {
		t.Fatalf("write file: %v", err)
	}
	if err := v.noOrgEndpointForUserAccount(); err != nil {
		t.Fatalf("users/jclee941 should pass, got: %v", err)
	}
}

func TestNoOrgEndpointForUserAccountRepoClean(t *testing.T) {
	rootDir, err := findRepoRoot()
	if err != nil {
		t.Fatalf("find repo root: %v", err)
	}
	v := &validator{rootDir: rootDir}
	if err := v.noOrgEndpointForUserAccount(); err != nil {
		t.Fatalf("repo should not use orgs/ endpoint for jclee941: %v", err)
	}
}

func TestOrphanReusableWorkflowsDetectsOrphan(t *testing.T) {
	tmpDir := t.TempDir()
	wfDir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	deployDir := filepath.Join(tmpDir, "scripts", "cmd", "deploy-to-repos")
	if err := os.MkdirAll(deployDir, 0o755); err != nil {
		t.Fatalf("mkdir deploy: %v", err)
	}

	// Deploy manifest lists only 45_reusable-gitleaks.yml as deployed downstream.
	deploy := "package main\n\nvar downstreamWorkflowAllowlist = map[string]struct{}{\n" +
		"\t\".github/workflows/45_reusable-gitleaks.yml\": {},\n}\n"
	if err := os.WriteFile(filepath.Join(deployDir, "main.go"), []byte(deploy), 0o644); err != nil {
		t.Fatalf("write deploy: %v", err)
	}

	callOnly := "name: x\non:\n  workflow_call:\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n"
	// 81_auto-merge: workflow_call-only, no caller, NOT in manifest -> ORPHAN.
	if err := os.WriteFile(filepath.Join(wfDir, "81_auto-merge.yml"), []byte(callOnly), 0o644); err != nil {
		t.Fatalf("write orphan: %v", err)
	}
	// 45_reusable-gitleaks: workflow_call-only but IS in manifest -> OK.
	if err := os.WriteFile(filepath.Join(wfDir, "45_reusable-gitleaks.yml"), []byte(callOnly), 0o644); err != nil {
		t.Fatalf("write manifest reusable: %v", err)
	}
	// 44_reusable-pr-checks: workflow_call-only but CALLED locally by 03 -> OK.
	if err := os.WriteFile(filepath.Join(wfDir, "44_reusable-pr-checks.yml"), []byte(callOnly), 0o644); err != nil {
		t.Fatalf("write called reusable: %v", err)
	}
	caller := "name: PR Checks\non:\n  pull_request:\njobs:\n  c:\n    uses: ./.github/workflows/44_reusable-pr-checks.yml\n"
	if err := os.WriteFile(filepath.Join(wfDir, "03_pr-checks.yml"), []byte(caller), 0o644); err != nil {
		t.Fatalf("write caller: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	err := v.orphanReusableWorkflows()
	if err == nil {
		t.Fatal("expected orphan 81_auto-merge.yml to be flagged, got nil")
	}
	if !strings.Contains(err.Error(), "81_auto-merge.yml") {
		t.Fatalf("error should name the orphan file, got: %v", err)
	}
	if strings.Contains(err.Error(), "45_reusable-gitleaks.yml") {
		t.Fatalf("manifest-deployed reusable must not be flagged: %v", err)
	}
	if strings.Contains(err.Error(), "44_reusable-pr-checks.yml") {
		t.Fatalf("locally-called reusable must not be flagged: %v", err)
	}
}

func TestOrphanReusableWorkflowsCleanPasses(t *testing.T) {
	tmpDir := t.TempDir()
	wfDir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	deployDir := filepath.Join(tmpDir, "scripts", "cmd", "deploy-to-repos")
	if err := os.MkdirAll(deployDir, 0o755); err != nil {
		t.Fatalf("mkdir deploy: %v", err)
	}
	deploy := "package main\n\nvar downstreamWorkflowAllowlist = map[string]struct{}{\n}\n"
	if err := os.WriteFile(filepath.Join(deployDir, "main.go"), []byte(deploy), 0o644); err != nil {
		t.Fatalf("write deploy: %v", err)
	}
	// Only a normal triggered workflow + a called reusable: no orphans.
	normal := "name: PR Checks\non:\n  pull_request:\njobs:\n  c:\n    uses: ./.github/workflows/44_reusable-pr-checks.yml\n"
	if err := os.WriteFile(filepath.Join(wfDir, "03_pr-checks.yml"), []byte(normal), 0o644); err != nil {
		t.Fatalf("write normal: %v", err)
	}
	callOnly := "name: x\non:\n  workflow_call:\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n"
	if err := os.WriteFile(filepath.Join(wfDir, "44_reusable-pr-checks.yml"), []byte(callOnly), 0o644); err != nil {
		t.Fatalf("write reusable: %v", err)
	}
	v := &validator{rootDir: tmpDir}
	if err := v.orphanReusableWorkflows(); err != nil {
		t.Fatalf("clean repo should pass, got: %v", err)
	}
}

func TestOrphanReusableWorkflowsRepoClean(t *testing.T) {
	rootDir, err := findRepoRoot()
	if err != nil {
		t.Fatalf("find repo root: %v", err)
	}
	v := &validator{rootDir: rootDir}
	if err := v.orphanReusableWorkflows(); err != nil {
		t.Fatalf("repo should have no orphaned reusable workflows: %v", err)
	}
}

func TestOrphanReusableWorkflowsInlineForms(t *testing.T) {
	tmpDir := t.TempDir()
	wfDir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	deployDir := filepath.Join(tmpDir, "scripts", "cmd", "deploy-to-repos")
	if err := os.MkdirAll(deployDir, 0o755); err != nil {
		t.Fatalf("mkdir deploy: %v", err)
	}
	deploy := "package main\n\nvar downstreamWorkflowAllowlist = map[string]struct{}{\n}\n"
	if err := os.WriteFile(filepath.Join(deployDir, "main.go"), []byte(deploy), 0o644); err != nil {
		t.Fatalf("write deploy: %v", err)
	}

	// Inline mapping form: `on: workflow_call` (no indented block).
	if err := os.WriteFile(filepath.Join(wfDir, "81_inline.yml"), []byte("name: x\non: workflow_call\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n"), 0o644); err != nil {
		t.Fatalf("write inline: %v", err)
	}
	// Inline array form: `on: [workflow_call]`.
	if err := os.WriteFile(filepath.Join(wfDir, "82_array.yml"), []byte("name: y\non: [workflow_call]\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n"), 0o644); err != nil {
		t.Fatalf("write array: %v", err)
	}
	// .yaml extension orphan.
	if err := os.WriteFile(filepath.Join(wfDir, "83_ext.yaml"), []byte("name: z\non:\n  workflow_call:\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n"), 0o644); err != nil {
		t.Fatalf("write yaml: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	err := v.orphanReusableWorkflows()
	if err == nil {
		t.Fatal("expected inline/array/.yaml orphans to be flagged, got nil")
	}
	for _, want := range []string{"81_inline.yml", "82_array.yml", "83_ext.yaml"} {
		if !strings.Contains(err.Error(), want) {
			t.Fatalf("orphan %s should be flagged, got: %v", want, err)
		}
	}
}

func TestOrphanReusableWorkflowsManifestParseError(t *testing.T) {
	tmpDir := t.TempDir()
	wfDir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	// No deploy-to-repos/main.go at all -> manifest unreadable. The validator
	// must NOT silently treat every reusable as deployed; it must surface the
	// error rather than masking orphans.
	if err := os.WriteFile(filepath.Join(wfDir, "45_reusable-gitleaks.yml"), []byte("name: x\non:\n  workflow_call:\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n"), 0o644); err != nil {
		t.Fatalf("write reusable: %v", err)
	}
	v := &validator{rootDir: tmpDir}
	if err := v.orphanReusableWorkflows(); err == nil {
		t.Fatal("expected an error when the deploy manifest cannot be read")
	}
}

func TestDeployManifestPathsExistDetectsMissing(t *testing.T) {
	tmpDir := t.TempDir()
	deployDir := filepath.Join(tmpDir, "scripts", "cmd", "deploy-to-repos")
	if err := os.MkdirAll(deployDir, 0o755); err != nil {
		t.Fatalf("mkdir deploy: %v", err)
	}
	wfDir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		t.Fatalf("mkdir wf: %v", err)
	}
	// Manifest lists two files; only one exists on disk.
	if err := os.WriteFile(filepath.Join(wfDir, "10_pr-review.yml"), []byte("name: x\n"), 0o644); err != nil {
		t.Fatalf("write wf: %v", err)
	}
	deploy := "package main\n\n" +
		"var downstreamWorkflowAllowlist = map[string]struct{}{\n" +
		"\t\".github/workflows/10_pr-review.yml\": {},\n" +
		"\t\".github/workflows/99_ghost.yml\": {},\n}\n" +
		"var extraFiles = []string{\n}\n"
	if err := os.WriteFile(filepath.Join(deployDir, "main.go"), []byte(deploy), 0o644); err != nil {
		t.Fatalf("write deploy: %v", err)
	}
	v := &validator{rootDir: tmpDir}
	err := v.deployManifestPathsExist()
	if err == nil {
		t.Fatal("expected missing manifest path 99_ghost.yml to be flagged")
	}
	if !strings.Contains(err.Error(), "99_ghost.yml") {
		t.Fatalf("error should name the missing path, got: %v", err)
	}
	if strings.Contains(err.Error(), "10_pr-review.yml") {
		t.Fatalf("existing path must not be flagged: %v", err)
	}
}

func TestDeployManifestPathsExistRepoClean(t *testing.T) {
	rootDir, err := findRepoRoot()
	if err != nil {
		t.Fatalf("find repo root: %v", err)
	}
	v := &validator{rootDir: rootDir}
	if err := v.deployManifestPathsExist(); err != nil {
		t.Fatalf("all deploy manifest paths should exist: %v", err)
	}
}

func TestDeployManifestConsistencyDetectsOverlap(t *testing.T) {
	tmpDir := t.TempDir()
	deployDir := filepath.Join(tmpDir, "scripts", "cmd", "deploy-to-repos")
	if err := os.MkdirAll(deployDir, 0o755); err != nil {
		t.Fatalf("mkdir deploy: %v", err)
	}
	wfDir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		t.Fatalf("mkdir wf: %v", err)
	}
	// 10_pr-review.yml is BOTH in the allowlist AND in removedWorkflows -> a
	// contradiction (deploy it AND delete it downstream).
	if err := os.WriteFile(filepath.Join(wfDir, "10_pr-review.yml"), []byte("name: x\n"), 0o644); err != nil {
		t.Fatalf("write wf: %v", err)
	}
	deploy := "package main\n\n" +
		"var downstreamWorkflowAllowlist = map[string]struct{}{\n" +
		"\t\".github/workflows/10_pr-review.yml\": {},\n}\n" +
		"var removedWorkflows = []string{\n" +
		"\t\".github/workflows/10_pr-review.yml\",\n}\n"
	if err := os.WriteFile(filepath.Join(deployDir, "main.go"), []byte(deploy), 0o644); err != nil {
		t.Fatalf("write deploy: %v", err)
	}
	v := &validator{rootDir: tmpDir}
	err := v.deployManifestConsistency()
	if err == nil {
		t.Fatal("expected allowlist/removedWorkflows overlap to be flagged")
	}
	if !strings.Contains(err.Error(), "10_pr-review.yml") {
		t.Fatalf("error should name the conflicting path, got: %v", err)
	}
}

func TestDeployManifestConsistencyDetectsRemovedStillExists(t *testing.T) {
	tmpDir := t.TempDir()
	deployDir := filepath.Join(tmpDir, "scripts", "cmd", "deploy-to-repos")
	if err := os.MkdirAll(deployDir, 0o755); err != nil {
		t.Fatalf("mkdir deploy: %v", err)
	}
	wfDir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		t.Fatalf("mkdir wf: %v", err)
	}
	// removedWorkflows lists a file that STILL exists locally -> it is supposed
	// to be deleted downstream but is still active here (drift).
	if err := os.WriteFile(filepath.Join(wfDir, "99_ghost.yml"), []byte("name: x\n"), 0o644); err != nil {
		t.Fatalf("write wf: %v", err)
	}
	deploy := "package main\n\n" +
		"var downstreamWorkflowAllowlist = map[string]struct{}{\n}\n" +
		"var removedWorkflows = []string{\n" +
		"\t\".github/workflows/99_ghost.yml\",\n}\n"
	if err := os.WriteFile(filepath.Join(deployDir, "main.go"), []byte(deploy), 0o644); err != nil {
		t.Fatalf("write deploy: %v", err)
	}
	v := &validator{rootDir: tmpDir}
	err := v.deployManifestConsistency()
	if err == nil {
		t.Fatal("expected removedWorkflows entry that still exists to be flagged")
	}
	if !strings.Contains(err.Error(), "99_ghost.yml") {
		t.Fatalf("error should name the still-existing removed path, got: %v", err)
	}
}

func TestDeployManifestConsistencyRepoClean(t *testing.T) {
	rootDir, err := findRepoRoot()
	if err != nil {
		t.Fatalf("find repo root: %v", err)
	}
	v := &validator{rootDir: rootDir}
	if err := v.deployManifestConsistency(); err != nil {
		t.Fatalf("deploy manifest should be internally consistent: %v", err)
	}
}

func TestReadmeWorkflowInventoryUniqueDetectsDup(t *testing.T) {
	tmpDir := t.TempDir()
	wfDir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	if err := os.WriteFile(filepath.Join(wfDir, "10_pr-review.yml"), []byte("name: x\n"), 0o644); err != nil {
		t.Fatalf("write wf: %v", err)
	}
	// README lists 10_pr-review.yml TWICE in inventory tables.
	readme := "# R\n\n| Workflow File | Trigger | Description |\n" +
		"|---|---|---|\n" +
		"| `10_pr-review.yml` | pull_request | a |\n" +
		"| `10_pr-review.yml` | pull_request | dup |\n"
	if err := os.WriteFile(filepath.Join(tmpDir, "README.md"), []byte(readme), 0o644); err != nil {
		t.Fatalf("write readme: %v", err)
	}
	v := &validator{rootDir: tmpDir}
	err := v.readmeWorkflowInventoryUnique()
	if err == nil {
		t.Fatal("expected duplicate README inventory row to be flagged")
	}
	if !strings.Contains(err.Error(), "10_pr-review.yml") {
		t.Fatalf("error should name the duplicated row, got: %v", err)
	}
}

func TestReadmeWorkflowInventoryUniqueDetectsMissingOrExtra(t *testing.T) {
	tmpDir := t.TempDir()
	wfDir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	if err := os.WriteFile(filepath.Join(wfDir, "10_pr-review.yml"), []byte("name: x\n"), 0o644); err != nil {
		t.Fatalf("write wf: %v", err)
	}
	// README lists a workflow that does NOT exist + omits the real one.
	readme := "# R\n\n| Workflow File | Trigger | Description |\n" +
		"|---|---|---|\n" +
		"| `99_ghost.yml` | pull_request | a |\n"
	if err := os.WriteFile(filepath.Join(tmpDir, "README.md"), []byte(readme), 0o644); err != nil {
		t.Fatalf("write readme: %v", err)
	}
	v := &validator{rootDir: tmpDir}
	err := v.readmeWorkflowInventoryUnique()
	if err == nil {
		t.Fatal("expected README inventory to mismatch actual workflow set")
	}
}

func TestReadmeWorkflowInventoryUniqueRepoClean(t *testing.T) {
	rootDir, err := findRepoRoot()
	if err != nil {
		t.Fatalf("find repo root: %v", err)
	}
	v := &validator{rootDir: rootDir}
	if err := v.readmeWorkflowInventoryUnique(); err != nil {
		t.Fatalf("README workflow inventory should be unique and complete: %v", err)
	}
}
