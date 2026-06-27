package main

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

var staleRequiredCheckDocRes = []*regexp.Regexp{
	regexp.MustCompile(`pr-checks / Check PR Title`),
	regexp.MustCompile(`pr-checks / Check Branch Name`),
	regexp.MustCompile(`브랜치명 OK\?`),
	regexp.MustCompile(`Gitleaks / scan`),
	regexp.MustCompile(`(?i)required.*Gitleaks`),
	regexp.MustCompile(`(?i)actionlint.*advisory`),
	regexp.MustCompile(`(?i)2 required|2 contexts|two App-reported contexts`),
}

var staleAutomationStatusDocRes = []*regexp.Regexp{
	regexp.MustCompile(`(?i)sync-secrets.*(still|continues?|계속|아직).*hardcod`),
	regexp.MustCompile(`(?i)sync-secrets.*(missing|no|없음|미작성).*(?:_test\.go|test coverage|테스트)`),
	regexp.MustCompile(`(?i)repo-review.*(missing|no|없음|미작성).*(?:_test\.go|test coverage|테스트)`),
	regexp.MustCompile(`(?i)(removed workflow|제거된 워크플로우|still|obsolete|stale).*20_readme-gen\.yml|20_readme-gen\.yml.*(still|obsolete|stale|removed workflow|제거된 워크플로우)`),
	regexp.MustCompile(`(?i)(removed workflow|제거된 워크플로우|still|obsolete|stale).*22_template-sync\.yml|22_template-sync\.yml.*(still|obsolete|stale|removed workflow|제거된 워크플로우)`),
}

var nonCanonicalGoCliDocRe = regexp.MustCompile("go run \\./scripts/cmd/[A-Za-z0-9_-]+(?:[^\\n`]*)?")

func (v *validator) docsUseCurrentAppRequiredChecks() error {
	files, err := v.documentationFiles()
	if err != nil {
		return err
	}

	var offenders []string
	for _, file := range files {
		b, readErr := os.ReadFile(file)
		if readErr != nil {
			return fmt.Errorf("read documentation %s: %w", file, readErr)
		}
		for _, hit := range staleRequiredCheckDocHits(string(b)) {
			rel, relErr := filepath.Rel(v.rootDir, file)
			if relErr != nil {
				rel = file
			}
			offenders = append(offenders, fmt.Sprintf("%s:%d contains %q", rel, hit.line, hit.text))
		}
		for _, hit := range staleAutomationStatusDocHits(string(b)) {
			rel, relErr := filepath.Rel(v.rootDir, file)
			if relErr != nil {
				rel = file
			}
			offenders = append(offenders, fmt.Sprintf("%s:%d contains stale automation status %q", rel, hit.line, hit.text))
		}
		for _, hit := range hardcodedManagedRepoDocHits(string(b), managedRepoNameSet()) {
			rel, relErr := filepath.Rel(v.rootDir, file)
			if relErr != nil {
				rel = file
			}
			offenders = append(offenders, fmt.Sprintf("%s:%d lists managed repos %q", rel, hit.line, strings.Join(hit.repos, ",")))
		}
		for _, hit := range nonCanonicalGoCliDocHits(string(b)) {
			rel, relErr := filepath.Rel(v.rootDir, file)
			if relErr != nil {
				rel = file
			}
			offenders = append(offenders, fmt.Sprintf("%s:%d uses non-canonical Go CLI command %q", rel, hit.line, hit.text))
		}
	}
	if len(offenders) > 0 {
		return fmt.Errorf("documentation contains stale or non-canonical automation guidance: %s", strings.Join(offenders, "; "))
	}
	return nil
}

func (v *validator) documentationFiles() ([]string, error) {
	var files []string
	for _, root := range []string{"README.md", "CONTRIBUTING.md", ".github/PULL_REQUEST_TEMPLATE.md", "docs", "templates"} {
		path := filepath.Join(v.rootDir, root)
		info, err := os.Stat(path)
		if err != nil {
			if os.IsNotExist(err) && root != "README.md" {
				continue
			}
			return nil, fmt.Errorf("stat documentation path %s: %w", path, err)
		}
		if !info.IsDir() {
			files = append(files, path)
			continue
		}
		if err := filepath.WalkDir(path, func(file string, d os.DirEntry, walkErr error) error {
			if walkErr != nil {
				return walkErr
			}
			if d.IsDir() || !strings.HasSuffix(d.Name(), ".md") {
				return nil
			}
			files = append(files, file)
			return nil
		}); err != nil {
			return nil, fmt.Errorf("walk documentation path %s: %w", path, err)
		}
	}
	goCliUsageFiles, err := filepath.Glob(filepath.Join(v.rootDir, "scripts", "cmd", "*", "main.go"))
	if err != nil {
		return nil, fmt.Errorf("glob Go CLI usage files: %w", err)
	}
	files = append(files, goCliUsageFiles...)
	return files, nil
}

type staleRequiredCheckDocHit struct {
	line int
	text string
}

func staleRequiredCheckDocHits(content string) []staleRequiredCheckDocHit {
	var hits []staleRequiredCheckDocHit
	for i, line := range strings.Split(content, "\n") {
		for _, re := range staleRequiredCheckDocRes {
			if match := re.FindString(line); match != "" {
				hits = append(hits, staleRequiredCheckDocHit{line: i + 1, text: match})
			}
		}
	}
	return hits
}

func staleAutomationStatusDocHits(content string) []staleRequiredCheckDocHit {
	var hits []staleRequiredCheckDocHit
	for i, line := range strings.Split(content, "\n") {
		for _, re := range staleAutomationStatusDocRes {
			if match := re.FindString(line); match != "" {
				hits = append(hits, staleRequiredCheckDocHit{line: i + 1, text: match})
			}
		}
	}
	return hits
}

func nonCanonicalGoCliDocHits(content string) []staleRequiredCheckDocHit {
	var hits []staleRequiredCheckDocHit
	for i, line := range strings.Split(content, "\n") {
		if match := nonCanonicalGoCliDocRe.FindString(line); match != "" {
			hits = append(hits, staleRequiredCheckDocHit{line: i + 1, text: match})
		}
	}
	return hits
}

func hardcodedManagedRepoDocHits(content string, protected map[string]struct{}) []hardcodedRepoInventoryHit {
	var hits []hardcodedRepoInventoryHit
	lines := strings.Split(content, "\n")
	blockStart := 0
	var block []string
	flush := func() {
		if len(block) == 0 {
			return
		}
		repos := managedReposInShellList(strings.Join(block, "\n"), protected)
		if len(repos) >= 3 {
			hits = append(hits, hardcodedRepoInventoryHit{line: blockStart + 1, repos: repos})
		}
		block = nil
	}
	for i, line := range lines {
		if strings.TrimSpace(line) == "" {
			flush()
			blockStart = i + 1
			continue
		}
		if len(block) == 0 {
			blockStart = i
		}
		block = append(block, line)
	}
	flush()
	return hits
}
