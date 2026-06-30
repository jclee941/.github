package main

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

var mermaidDirectiveRe = regexp.MustCompile(`^\s*(flowchart|graph|sequenceDiagram|classDiagram|stateDiagram(?:-v2)?|erDiagram|journey|gantt|pie|mindmap|timeline)\b`)

const maxDisplayedFindings = 20

type finding struct {
	path string
	line int
	text string
}

func scanRepoDocs(root string) ([]finding, error) {
	var findings []finding
	err := filepath.WalkDir(root, func(path string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() {
			if shouldSkipDir(entry.Name()) {
				return filepath.SkipDir
			}
			return nil
		}
		if !strings.EqualFold(filepath.Ext(entry.Name()), ".md") {
			return nil
		}
		fileFindings, err := scanMarkdownFile(root, path)
		if err != nil {
			return err
		}
		findings = append(findings, fileFindings...)
		return nil
	})
	if err != nil {
		return nil, fmt.Errorf("walk markdown docs: %w", err)
	}
	return findings, nil
}

func scanMarkdownFile(root, path string) ([]finding, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read markdown %s: %w", path, err)
	}
	rel, err := filepath.Rel(root, path)
	if err != nil {
		rel = path
	}

	var findings []finding
	for i, line := range strings.Split(string(content), "\n") {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "```mermaid") {
			findings = append(findings, finding{path: rel, line: i + 1, text: "raw Mermaid fenced block"})
			continue
		}
		if mermaidDirectiveRe.MatchString(trimmed) {
			findings = append(findings, finding{path: rel, line: i + 1, text: trimmed})
		}
	}
	return findings, nil
}

func shouldSkipDir(name string) bool {
	switch name {
	case ".git", ".hg", ".svn", ".venv", ".omo", "node_modules", "vendor", "dist", "build", "_site":
		return true
	default:
		return false
	}
}

func formatFindings(findings []finding) string {
	displayed := findings
	if len(displayed) > maxDisplayedFindings {
		displayed = displayed[:maxDisplayedFindings]
	}
	parts := make([]string, 0, len(displayed)+1)
	for _, hit := range displayed {
		parts = append(parts, fmt.Sprintf("%s:%d %s", hit.path, hit.line, hit.text))
	}
	if len(findings) > len(displayed) {
		parts = append(parts, fmt.Sprintf("and %d more", len(findings)-len(displayed)))
	}
	return strings.Join(parts, "; ")
}
