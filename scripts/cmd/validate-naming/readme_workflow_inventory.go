package main

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"slices"
	"sort"
	"strings"
)

// readmeWorkflowInventoryUnique verifies that the README workflow inventory
// tables enumerate each workflow exactly once and that the set of enumerated
// workflows matches the actual files on disk. This guards against the LLM
// README generator emitting duplicate rows or stale/missing entries.
func (v *validator) readmeWorkflowInventoryUnique() error {
	rows, err := v.readmeWorkflowInventoryRows()
	if err != nil {
		return err
	}
	counts := map[string]int{}
	for name := range rows {
		counts[name] = 1
	}

	readmePath := filepath.Join(v.rootDir, "README.md")
	b, err := os.ReadFile(readmePath)
	if err != nil {
		return fmt.Errorf("read README.md: %w", err)
	}
	rowRe := regexp.MustCompile("(?m)^\\| `([^`]+\\.ya?ml)` \\|")
	for _, m := range rowRe.FindAllStringSubmatch(string(b), -1) {
		counts[m[1]]++
	}

	var dups []string
	listed := map[string]bool{}
	for name, c := range counts {
		listed[name] = true
		if c > 2 {
			dups = append(dups, fmt.Sprintf("%s (x%d)", name, c-1))
		}
	}
	if len(dups) > 0 {
		sort.Strings(dups)
		return fmt.Errorf("README workflow inventory has duplicate rows: %s", strings.Join(dups, ", "))
	}

	actual, err := v.workflowFileSet()
	if err != nil {
		return err
	}

	var missing []string // on disk but not in README
	for name := range actual {
		if !listed[name] {
			missing = append(missing, name)
		}
	}
	var extra []string // in README but no such file
	for name := range listed {
		if !actual[name] {
			extra = append(extra, name)
		}
	}
	if len(missing) > 0 || len(extra) > 0 {
		sort.Strings(missing)
		sort.Strings(extra)
		return fmt.Errorf("README workflow inventory out of sync with disk (missing: [%s]; extra: [%s])", strings.Join(missing, ", "), strings.Join(extra, ", "))
	}
	return nil
}

func (v *validator) readmeWorkflowInventoryRows() (map[string]string, error) {
	readmePath := filepath.Join(v.rootDir, "README.md")
	b, err := os.ReadFile(readmePath)
	if err != nil {
		return nil, fmt.Errorf("read README.md: %w", err)
	}
	rowRe := regexp.MustCompile("(?m)^\\| `([^`]+\\.ya?ml)` \\| ([^|]+) \\|")
	rows := map[string]string{}
	for _, m := range rowRe.FindAllStringSubmatch(string(b), -1) {
		if _, exists := rows[m[1]]; exists {
			continue
		}
		rows[m[1]] = strings.Join(strings.Fields(m[2]), " ")
	}
	if len(rows) == 0 {
		return nil, fmt.Errorf("README.md contains no workflow inventory rows")
	}
	return rows, nil
}

func (v *validator) workflowFileSet() (map[string]bool, error) {
	workflowsDir := filepath.Join(v.rootDir, ".github", "workflows")
	actual := map[string]bool{}
	walkErr := filepath.WalkDir(workflowsDir, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() || (!strings.HasSuffix(d.Name(), ".yml") && !strings.HasSuffix(d.Name(), ".yaml")) {
			return nil
		}
		rel, relErr := filepath.Rel(workflowsDir, path)
		if relErr != nil {
			return relErr
		}
		actual[filepath.ToSlash(rel)] = true
		return nil
	})
	if walkErr != nil {
		return nil, fmt.Errorf("walk workflows dir: %w", walkErr)
	}
	return actual, nil
}

func (v *validator) readmeWorkflowInventoryTriggers() error {
	rows, err := v.readmeWorkflowInventoryRows()
	if err != nil {
		return err
	}

	var mismatches []string
	for name, readmeTrigger := range rows {
		workflowPath := filepath.Join(v.rootDir, ".github", "workflows", filepath.FromSlash(name))
		body, err := os.ReadFile(workflowPath)
		if err != nil {
			return fmt.Errorf("read workflow %s: %w", name, err)
		}
		expected := workflowTriggerLabel(string(body))
		if normalizeTriggerLabel(readmeTrigger) != expected {
			mismatches = append(mismatches, fmt.Sprintf("%s README=%q actual=%q", name, readmeTrigger, expected))
		}
	}
	if len(mismatches) > 0 {
		sort.Strings(mismatches)
		return fmt.Errorf("README workflow trigger labels out of sync: %s", strings.Join(mismatches, "; "))
	}
	return nil
}

func workflowTriggerLabel(body string) string {
	triggers := workflowTriggers(body)
	for i, trigger := range triggers {
		if trigger == "workflow_dispatch" {
			triggers[i] = "manual"
		}
	}
	sortTriggers(triggers)
	return strings.Join(triggers, ", ")
}

func normalizeTriggerLabel(label string) string {
	var triggers []string
	for _, trigger := range strings.Split(label, ",") {
		trigger = strings.TrimSpace(trigger)
		if trigger != "" {
			triggers = append(triggers, trigger)
		}
	}
	sortTriggers(triggers)
	return strings.Join(triggers, ", ")
}

func workflowTriggers(body string) []string {
	onBlock := extractOnBlock(body)
	if onBlock == "" {
		return nil
	}

	seen := map[string]bool{}
	var triggers []string
	add := func(trigger string) {
		trigger = strings.TrimSpace(strings.Trim(trigger, "[]'\""))
		if trigger == "" || seen[trigger] {
			return
		}
		seen[trigger] = true
		triggers = append(triggers, trigger)
	}

	keyRe := regexp.MustCompile(`^  ([A-Za-z_][A-Za-z0-9_-]*):\s*`)
	for _, line := range strings.Split(onBlock, "\n") {
		if m := keyRe.FindStringSubmatch(line); len(m) == 2 {
			add(m[1])
			continue
		}
		if strings.HasPrefix(line, "  - ") {
			add(strings.TrimPrefix(line, "  - "))
			continue
		}
		if !strings.HasPrefix(line, "  ") || strings.HasPrefix(line, "   ") {
			continue
		}
		scalar := strings.TrimSpace(line)
		if scalar == "" || strings.HasPrefix(scalar, "#") {
			continue
		}
		if strings.HasPrefix(scalar, "[") && strings.HasSuffix(scalar, "]") {
			for _, part := range strings.Split(strings.Trim(scalar, "[]"), ",") {
				add(part)
			}
			continue
		}
		if !strings.Contains(scalar, ":") {
			add(scalar)
		}
	}
	return triggers
}

func sortTriggers(triggers []string) {
	rank := map[string]int{
		"push":                0,
		"pull_request_review": 1,
		"pull_request":        2,
		"pull_request_target": 3,
		"issues":              4,
		"issue_comment":       5,
		"deployment_status":   6,
		"deployment":          7,
		"workflow_run":        8,
		"check_suite":         9,
		"repository_dispatch": 10,
		"workflow_call":       11,
		"manual":              12,
	}
	slices.SortStableFunc(triggers, func(a, b string) int {
		ra, okA := rank[a]
		rb, okB := rank[b]
		if okA && okB {
			return ra - rb
		}
		if okA {
			return -1
		}
		if okB {
			return 1
		}
		return strings.Compare(a, b)
	})
}
