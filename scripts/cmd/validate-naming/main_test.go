package main

import (
	"path/filepath"
	"testing"
)

func TestContains(t *testing.T) {
	if !contains([]string{"a", "b", "c"}, "b") {
		t.Error("expected contains to find 'b'")
	}
	if contains([]string{"a", "b", "c"}, "d") {
		t.Error("expected contains to NOT find 'd'")
	}
}

func TestRequiredStatusChecksMatchWorkflowContexts(t *testing.T) {
	rootDir, err := findRepoRoot()
	if err != nil {
		t.Fatalf("find repo root: %v", err)
	}

	v := &validator{rootDir: rootDir}
	if err := v.requiredStatusChecksMatchWorkflowContexts(); err != nil {
		t.Fatalf("required status checks should match workflow contexts: %v", err)
	}
}

func TestRulesetsManagerFilePointsAtPayloadSource(t *testing.T) {
	v := &validator{rootDir: "/repo"}
	got := filepath.ToSlash(v.rulesetsManagerFile())
	want := "/repo/scripts/cmd/rulesets-manager/payload.go"
	if got != want {
		t.Fatalf("rulesetsManagerFile() = %q, want %q", got, want)
	}
}
