package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestActiveWorkflowsAvoidStaleControlPlaneSurfacesDetectsPrettyMatrixJSON(t *testing.T) {
	tmpDir := t.TempDir()
	wfDir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}

	bad := `name: Repository Health Check
on:
  workflow_dispatch:
jobs:
  discover-repos:
    outputs:
      repos: ${{ steps.discover.outputs.repos }}
    runs-on: ubuntu-latest
    steps:
      - id: discover
        run: |
          repos=$(cd scripts && go run ./cmd/repo-review --print-default-repos | jq -R 'split(",")')
          echo "repos=$repos" >> "$GITHUB_OUTPUT"
  check-health:
    needs: discover-repos
    strategy:
      matrix:
        repo: ${{ fromJson(needs.discover-repos.outputs.repos) }}
`
	if err := os.WriteFile(filepath.Join(wfDir, "31_repo-health.yml"), []byte(bad), 0o644); err != nil {
		t.Fatalf("write bad workflow: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	if err := v.activeWorkflowsAvoidStaleControlPlaneSurfaces(); err == nil {
		t.Fatal("expected pretty matrix JSON output to be flagged")
	}
}

func TestActiveWorkflowsAvoidStaleControlPlaneSurfacesDetectsRepoReviewDryRunBypass(t *testing.T) {
	tmpDir := t.TempDir()
	wfDir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}

	bad := `name: Repo Review Batch
on:
  workflow_dispatch:
jobs:
  batch:
    runs-on: ubuntu-latest
    steps:
      - name: Close stale bot-review issues
        run: gh issue close 1
`
	if err := os.WriteFile(filepath.Join(wfDir, "40_repo-review-batch.yml"), []byte(bad), 0o644); err != nil {
		t.Fatalf("write bad workflow: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	if err := v.activeWorkflowsAvoidStaleControlPlaneSurfaces(); err == nil {
		t.Fatal("expected dry_run bypass to be flagged")
	}
}

func TestActiveWorkflowsAvoidStaleControlPlaneSurfacesDetectsUnsafeAutoHeal(t *testing.T) {
	tmpDir := t.TempDir()
	wfDir := filepath.Join(tmpDir, ".github", "workflows")
	if err := os.MkdirAll(wfDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}

	bad := `name: CI Auto-Heal
on:
  workflow_run:
    workflows: ["Sanity"]
    types: [completed]
jobs:
  heal:
    runs-on: ubuntu-latest
    steps:
      - env:
          CLIPROXY_API_KEY: ${{ secrets.CLIPROXY_API_KEY }}
        run: |
          gh repo clone jclee941/example /tmp/example
          git push origin branch
          gh pr create -R jclee941/example
`
	if err := os.WriteFile(filepath.Join(wfDir, "60_ci-auto-heal.yml"), []byte(bad), 0o644); err != nil {
		t.Fatalf("write bad workflow: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	err := v.activeWorkflowsAvoidStaleControlPlaneSurfaces()
	if err == nil {
		t.Fatal("expected unsafe auto-heal surface to be flagged")
	}
	for _, want := range []string{"CLIPROXY_API_KEY", "gh repo clone", "git push origin", "gh pr create"} {
		if !strings.Contains(err.Error(), want) {
			t.Fatalf("error should mention %q, got: %v", want, err)
		}
	}
}
