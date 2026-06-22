package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestActiveWorkflowsAvoidStaleControlPlaneSurfacesDetectsLiveRepoDiscovery(t *testing.T) {
	tmpDir := t.TempDir()
	wfDir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}

	bad := `name: bad
on:
  workflow_dispatch:
jobs:
  discover:
    runs-on: ubuntu-latest
    steps:
      - run: gh api users/jclee941/repos --paginate
`
	if err := os.WriteFile(filepath.Join(wfDir, "31_bad.yml"), []byte(bad), 0o644); err != nil {
		t.Fatalf("write bad workflow: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	err := v.activeWorkflowsAvoidStaleControlPlaneSurfaces()
	if err == nil {
		t.Fatal("expected live repo discovery to be flagged")
	}
	if !strings.Contains(err.Error(), "31_bad.yml") {
		t.Fatalf("error should identify offending workflow, got: %v", err)
	}
}

func TestActiveWorkflowsAvoidStaleControlPlaneSurfacesDetectsRetiredWorkflowDependency(t *testing.T) {
	tmpDir := t.TempDir()
	wfDir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}

	bad := `name: bad
on:
  workflow_run:
    workflows: ["Template Sync", "Auto Deploy Workflows"]
    types: [completed]
jobs:
  noop:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
`
	if err := os.WriteFile(filepath.Join(wfDir, "29_bad.yml"), []byte(bad), 0o644); err != nil {
		t.Fatalf("write bad workflow: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	err := v.activeWorkflowsAvoidStaleControlPlaneSurfaces()
	if err == nil {
		t.Fatal("expected retired workflow dependencies to be flagged")
	}
	for _, want := range []string{"Template Sync", "Auto Deploy Workflows"} {
		if !strings.Contains(err.Error(), want) {
			t.Fatalf("error should mention %q, got: %v", want, err)
		}
	}
}

func TestActiveWorkflowsAvoidStaleControlPlaneSurfacesDetectsWorkflowOwnedGitOps(t *testing.T) {
	tmpDir := t.TempDir()
	wfDir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}

	bad := `name: workflow-owned GitOps
on:
  push:
    branches: ['fix/**']
jobs:
  open-pr:
    runs-on: ubuntu-latest
    steps:
      - run: gh pr create --head fix/x --base master
`
	if err := os.WriteFile(filepath.Join(wfDir, "52_workflow-owned-gitops.yml"), []byte(bad), 0o644); err != nil {
		t.Fatalf("write bad workflow: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	err := v.activeWorkflowsAvoidStaleControlPlaneSurfaces()
	if err == nil {
		t.Fatal("expected workflow-owned GitOps automation to be flagged")
	}
	if !strings.Contains(err.Error(), "52_workflow-owned-gitops.yml") {
		t.Fatalf("error should identify GitOps workflow, got: %v", err)
	}
}

func TestActiveWorkflowsAvoidStaleControlPlaneSurfacesDetectsNewWorkflowOwnedGitOps(t *testing.T) {
	tmpDir := t.TempDir()
	wfDir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}

	bad := `name: new gitops
on:
  workflow_dispatch:
jobs:
  merge:
    runs-on: ubuntu-latest
    steps:
      - run: gh pr merge 123 --squash
`
	if err := os.WriteFile(filepath.Join(wfDir, "52_new-gitops.yml"), []byte(bad), 0o644); err != nil {
		t.Fatalf("write bad workflow: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	err := v.activeWorkflowsAvoidStaleControlPlaneSurfaces()
	if err == nil {
		t.Fatal("expected new workflow-owned GitOps automation to be flagged")
	}
	if !strings.Contains(err.Error(), "52_new-gitops.yml") {
		t.Fatalf("error should identify new GitOps workflow, got: %v", err)
	}
}

func TestActiveWorkflowsAvoidStaleControlPlaneSurfacesDetectsUndefinedReposLoop(t *testing.T) {
	tmpDir := t.TempDir()
	wfDir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}

	bad := `name: bad
on:
  workflow_dispatch:
jobs:
  health:
    runs-on: ubuntu-latest
    steps:
      - run: |
          set -u
          for REPO in $REPOS; do echo "$REPO"; done
`
	if err := os.WriteFile(filepath.Join(wfDir, "29_bad.yml"), []byte(bad), 0o644); err != nil {
		t.Fatalf("write bad workflow: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	if err := v.activeWorkflowsAvoidStaleControlPlaneSurfaces(); err == nil {
		t.Fatal("expected undefined REPOS loop to be flagged")
	}
}

func TestActiveWorkflowsAvoidStaleControlPlaneSurfacesAllowsConfigDerivedInventory(t *testing.T) {
	tmpDir := t.TempDir()
	wfDir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}

	good := `name: good
on:
  workflow_run:
    workflows: ["Sanity"]
    types: [completed]
jobs:
  health:
    runs-on: ubuntu-latest
    steps:
      - run: |
          REPOS=$(cd scripts && go run ./cmd/repo-review --print-default-repos)
          for REPO in $(echo "$REPOS" | tr ',' ' '); do echo "$REPO"; done
`
	if err := os.WriteFile(filepath.Join(wfDir, "29_good.yml"), []byte(good), 0o644); err != nil {
		t.Fatalf("write good workflow: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	if err := v.activeWorkflowsAvoidStaleControlPlaneSurfaces(); err != nil {
		t.Fatalf("config-derived workflow inventory should pass, got: %v", err)
	}
}

func TestActiveWorkflowsAvoidStaleControlPlaneSurfacesDetectsUnsplitCSVRepoLoop(t *testing.T) {
	tmpDir := t.TempDir()
	wfDir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}

	bad := `name: bad
on:
  workflow_dispatch:
jobs:
  health:
    runs-on: ubuntu-latest
    steps:
      - run: |
          REPOS=$(cd scripts && go run ./cmd/repo-review --print-default-repos)
          for REPO in $REPOS; do echo "$REPO"; done
`
	if err := os.WriteFile(filepath.Join(wfDir, "29_bad.yml"), []byte(bad), 0o644); err != nil {
		t.Fatalf("write bad workflow: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	if err := v.activeWorkflowsAvoidStaleControlPlaneSurfaces(); err == nil {
		t.Fatal("expected unsplit CSV repo loop to be flagged")
	}
}

func TestActiveWorkflowsAvoidStaleControlPlaneSurfacesDetectsLowercaseBraceCSVLoop(t *testing.T) {
	tmpDir := t.TempDir()
	wfDir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}

	bad := `name: bad
on:
  workflow_dispatch:
jobs:
  health:
    runs-on: ubuntu-latest
    steps:
      - run: |
          REPOS=$(cd scripts && go run ./cmd/repo-review --print-default-repos)
          for repo in ${REPOS}; do echo "$repo"; done
`
	if err := os.WriteFile(filepath.Join(wfDir, "29_bad.yml"), []byte(bad), 0o644); err != nil {
		t.Fatalf("write bad workflow: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	if err := v.activeWorkflowsAvoidStaleControlPlaneSurfaces(); err == nil {
		t.Fatal("expected lowercase unsplit CSV repo loop to be flagged")
	}
}

func TestActiveWorkflowsAvoidStaleControlPlaneSurfacesRepoClean(t *testing.T) {
	rootDir, err := findRepoRoot()
	if err != nil {
		t.Fatalf("find repo root: %v", err)
	}
	v := &validator{rootDir: rootDir}
	if err := v.activeWorkflowsAvoidStaleControlPlaneSurfaces(); err != nil {
		t.Fatalf("repo should not retain stale workflow control-plane surfaces: %v", err)
	}
}
