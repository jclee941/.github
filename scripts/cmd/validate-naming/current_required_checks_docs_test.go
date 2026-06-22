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
