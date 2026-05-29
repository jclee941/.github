package main

import (
	"os"
	"path/filepath"
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
	os.MkdirAll(filepath.Join(tmpDir, ".github", "workflows"), 0o755)
	os.WriteFile(filepath.Join(tmpDir, ".github", "workflows", "34_auto-deploy.yml"), []byte(yamlContent), 0o644)

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
