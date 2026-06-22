package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestGoCommandsDeriveManagedRepoInventoryFromConfigDetectsHardcodedRepos(t *testing.T) {
	tmpDir := t.TempDir()
	cmdDir := filepath.Join(tmpDir, "scripts", "cmd", "bad")
	if err := os.MkdirAll(cmdDir, 0o755); err != nil {
		t.Fatalf("mkdir cmd dir: %v", err)
	}
	bad := `package main

var repos = []string{
	"resume",
	"tmux",
	"hycu",
}
`
	if err := os.WriteFile(filepath.Join(cmdDir, "main.go"), []byte(bad), 0o644); err != nil {
		t.Fatalf("write Go command: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	err := v.goCommandsDeriveManagedRepoInventoryFromConfig()
	if err == nil {
		t.Fatal("expected hardcoded managed repo inventory to be flagged")
	}
	if !strings.Contains(err.Error(), "scripts/cmd/bad/main.go") {
		t.Fatalf("error should identify offending Go command, got: %v", err)
	}
}

func TestGoCommandsDeriveManagedRepoInventoryFromConfigRepoClean(t *testing.T) {
	rootDir, err := findRepoRoot()
	if err != nil {
		t.Fatalf("find repo root: %v", err)
	}
	v := &validator{rootDir: rootDir}
	if err := v.goCommandsDeriveManagedRepoInventoryFromConfig(); err != nil {
		t.Fatalf("repo Go commands should derive managed repo inventory: %v", err)
	}
}
