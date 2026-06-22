package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestReadmeUsesJcleeBotAutomationSurfaceDetectsLegacyRow(t *testing.T) {
	tmpDir := t.TempDir()
	readme := "# R\n\n" +
		"### jclee-bot Automation | jclee-bot 자동화\n\n" +
		"운영 자동화는 **GitHub App 중심 운영 모델**을 따릅니다.\n\n" +
		"jclee-bot에의해자동화됨\n\n" +
		"| Workflow File | Trigger | Description |\n" +
		"|---|---|---|\n" +
		"| `37_ci-failure-issues.yml` | workflow_run | legacy |\n"
	if err := os.WriteFile(filepath.Join(tmpDir, "README.md"), []byte(readme), 0o644); err != nil {
		t.Fatalf("write readme: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	err := v.readmeUsesJcleeBotAutomationSurface()
	if err == nil {
		t.Fatal("expected legacy workflow row to be flagged")
	}
	if !strings.Contains(err.Error(), "workflow file inventory row") {
		t.Fatalf("error should name workflow rows, got: %v", err)
	}
}

func TestReadmeUsesJcleeBotAutomationSurfaceDetectsMissingMarker(t *testing.T) {
	tmpDir := t.TempDir()
	readme := "# R\n\n### jclee-bot Automation | jclee-bot 자동화\n"
	if err := os.WriteFile(filepath.Join(tmpDir, "README.md"), []byte(readme), 0o644); err != nil {
		t.Fatalf("write readme: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	err := v.readmeUsesJcleeBotAutomationSurface()
	if err == nil {
		t.Fatal("expected missing automation markers to be flagged")
	}
	if !strings.Contains(err.Error(), "jclee-bot에의해자동화됨") {
		t.Fatalf("error should name the missing marker, got: %v", err)
	}
}

func TestReadmeUsesJcleeBotAutomationSurfaceRepoClean(t *testing.T) {
	rootDir, err := findRepoRoot()
	if err != nil {
		t.Fatalf("find repo root: %v", err)
	}
	v := &validator{rootDir: rootDir}
	if err := v.readmeUsesJcleeBotAutomationSurface(); err != nil {
		t.Fatalf("README should present jclee-bot automation surface: %v", err)
	}
}
