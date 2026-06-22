package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

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

func TestReadmeWorkflowInventoryTriggersDetectsMismatch(t *testing.T) {
	tmpDir := t.TempDir()
	wfDir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	workflow := "name: x\non:\n  pull_request:\n  workflow_dispatch:\njobs:\n  a:\n    runs-on: ubuntu-latest\n"
	if err := os.WriteFile(filepath.Join(wfDir, "10_pr-review.yml"), []byte(workflow), 0o644); err != nil {
		t.Fatalf("write wf: %v", err)
	}
	readme := "# R\n\n| Workflow File | Trigger | Description |\n" +
		"|---|---|---|\n" +
		"| `10_pr-review.yml` | push | a |\n"
	if err := os.WriteFile(filepath.Join(tmpDir, "README.md"), []byte(readme), 0o644); err != nil {
		t.Fatalf("write readme: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	err := v.readmeWorkflowInventoryTriggers()
	if err == nil {
		t.Fatal("expected stale README trigger label to be flagged")
	}
	if !strings.Contains(err.Error(), `actual="pull_request, manual"`) {
		t.Fatalf("error should name the actual trigger label, got: %v", err)
	}
}

func TestReadmeWorkflowInventoryTriggersRepoClean(t *testing.T) {
	rootDir, err := findRepoRoot()
	if err != nil {
		t.Fatalf("find repo root: %v", err)
	}
	v := &validator{rootDir: rootDir}
	if err := v.readmeWorkflowInventoryTriggers(); err != nil {
		t.Fatalf("README workflow triggers should match workflow files: %v", err)
	}
}
