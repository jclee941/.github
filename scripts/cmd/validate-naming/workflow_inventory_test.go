package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestWorkflowsDeriveManagedRepoInventoryFromConfigDetectsHardcodedList(t *testing.T) {
	tmpDir := t.TempDir()
	wfDir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}

	bad := `name: bad
on:
  workflow_dispatch:
jobs:
  heal:
    runs-on: ubuntu-latest
    steps:
      - run: |
          REPOS="account blacklist resume tmux"
          for repo in $REPOS; do echo "$repo"; done
`
	if err := os.WriteFile(filepath.Join(wfDir, "60_bad.yml"), []byte(bad), 0o644); err != nil {
		t.Fatalf("write bad workflow: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	err := v.workflowsDeriveManagedRepoInventoryFromConfig()
	if err == nil {
		t.Fatal("expected hardcoded managed repo inventory to be flagged")
	}
	if !strings.Contains(err.Error(), "60_bad.yml") {
		t.Fatalf("error should identify offending workflow, got: %v", err)
	}
}

func TestWorkflowsDeriveManagedRepoInventoryFromConfigDetectsInputDefault(t *testing.T) {
	tmpDir := t.TempDir()
	wfDir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}

	bad := `name: bad
on:
  workflow_dispatch:
    inputs:
      repos:
        default: "account,blacklist,resume,tmux"
jobs:
  noop:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
`
	if err := os.WriteFile(filepath.Join(wfDir, "40_bad.yml"), []byte(bad), 0o644); err != nil {
		t.Fatalf("write bad workflow: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	if err := v.workflowsDeriveManagedRepoInventoryFromConfig(); err == nil {
		t.Fatal("expected hardcoded workflow_dispatch repo default to be flagged")
	}
}

func TestWorkflowsDeriveManagedRepoInventoryFromConfigDetectsBlockScalarInputDefault(t *testing.T) {
	tmpDir := t.TempDir()
	wfDir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}

	bad := `name: bad
on:
  workflow_dispatch:
    inputs:
      repos:
        default: |
          account
          blacklist
          resume
          tmux
jobs:
  noop:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
`
	if err := os.WriteFile(filepath.Join(wfDir, "41_bad.yml"), []byte(bad), 0o644); err != nil {
		t.Fatalf("write bad workflow: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	if err := v.workflowsDeriveManagedRepoInventoryFromConfig(); err == nil {
		t.Fatal("expected block-scalar workflow_dispatch repo default to be flagged")
	}
}

func TestWorkflowsDeriveManagedRepoInventoryFromConfigDetectsMultilineShellArray(t *testing.T) {
	tmpDir := t.TempDir()
	wfDir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}

	bad := `name: bad
on:
  workflow_dispatch:
jobs:
  heal:
    runs-on: ubuntu-latest
    steps:
      - run: |
          REPOS=(
            account
            blacklist
            resume
            tmux
          )
          for repo in "${REPOS[@]}"; do echo "$repo"; done
`
	if err := os.WriteFile(filepath.Join(wfDir, "62_bad.yml"), []byte(bad), 0o644); err != nil {
		t.Fatalf("write bad workflow: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	if err := v.workflowsDeriveManagedRepoInventoryFromConfig(); err == nil {
		t.Fatal("expected multiline shell repo array to be flagged")
	}
}

func TestWorkflowsDeriveManagedRepoInventoryFromConfigDetectsShellArray(t *testing.T) {
	tmpDir := t.TempDir()
	wfDir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}

	bad := `name: bad
on:
  workflow_dispatch:
jobs:
  heal:
    runs-on: ubuntu-latest
    steps:
      - run: |
          REPOS=(account blacklist resume tmux)
          for repo in "${REPOS[@]}"; do echo "$repo"; done
`
	if err := os.WriteFile(filepath.Join(wfDir, "61_bad.yml"), []byte(bad), 0o644); err != nil {
		t.Fatalf("write bad workflow: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	if err := v.workflowsDeriveManagedRepoInventoryFromConfig(); err == nil {
		t.Fatal("expected hardcoded shell repo array to be flagged")
	}
}

func TestWorkflowsDeriveManagedRepoInventoryFromConfigAllowsCliDerivedList(t *testing.T) {
	tmpDir := t.TempDir()
	wfDir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}

	good := `name: good
on:
  workflow_dispatch:
jobs:
  heal:
    runs-on: ubuntu-latest
    steps:
      - run: |
          repos=$(cd scripts && go run ./cmd/repo-review --print-default-repos)
          echo "repos=$repos" >> "$GITHUB_OUTPUT"
`
	if err := os.WriteFile(filepath.Join(wfDir, "60_good.yml"), []byte(good), 0o644); err != nil {
		t.Fatalf("write good workflow: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	if err := v.workflowsDeriveManagedRepoInventoryFromConfig(); err != nil {
		t.Fatalf("CLI-derived managed repo inventory should pass, got: %v", err)
	}
}

func TestWorkflowsDeriveManagedRepoInventoryFromConfigRepoClean(t *testing.T) {
	rootDir, err := findRepoRoot()
	if err != nil {
		t.Fatalf("find repo root: %v", err)
	}
	v := &validator{rootDir: rootDir}
	if err := v.workflowsDeriveManagedRepoInventoryFromConfig(); err != nil {
		t.Fatalf("repo should not hardcode managed repo inventory in workflows: %v", err)
	}
}
