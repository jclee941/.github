package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestDocsUseCurrentAppRequiredChecksDetectsLegacyRequiredChecks(t *testing.T) {
	tmpDir := t.TempDir()
	docsDir := filepath.Join(tmpDir, "docs")
	if err := os.MkdirAll(docsDir, 0o755); err != nil {
		t.Fatalf("mkdir docs: %v", err)
	}
	if err := os.WriteFile(filepath.Join(tmpDir, "README.md"), []byte("# ok\n"), 0o644); err != nil {
		t.Fatalf("write readme: %v", err)
	}
	bad := "Required checks: pr-checks / Check PR Title, Gitleaks / scan\n"
	if err := os.WriteFile(filepath.Join(docsDir, "architecture.md"), []byte(bad), 0o644); err != nil {
		t.Fatalf("write doc: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	err := v.docsUseCurrentAppRequiredChecks()
	if err == nil {
		t.Fatal("expected legacy required check documentation to be flagged")
	}
	if !strings.Contains(err.Error(), "docs/architecture.md") {
		t.Fatalf("error should identify offending doc, got: %v", err)
	}
}

func TestDocsUseCurrentAppRequiredChecksCoversContributingTemplatesAndPrTemplate(t *testing.T) {
	cases := []struct {
		name string
		file string
	}{
		{name: "root contributing", file: "CONTRIBUTING.md"},
		{name: "template contributing", file: "templates/CONTRIBUTING.md"},
		{name: "pull request template", file: ".github/PULL_REQUEST_TEMPLATE.md"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			tmpDir := t.TempDir()
			for _, dir := range []string{"docs", "templates", ".github"} {
				if err := os.MkdirAll(filepath.Join(tmpDir, dir), 0o755); err != nil {
					t.Fatalf("mkdir %s: %v", dir, err)
				}
			}
			for _, file := range []string{"README.md", "CONTRIBUTING.md", "templates/CONTRIBUTING.md", ".github/PULL_REQUEST_TEMPLATE.md"} {
				if err := os.WriteFile(filepath.Join(tmpDir, file), []byte("# ok\n"), 0o644); err != nil {
					t.Fatalf("write %s: %v", file, err)
				}
			}
			bad := "Required checks: actionlint remains advisory\n"
			if err := os.WriteFile(filepath.Join(tmpDir, tc.file), []byte(bad), 0o644); err != nil {
				t.Fatalf("write %s: %v", tc.file, err)
			}

			v := &validator{rootDir: tmpDir}
			err := v.docsUseCurrentAppRequiredChecks()
			if err == nil {
				t.Fatalf("expected stale required-check guidance in %s to be flagged", tc.file)
			}
			if !strings.Contains(err.Error(), tc.file) {
				t.Fatalf("error should identify %s, got: %v", tc.file, err)
			}
		})
	}
}

func TestDocsUseCurrentAppRequiredChecksAllowsCurrentAppContexts(t *testing.T) {
	tmpDir := t.TempDir()
	docsDir := filepath.Join(tmpDir, "docs")
	if err := os.MkdirAll(docsDir, 0o755); err != nil {
		t.Fatalf("mkdir docs: %v", err)
	}
	if err := os.WriteFile(filepath.Join(tmpDir, "README.md"), []byte("# ok\n"), 0o644); err != nil {
		t.Fatalf("write readme: %v", err)
	}
	good := "Required: jclee-bot / pr-metadata, jclee-bot / secret-scan, jclee-bot / actionlint\n"
	if err := os.WriteFile(filepath.Join(docsDir, "architecture.md"), []byte(good), 0o644); err != nil {
		t.Fatalf("write doc: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	if err := v.docsUseCurrentAppRequiredChecks(); err != nil {
		t.Fatalf("current App required checks should pass, got: %v", err)
	}
}

func TestDocsUseCurrentAppRequiredChecksDetectsHardcodedManagedRepoList(t *testing.T) {
	tmpDir := t.TempDir()
	docsDir := filepath.Join(tmpDir, "docs")
	if err := os.MkdirAll(docsDir, 0o755); err != nil {
		t.Fatalf("mkdir docs: %v", err)
	}
	if err := os.WriteFile(filepath.Join(tmpDir, "README.md"), []byte("# ok\n"), 0o644); err != nil {
		t.Fatalf("write readme: %v", err)
	}
	bad := "| account | blacklist | resume | tmux |\n"
	if err := os.WriteFile(filepath.Join(docsDir, "inventory.md"), []byte(bad), 0o644); err != nil {
		t.Fatalf("write doc: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	err := v.docsUseCurrentAppRequiredChecks()
	if err == nil {
		t.Fatal("expected hardcoded managed repo documentation to be flagged")
	}
	if !strings.Contains(err.Error(), "docs/inventory.md") {
		t.Fatalf("error should identify offending doc, got: %v", err)
	}
}

func TestDocsUseCurrentAppRequiredChecksDetectsStaleAutomationStatusClaims(t *testing.T) {
	// Given
	tmpDir := t.TempDir()
	docsDir := filepath.Join(tmpDir, "docs")
	if err := os.MkdirAll(docsDir, 0o755); err != nil {
		t.Fatalf("mkdir docs: %v", err)
	}
	if err := os.WriteFile(filepath.Join(tmpDir, "README.md"), []byte("# ok\n"), 0o644); err != nil {
		t.Fatalf("write readme: %v", err)
	}
	staleClaims := strings.Join([]string{
		"# Automation enhancement brainstorm",
		"",
		"- sync-secrets still owns a hardcoded repo inventory and is missing a matching _test.go file.",
		"- The automation-standardization status still depends on removed workflow files 20_readme-gen.yml and 22_template-sync.yml.",
	}, "\n")
	docPath := filepath.Join(docsDir, "automation-enhancement-brainstorm.md")
	if err := os.WriteFile(docPath, []byte(staleClaims), 0o644); err != nil {
		t.Fatalf("write stale automation doc: %v", err)
	}

	// When
	v := &validator{rootDir: tmpDir}
	err := v.docsUseCurrentAppRequiredChecks()

	// Then
	if err == nil {
		t.Fatal("expected stale automation-standardization status claims to be flagged")
	}
	if !strings.Contains(err.Error(), "docs/automation-enhancement-brainstorm.md") {
		t.Fatalf("error should identify offending doc, got: %v", err)
	}
}

func TestStaleAutomationStatusDocHitsDetectsEachStaleClaim(t *testing.T) {
	tests := []struct {
		name string
		line string
		want string
	}{
		{
			name: "sync-secrets hardcoded inventory",
			line: "`sync-secrets` still uses a hardcoded managed repo inventory.",
			want: "sync-secrets` still uses a hardcod",
		},
		{
			name: "sync-secrets missing test",
			line: "`sync-secrets` has no _test.go coverage.",
			want: "sync-secrets` has no _test.go",
		},
		{
			name: "repo-review missing test",
			line: "`repo-review` is missing _test.go coverage.",
			want: "repo-review` is missing _test.go",
		},
		{
			name: "removed readme workflow",
			line: "removed workflow `20_readme-gen.yml` still appears in the status table.",
			want: "20_readme-gen.yml",
		},
		{
			name: "removed template workflow",
			line: "removed workflow `22_template-sync.yml` still appears in the status table.",
			want: "22_template-sync.yml",
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			hits := staleAutomationStatusDocHits(tc.line)
			if len(hits) != 1 {
				t.Fatalf("staleAutomationStatusDocHits(%q) returned %d hits, want 1: %#v", tc.line, len(hits), hits)
			}
			if !strings.Contains(hits[0].text, tc.want) {
				t.Fatalf("hit text = %q, want substring %q", hits[0].text, tc.want)
			}
		})
	}
}

func TestStaleAutomationStatusDocHitsAllowsCurrentStatusClaims(t *testing.T) {
	lines := []string{
		"`sync-secrets` no longer hardcodes inventory and now derives repos from config/repos.yaml.",
		"`sync-secrets` has `_test.go` coverage.",
		"`repo-review` has `_test.go` coverage.",
		"`20_readme-gen.yml` and `22_template-sync.yml` are absent from the current workflow set.",
	}
	for _, line := range lines {
		if hits := staleAutomationStatusDocHits(line); len(hits) != 0 {
			t.Fatalf("staleAutomationStatusDocHits(%q) returned false-positive hits: %#v", line, hits)
		}
	}
}

func TestDocsUseCurrentAppRequiredChecksDetectsMultilineManagedRepoList(t *testing.T) {
	tmpDir := t.TempDir()
	docsDir := filepath.Join(tmpDir, "docs")
	if err := os.MkdirAll(docsDir, 0o755); err != nil {
		t.Fatalf("mkdir docs: %v", err)
	}
	if err := os.WriteFile(filepath.Join(tmpDir, "README.md"), []byte("# ok\n"), 0o644); err != nil {
		t.Fatalf("write readme: %v", err)
	}
	bad := "- account\n- blacklist\n- resume\n- tmux\n"
	if err := os.WriteFile(filepath.Join(docsDir, "inventory.md"), []byte(bad), 0o644); err != nil {
		t.Fatalf("write doc: %v", err)
	}

	v := &validator{rootDir: tmpDir}
	if err := v.docsUseCurrentAppRequiredChecks(); err == nil {
		t.Fatal("expected multiline managed repo documentation to be flagged")
	}
}

func TestDocsUseCurrentAppRequiredChecksRepoClean(t *testing.T) {
	rootDir, err := findRepoRoot()
	if err != nil {
		t.Fatalf("find repo root: %v", err)
	}
	v := &validator{rootDir: rootDir}
	if err := v.docsUseCurrentAppRequiredChecks(); err != nil {
		t.Fatalf("repo docs should not advertise legacy required checks: %v", err)
	}
}
