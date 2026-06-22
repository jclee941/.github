package main

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

var liveRepoDiscoveryRe = regexp.MustCompile(`\bgh\s+api\s+users/jclee941/repos\b`)

var reposLoopRe = regexp.MustCompile(`(?i)\bfor\s+[A-Z_][A-Z0-9_]*\s+in\s+(\$REPOS|\$\{REPOS\})`)

var reposAssignmentRe = regexp.MustCompile(`\bREPOS=`)

var csvReposLoopRe = regexp.MustCompile(`(?i)\bfor\s+[A-Z_][A-Z0-9_]*\s+in\s+(\$REPOS|\$\{REPOS\})`)

var retiredWorkflowNames = []string{
	"Auto Deploy Workflows",
	"Template Sync",
}

func (v *validator) activeWorkflowsAvoidStaleControlPlaneSurfaces() error {
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
		content := string(b)
		for _, hit := range liveRepoDiscoveryHits(content) {
			offenders = append(offenders, fmt.Sprintf("%s:%d uses live repo discovery instead of config/repos.yaml", filepath.Base(file), hit))
		}
		for _, hit := range retiredWorkflowDependencyHits(content) {
			offenders = append(offenders, fmt.Sprintf("%s references retired workflow %q", filepath.Base(file), hit))
		}
		for _, hit := range undefinedReposLoopHits(content) {
			offenders = append(offenders, fmt.Sprintf("%s:%d loops over REPOS before assigning it in the same run block", filepath.Base(file), hit))
		}
		for _, hit := range unsplitCSVReposLoopHits(content) {
			offenders = append(offenders, fmt.Sprintf("%s:%d loops over comma-delimited REPOS without splitting it", filepath.Base(file), hit))
		}
		offenders = append(offenders, matrixRepoOutputHits(filepath.Base(file), content)...)
		offenders = append(offenders, unsafeWorkflowMutationHits(filepath.Base(file), content)...)
		offenders = append(offenders, workflowOwnedGitOpsHits(filepath.Base(file), content)...)
	}
	if len(offenders) > 0 {
		return fmt.Errorf("active workflows retain stale control-plane surfaces: %s", strings.Join(offenders, "; "))
	}
	return nil
}

func matrixRepoOutputHits(fileName string, content string) []string {
	if fileName != "31_repo-health.yml" {
		return nil
	}
	if strings.Contains(content, "fromJson(needs.discover-repos.outputs.repos)") &&
		!strings.Contains(content, "jq -R -c 'split(\",\")'") {
		return []string{fileName + " must emit compact JSON for fromJson matrix repos"}
	}
	return nil
}

func unsplitCSVReposLoopHits(content string) []int {
	var hits []int
	for i, line := range strings.Split(content, "\n") {
		if csvReposLoopRe.MatchString(line) {
			hits = append(hits, i+1)
		}
	}
	return hits
}

func unsafeWorkflowMutationHits(fileName string, content string) []string {
	var hits []string
	if fileName == "40_repo-review-batch.yml" && strings.Contains(content, "Close stale bot-review issues") {
		if !strings.Contains(content, "if: inputs.dry_run != true") {
			hits = append(hits, fileName+" closes stale issues without honoring dry_run")
		}
	}
	if fileName == "60_ci-auto-heal.yml" {
		for _, token := range []string{
			"CLIPROXY_API_KEY:",
			"gh repo clone",
			"git push origin",
			"gh pr create",
		} {
			if strings.Contains(content, token) {
				hits = append(hits, fmt.Sprintf("%s retains unsafe auto-heal token/command surface %q", fileName, token))
			}
		}
	}
	return hits
}

func workflowOwnedGitOpsHits(fileName string, content string) []string {
	retiredGitOpsWorkflows := map[string]struct{}{
		"01_branch-to-pr.yml":          {},
		"12_dependabot-auto-merge.yml": {},
		"13_pr-auto-merge.yml":         {},
	}
	var hits []string
	for _, token := range []string{
		"gh pr create",
		"gh pr merge",
		"gh pr review",
	} {
		if strings.Contains(content, token) {
			hits = append(hits, fmt.Sprintf("%s retains workflow-owned GitOps mutation %q", fileName, token))
		}
	}
	if _, retired := retiredGitOpsWorkflows[fileName]; !retired {
		return hits
	}
	for _, token := range []string{
		"pull_request:",
		"pull_request_review:",
		"push:",
	} {
		if strings.Contains(content, token) {
			hits = append(hits, fmt.Sprintf("%s retains workflow-owned GitOps surface %q", fileName, token))
		}
	}
	return hits
}

func liveRepoDiscoveryHits(content string) []int {
	var hits []int
	for i, line := range strings.Split(content, "\n") {
		if liveRepoDiscoveryRe.MatchString(line) {
			hits = append(hits, i+1)
		}
	}
	return hits
}

func retiredWorkflowDependencyHits(content string) []string {
	var hits []string
	for _, name := range retiredWorkflowNames {
		if strings.Contains(content, name) {
			hits = append(hits, name)
		}
	}
	return hits
}

func undefinedReposLoopHits(content string) []int {
	lines := strings.Split(content, "\n")
	inRun := false
	runIndent := 0
	sawReposAssignment := false
	var hits []int

	for i, line := range lines {
		trimmed := strings.TrimLeft(line, " ")
		indent := len(line) - len(trimmed)
		if inRun {
			if strings.TrimSpace(line) == "" || indent > runIndent {
				sawReposAssignment, hits = checkReposLoopLine(i+1, line, sawReposAssignment, hits)
				continue
			}
			inRun = false
			sawReposAssignment = false
		}

		runValue, ok := runDirectiveValue(trimmed)
		if !ok {
			continue
		}
		if strings.HasPrefix(runValue, "|") || strings.HasPrefix(runValue, ">") {
			inRun = true
			runIndent = indent
			sawReposAssignment = false
			continue
		}
		_, hits = checkReposLoopLine(i+1, line, false, hits)
	}
	return hits
}

func checkReposLoopLine(lineNumber int, line string, sawAssignment bool, hits []int) (bool, []int) {
	if reposAssignmentRe.MatchString(line) {
		sawAssignment = true
	}
	if reposLoopRe.MatchString(line) && !sawAssignment {
		hits = append(hits, lineNumber)
	}
	return sawAssignment, hits
}
