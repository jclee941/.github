package main

import (
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"

	repoinventory "github.com/jclee941/jclee-bot/scripts/internal/repos"
)

func TestScanRepoDocs_detectsRawMermaidFence_whenMarkdownContainsChartBlock(t *testing.T) {
	// Given
	root := t.TempDir()
	writeTestFile(t, root, "README.md", "# Architecture\n\n```mermaid\nflowchart LR\nA --> B\n```\n")

	// When
	findings, err := scanRepoDocs(root)

	// Then
	if err != nil {
		t.Fatalf("scanRepoDocs returned error: %v", err)
	}
	if len(findings) != 2 {
		t.Fatalf("findings length = %d, want 2: %#v", len(findings), findings)
	}
	if findings[0].path != "README.md" || findings[0].line != 3 {
		t.Fatalf("first finding = %#v, want README.md line 3", findings[0])
	}
}

func TestScanRepoDocs_detectsRawMermaidDirective_whenFenceLanguageIsMissing(t *testing.T) {
	// Given
	root := t.TempDir()
	writeTestFile(t, root, "docs/architecture.md", "```\nflowchart TD\nA --> B\n```\n")

	// When
	findings, err := scanRepoDocs(root)

	// Then
	if err != nil {
		t.Fatalf("scanRepoDocs returned error: %v", err)
	}
	if len(findings) != 1 {
		t.Fatalf("findings length = %d, want 1: %#v", len(findings), findings)
	}
	if findings[0].path != filepath.Join("docs", "architecture.md") || findings[0].line != 2 {
		t.Fatalf("finding = %#v, want docs/architecture.md line 2", findings[0])
	}
}

func TestScanRepoDocs_allowsRenderedSvgImage_whenMarkdownReferencesAsset(t *testing.T) {
	// Given
	root := t.TempDir()
	writeTestFile(t, root, "README.md", "![Architecture](./docs/assets/architecture.svg)\n")
	writeTestFile(t, root, "docs/assets/architecture.svg", "<svg xmlns=\"http://www.w3.org/2000/svg\"/>\n")

	// When
	findings, err := scanRepoDocs(root)

	// Then
	if err != nil {
		t.Fatalf("scanRepoDocs returned error: %v", err)
	}
	if len(findings) != 0 {
		t.Fatalf("rendered SVG image should pass, got findings: %#v", findings)
	}
}

func TestScanRepoDocs_skipsOmoEvidenceArtifacts(t *testing.T) {
	// Given
	root := t.TempDir()
	writeTestFile(t, root, ".omo/evidence/remote-readmes/splunk.md", "```mermaid\nflowchart LR\nA --> B\n```\n")
	writeTestFile(t, root, "README.md", "# Clean docs\n")

	// When
	findings, err := scanRepoDocs(root)

	// Then
	if err != nil {
		t.Fatalf("scanRepoDocs returned error: %v", err)
	}
	if len(findings) != 0 {
		t.Fatalf(".omo evidence artifacts should be skipped, got findings: %#v", findings)
	}
}

func TestNormalizeRepoList_usesDeployableInventoryByDefault(t *testing.T) {
	// Given
	allowed := repoinventory.Names(repoinventory.DeployableRepos())

	// When
	got, err := normalizeRepoList("splunk, tmux,splunk", allowed)

	// Then
	if err != nil {
		t.Fatalf("normalizeRepoList returned error: %v", err)
	}
	want := []string{"splunk", "tmux"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("normalizeRepoList = %v, want %v", got, want)
	}
	if strings.Contains(strings.Join(allowed, ","), "jclee-bot") {
		t.Fatalf("downstream deployable inventory must not include source repo: %v", allowed)
	}
}

func TestNormalizeRepoList_rejectsPathLikeRepoName(t *testing.T) {
	// Given
	allowed := repoinventory.Names(repoinventory.DeployableRepos())

	// When
	_, err := normalizeRepoList("../splunk", allowed)

	// Then
	if err == nil {
		t.Fatal("expected path-like repo name to be rejected")
	}
}

func writeTestFile(t *testing.T, root, name, content string) {
	t.Helper()
	path := filepath.Join(root, name)
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("mkdir parent for %s: %v", name, err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("write %s: %v", name, err)
	}
}
