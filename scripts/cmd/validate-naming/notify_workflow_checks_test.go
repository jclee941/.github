package main

import (
	"os"
	"path/filepath"
	"testing"
)

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
