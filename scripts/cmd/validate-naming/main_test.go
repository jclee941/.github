package main

import (
	"testing"
)

func TestExtractYamlPaths(t *testing.T) {
	content := `on:
  push:
    branches: [master]
    paths:
      - '.github/workflows/**'
      - '.github/dependabot.yml'
      - '.github/ISSUE_TEMPLATE/**'
  workflow_dispatch:
`
	paths := extractYamlPaths(content)
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
