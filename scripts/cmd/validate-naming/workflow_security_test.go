package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestWorkflowRunBlocksUseEnvForDispatchInputsDetectsOffender(t *testing.T) {
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
        default: ""
jobs:
  batch:
    runs-on: ubuntu-latest
    steps:
      - run: |
          echo "${{ inputs.repos }}"
`
	if err := os.WriteFile(filepath.Join(wfDir, "40_bad.yml"), []byte(bad), 0o644); err != nil {
		t.Fatalf("write bad workflow: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	err := v.workflowRunBlocksUseEnvForDispatchInputs()
	if err == nil {
		t.Fatal("expected direct workflow_dispatch input interpolation to be flagged")
	}
	if !strings.Contains(err.Error(), "40_bad.yml") {
		t.Fatalf("error should identify offending workflow, got: %v", err)
	}
}

func TestDirectRunBlockInterpolationsDetectsRunForms(t *testing.T) {
	cases := map[string]string{
		"literal block": `steps:
  - run: |
      echo "${{ inputs.repos }}"
`,
		"literal block no expression whitespace": `steps:
  - run: |
      echo "${{inputs.repos}}"
`,
		"folded block": `steps:
  - run: >-
      echo "${{ inputs.repos }}"
`,
		"inline step": `steps:
  - run: echo "${{ inputs.repos }}"
`,
		"inline key": `steps:
  - name: bad
    run: echo "${{ inputs.repos }}"
`,
		"github event inputs spaced": `steps:
  - run: echo "${{ github.event.inputs.tag }}"
`,
		"github event inputs compact": `steps:
  - run: echo "${{github.event.inputs.tag}}"
`,
		"repo output direct": `steps:
  - run: echo "${{ steps.repo_inventory.outputs.repos }}"
`,
	}
	for name, body := range cases {
		t.Run(name, func(t *testing.T) {
			if hits := directRunBlockInterpolations(body); len(hits) == 0 {
				t.Fatal("expected direct run interpolation to be detected")
			}
		})
	}
}

func TestWorkflowRunBlocksUseEnvForDispatchInputsAllowsEnv(t *testing.T) {
	tmpDir := t.TempDir()
	wfDir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}

	good := `name: good
on:
  workflow_dispatch:
    inputs:
      repos:
        default: ""
jobs:
  batch:
    runs-on: ubuntu-latest
    steps:
      - env:
          INPUT_REPOS: ${{ inputs.repos }}
        run: |
          echo "$INPUT_REPOS"
`
	if err := os.WriteFile(filepath.Join(wfDir, "40_good.yml"), []byte(good), 0o644); err != nil {
		t.Fatalf("write good workflow: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	if err := v.workflowRunBlocksUseEnvForDispatchInputs(); err != nil {
		t.Fatalf("env-mediated workflow input should pass, got: %v", err)
	}
}

func TestWorkflowRunBlocksUseEnvForDispatchInputsRepoClean(t *testing.T) {
	rootDir, err := findRepoRoot()
	if err != nil {
		t.Fatalf("find repo root: %v", err)
	}
	v := &validator{rootDir: rootDir}
	if err := v.workflowRunBlocksUseEnvForDispatchInputs(); err != nil {
		t.Fatalf("repo should not directly interpolate dispatch inputs in run blocks: %v", err)
	}
}

func TestHardcodedManagedRepoInventoryHitsDetectsUnquotedShellAssignment(t *testing.T) {
	protected := map[string]struct{}{
		"account":   {},
		"blacklist": {},
		"resume":    {},
		"tmux":      {},
	}
	body := `steps:
  - run: |
      REPOS=account,blacklist,resume,tmux
      echo "$REPOS"
`
	hits := hardcodedManagedRepoInventoryHits(body, protected)
	if len(hits) != 1 {
		t.Fatalf("expected one unquoted REPOS assignment hit, got %d", len(hits))
	}
	if strings.Join(hits[0].repos, ",") != "account,blacklist,resume,tmux" {
		t.Fatalf("unexpected repos: %v", hits[0].repos)
	}
}
