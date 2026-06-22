package main

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"

	repoinventory "github.com/jclee941/.github/scripts/internal/repos"
)

var forbiddenRunInterpolationRe = regexp.MustCompile(`\$\{\{\s*(inputs|github\.event\.inputs)\.`)

var forbiddenRunOutputInterpolationRe = regexp.MustCompile(`\$\{\{\s*steps\.repo_inventory\.outputs\.repos\b`)

var shellRepoAssignmentRe = regexp.MustCompile(`(?i)\b[A-Z_]*REPOS[A-Z_]*=("[^"]+"|'[^']+'|[A-Za-z0-9_,.-]+)`)

var shellRepoArrayRe = regexp.MustCompile(`(?is)\b[A-Z_]*REPOS[A-Z_]*=\((.*?)\)`)

var yamlRepoDefaultRe = regexp.MustCompile(`(?i)^\s*default:\s*(.+)$`)

func (v *validator) workflowRunBlocksUseEnvForDispatchInputs() error {
	files, err := v.workflowFiles()
	if err != nil {
		return err
	}

	var offenders []string
	for _, file := range files {
		b, readErr := os.ReadFile(file)
		if readErr != nil {
			return fmt.Errorf("read workflow %s: %w", file, readErr)
		}
		for _, hit := range directRunBlockInterpolations(string(b)) {
			offenders = append(offenders, fmt.Sprintf("%s:%d uses %q", filepath.Base(file), hit.line, hit.token))
		}
	}
	if len(offenders) > 0 {
		return fmt.Errorf("workflow run blocks interpolate dispatch inputs or derived repo outputs directly; pass them through env first: %s", strings.Join(offenders, "; "))
	}
	return nil
}

func (v *validator) workflowsDeriveManagedRepoInventoryFromConfig() error {
	files, err := v.workflowFiles()
	if err != nil {
		return err
	}

	protected := managedRepoNameSet()
	var offenders []string
	for _, file := range files {
		b, readErr := os.ReadFile(file)
		if readErr != nil {
			return fmt.Errorf("read workflow %s: %w", file, readErr)
		}
		for _, hit := range hardcodedManagedRepoInventoryHits(string(b), protected) {
			offenders = append(offenders, fmt.Sprintf("%s:%d assigns managed repos %q", filepath.Base(file), hit.line, strings.Join(hit.repos, ",")))
		}
	}
	if len(offenders) > 0 {
		return fmt.Errorf("workflow run blocks hardcode managed repo inventory; derive it from config/repos.yaml instead: %s", strings.Join(offenders, "; "))
	}
	return nil
}

func (v *validator) workflowFiles() ([]string, error) {
	var files []string
	workflowsDir := filepath.Join(v.rootDir, ".github", "workflows")
	err := filepath.WalkDir(workflowsDir, func(path string, d os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if d.IsDir() {
			return nil
		}
		if strings.HasSuffix(d.Name(), ".yml") || strings.HasSuffix(d.Name(), ".yaml") {
			files = append(files, path)
		}
		return nil
	})
	if err != nil {
		return nil, fmt.Errorf("walk workflows dir: %w", err)
	}
	sort.Strings(files)
	return files, nil
}

type runInterpolationHit struct {
	line  int
	token string
}

type hardcodedRepoInventoryHit struct {
	line  int
	repos []string
}

func directRunBlockInterpolations(content string) []runInterpolationHit {
	lines := strings.Split(content, "\n")
	inRun := false
	runIndent := 0
	var hits []runInterpolationHit

	for i, line := range lines {
		trimmed := strings.TrimLeft(line, " ")
		indent := len(line) - len(trimmed)
		if inRun {
			if strings.TrimSpace(line) == "" || indent > runIndent {
				hits = append(hits, forbiddenInterpolationsInLine(i+1, line)...)
				continue
			}
			inRun = false
		}

		runValue, ok := runDirectiveValue(trimmed)
		if !ok {
			continue
		}
		if strings.HasPrefix(runValue, "|") || strings.HasPrefix(runValue, ">") {
			inRun = true
			runIndent = indent
			continue
		}
		hits = append(hits, forbiddenInterpolationsInLine(i+1, line)...)
	}
	return hits
}

func hardcodedManagedRepoInventoryHits(content string, protected map[string]struct{}) []hardcodedRepoInventoryHit {
	lines := strings.Split(content, "\n")
	inRun := false
	runIndent := 0
	var hits []hardcodedRepoInventoryHit

	hits = append(hits, hardcodedManagedRepoDefaults(lines, protected)...)
	hits = append(hits, hardcodedManagedRepoArrays(content, protected)...)

	for i, line := range lines {
		trimmed := strings.TrimLeft(line, " ")
		indent := len(line) - len(trimmed)
		if inRun {
			if strings.TrimSpace(line) == "" || indent > runIndent {
				hits = append(hits, hardcodedManagedRepoAssignmentsInLine(i+1, line, protected)...)
				continue
			}
			inRun = false
		}

		runValue, ok := runDirectiveValue(trimmed)
		if !ok {
			continue
		}
		if strings.HasPrefix(runValue, "|") || strings.HasPrefix(runValue, ">") {
			inRun = true
			runIndent = indent
			continue
		}
		hits = append(hits, hardcodedManagedRepoAssignmentsInLine(i+1, line, protected)...)
	}
	return hits
}

func runDirectiveValue(trimmed string) (string, bool) {
	for _, prefix := range []string{"- run:", "run:"} {
		if strings.HasPrefix(trimmed, prefix) {
			return strings.TrimSpace(strings.TrimPrefix(trimmed, prefix)), true
		}
	}
	return "", false
}

func forbiddenInterpolationsInLine(lineNumber int, line string) []runInterpolationHit {
	var hits []runInterpolationHit
	for _, re := range []*regexp.Regexp{forbiddenRunInterpolationRe, forbiddenRunOutputInterpolationRe} {
		for _, token := range re.FindAllString(line, -1) {
			hits = append(hits, runInterpolationHit{line: lineNumber, token: token})
		}
	}
	return hits
}

func hardcodedManagedRepoAssignmentsInLine(lineNumber int, line string, protected map[string]struct{}) []hardcodedRepoInventoryHit {
	var hits []hardcodedRepoInventoryHit
	for _, match := range shellRepoAssignmentRe.FindAllStringSubmatch(line, -1) {
		repos := managedReposInShellList(strings.Trim(match[1], `"'`), protected)
		if len(repos) >= 3 {
			hits = append(hits, hardcodedRepoInventoryHit{line: lineNumber, repos: repos})
		}
	}
	return hits
}

func hardcodedManagedRepoArrays(content string, protected map[string]struct{}) []hardcodedRepoInventoryHit {
	var hits []hardcodedRepoInventoryHit
	for _, loc := range shellRepoArrayRe.FindAllStringSubmatchIndex(content, -1) {
		repos := managedReposInShellList(content[loc[2]:loc[3]], protected)
		if len(repos) >= 3 {
			line := strings.Count(content[:loc[0]], "\n") + 1
			hits = append(hits, hardcodedRepoInventoryHit{line: line, repos: repos})
		}
	}
	return hits
}

func hardcodedManagedRepoDefaults(lines []string, protected map[string]struct{}) []hardcodedRepoInventoryHit {
	var hits []hardcodedRepoInventoryHit
	for i, line := range lines {
		match := yamlRepoDefaultRe.FindStringSubmatch(line)
		if match == nil {
			continue
		}
		value := strings.TrimSpace(match[1])
		if strings.HasPrefix(value, "|") || strings.HasPrefix(value, ">") {
			value = yamlIndentedBlock(lines, i)
		}
		repos := managedReposInShellList(strings.Trim(value, `"'[]`), protected)
		if len(repos) >= 3 {
			hits = append(hits, hardcodedRepoInventoryHit{line: i + 1, repos: repos})
		}
	}
	return hits
}

func yamlIndentedBlock(lines []string, start int) string {
	baseIndent := leadingSpaces(lines[start])
	var block []string
	for _, line := range lines[start+1:] {
		if strings.TrimSpace(line) == "" {
			continue
		}
		if leadingSpaces(line) <= baseIndent {
			break
		}
		block = append(block, strings.TrimSpace(line))
	}
	return strings.Join(block, "\n")
}

func leadingSpaces(line string) int {
	return len(line) - len(strings.TrimLeft(line, " "))
}

func managedReposInShellList(value string, protected map[string]struct{}) []string {
	seen := map[string]struct{}{}
	var repos []string
	for _, token := range strings.FieldsFunc(value, func(r rune) bool {
		return strings.ContainsRune(", \t\n()[]{}\"'", r)
	}) {
		if _, ok := protected[token]; !ok {
			continue
		}
		if _, ok := seen[token]; ok {
			continue
		}
		seen[token] = struct{}{}
		repos = append(repos, token)
	}
	sort.Strings(repos)
	return repos
}

func managedRepoNameSet() map[string]struct{} {
	protected := map[string]struct{}{}
	for _, repo := range repoinventory.ProtectedRepos() {
		protected[repo.Name] = struct{}{}
	}
	return protected
}
