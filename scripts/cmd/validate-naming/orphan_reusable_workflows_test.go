package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestOrphanReusableWorkflowsDetectsOrphan(t *testing.T) {
	tmpDir := t.TempDir()
	wfDir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}

	callOnly := "name: x\non:\n  workflow_call:\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n"
	// 81_auto-merge: workflow_call-only, no caller -> ORPHAN.
	if err := os.WriteFile(filepath.Join(wfDir, "81_auto-merge.yml"), []byte(callOnly), 0o644); err != nil {
		t.Fatalf("write orphan: %v", err)
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
