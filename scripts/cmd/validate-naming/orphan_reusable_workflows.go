package main

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

// orphanReusableWorkflows flags reusable workflows (on: workflow_call only)
// that are not called by any local workflow. Such files are dead duplicates
// of active workflows and must be removed to prevent inventory rot.
func (v *validator) orphanReusableWorkflows() error {
	workflowsDir := filepath.Join(v.rootDir, ".github", "workflows")

	// Collect file contents once. Recurse so subdirectory workflows (e.g.
	// security/) and both .yml/.yaml extensions are covered. Keys are paths
	// relative to the workflows dir (e.g. "security/11_pr-review.yml").
	contents := map[string]string{}
	walkErr := filepath.WalkDir(workflowsDir, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			return nil
		}
		if !strings.HasSuffix(d.Name(), ".yml") && !strings.HasSuffix(d.Name(), ".yaml") {
			return nil
		}
		b, readErr := os.ReadFile(path)
		if readErr != nil {
			return fmt.Errorf("read workflow %s: %w", path, readErr)
		}
		rel, relErr := filepath.Rel(workflowsDir, path)
		if relErr != nil {
			return relErr
		}
		contents[filepath.ToSlash(rel)] = string(b)
		return nil
	})
	if walkErr != nil {
		return fmt.Errorf("walk workflows dir: %w", walkErr)
	}

	var orphans []string
	for rel, body := range contents {
		if !isWorkflowCallOnly(body) {
			continue
		}
		base := filepath.Base(rel)
		// Called by any other local workflow? A `uses:` reference ends in the
		// file's base name (e.g. ./.github/workflows/44_x.yml or
		// jclee941/.github/.github/workflows/44_x.yml@ref).
		called := false
		for other, ob := range contents {
			if other == rel {
				continue
			}
			if strings.Contains(ob, "/"+base) {
				called = true
				break
			}
		}
		if !called {
			orphans = append(orphans, base)
		}
	}

	if len(orphans) > 0 {
		sort.Strings(orphans)
		return fmt.Errorf("orphaned reusable workflows (workflow_call-only, no local caller): %s", strings.Join(orphans, ", "))
	}
	return nil
}

// isWorkflowCallOnly reports whether a workflow's on: triggers contain ONLY
// workflow_call (plus the always-allowed manual workflow_dispatch). Every other
// trigger (push/pull_request/schedule/issues/...) means it runs on its own.
func isWorkflowCallOnly(body string) bool {
	onBlock := extractOnBlock(body)
	if onBlock == "" {
		return false
	}
	for _, trig := range []string{"push", "pull_request", "pull_request_target", "schedule", "issues", "issue_comment", "create", "delete", "release", "label", "repository_dispatch"} {
		// Block mapping form: `  push:`
		if regexp.MustCompile(`(?m)^\s+` + regexp.QuoteMeta(trig) + `:`).MatchString(onBlock) {
			return false
		}
		// Inline word form within an array/scalar: `[push, workflow_call]` or
		// `on: push` (extractOnBlock normalizes these onto their own line).
		if regexp.MustCompile(`\b` + regexp.QuoteMeta(trig) + `\b`).MatchString(onBlock) {
			return false
		}
	}
	// workflow_call present as a block mapping or an inline scalar/array word.
	if regexp.MustCompile(`(?m)^\s+workflow_call:`).MatchString(onBlock) {
		return true
	}
	return regexp.MustCompile(`\bworkflow_call\b`).MatchString(onBlock)
}

// extractOnBlock returns the contents of the top-level `on:` mapping block,
// i.e. everything indented under `on:` up to the next top-level key. Returns
// the empty string if no on: block is found.
func extractOnBlock(body string) string {
	lines := strings.Split(body, "\n")
	var out []string
	in := false
	for _, ln := range lines {
		if !in {
			if strings.HasPrefix(ln, "on:") {
				in = true
				// Inline form: `on: [push, workflow_call]` or `on: workflow_call`.
				rest := strings.TrimSpace(strings.TrimPrefix(ln, "on:"))
				if rest != "" {
					out = append(out, "  "+rest)
				}
			}
			continue
		}
		// A non-indented, non-empty line ends the on: block (next top-level key).
		if ln != "" && !strings.HasPrefix(ln, " ") && !strings.HasPrefix(ln, "\t") {
			break
		}
		out = append(out, ln)
	}
	return strings.Join(out, "\n")
}
