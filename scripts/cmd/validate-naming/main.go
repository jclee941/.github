package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"regexp"
	"slices"
	"sort"
	"strconv"
	"strings"
)

// validation checks cross-file invariants for the deployment system.
type validation struct {
	name string
	check func() error
	fix  func() error
}

func main() {
	fixMode := flag.Bool("fix", false, "automatically fix detected issues where possible")
	flag.Parse()

	rootDir, err := findRepoRoot()
	if err != nil {
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}

	v := &validator{rootDir: rootDir}

	validations := []validation{
		{"deploy constants match E2E test", v.deployConstantsMatchE2E, v.fixDeployConstantsMatchE2E},
		{"auto-deploy paths cover extraFiles", v.autoDeployPathsCoverExtraFiles, v.fixAutoDeployPaths},
		{"CODEOWNERS covers extraFiles directories", v.codeownersCoversExtraFiles, v.fixCodeowners},
		{"issue templates follow kebab-case", v.issueTemplatesKebabCase, nil},
		{"workflows follow naming convention", v.workflowsNamingConvention, nil},
		{"extraFiles have allowed extensions", v.extraFilesExtensions, nil},
		{"required status checks match workflow check-run names", v.requiredStatusChecksMatchWorkflowContexts, nil},
		{"notify-on-failure jobs checkout local actions first", v.notifyOnFailureRequiresCheckout, nil},
	}

	failed := 0
	fixed := 0
	for _, val := range validations {
		if err := val.check(); err != nil {
			fmt.Fprintf(os.Stderr, "FAIL: %s: %v\n", val.name, err)
			if *fixMode && val.fix != nil {
				if fixErr := val.fix(); fixErr != nil {
					fmt.Fprintf(os.Stderr, "  -> auto-fix failed: %v\n", fixErr)
				} else {
					fmt.Printf("  -> auto-fixed\n")
					fixed++
					continue
				}
			}
			failed++
		} else {
			fmt.Printf("PASS: %s\n", val.name)
		}
	}

	if fixed > 0 {
		fmt.Printf("\n%d issue(s) auto-fixed. Re-run without --fix to verify.\n", fixed)
	}
	if failed > 0 {
		fmt.Fprintf(os.Stderr, "\n%d validation(s) failed\n", failed)
		os.Exit(1)
	}
	fmt.Println("\nAll validations passed")
}

type validator struct {
	rootDir string
}

func findRepoRoot() (string, error) {
	wd, err := os.Getwd()
	if err != nil {
		return "", err
	}
	current := wd
	for {
		candidate := filepath.Join(current, ".github", "workflows", "03_pr-checks.yml")
		if _, err := os.Stat(candidate); err == nil {
			return current, nil
		}
		parent := filepath.Dir(current)
		if parent == current {
			break
		}
		current = parent
	}
	return "", fmt.Errorf("could not find repo root")
}

// extractGoConst reads a Go file and extracts string constants by name.
func extractGoConst(filePath string, constNames []string) (map[string]string, error) {
	fset := token.NewFileSet()
	f, err := parser.ParseFile(fset, filePath, nil, parser.AllErrors)
	if err != nil {
		return nil, fmt.Errorf("parse %s: %w", filePath, err)
	}

	result := make(map[string]string)
	for _, decl := range f.Decls {
		genDecl, ok := decl.(*ast.GenDecl)
		if !ok || genDecl.Tok != token.CONST {
			continue
		}
		for _, spec := range genDecl.Specs {
			valueSpec, ok := spec.(*ast.ValueSpec)
			if !ok {
				continue
			}
			for i, name := range valueSpec.Names {
				if !contains(constNames, name.Name) {
					continue
				}
				if i < len(valueSpec.Values) {
					if lit, ok := valueSpec.Values[i].(*ast.BasicLit); ok && lit.Kind == token.STRING {
						value, err := strconv.Unquote(lit.Value)
						if err != nil {
							return nil, fmt.Errorf("unquote %s in %s: %w", name.Name, filePath, err)
						}
						result[name.Name] = value
					}
				}
			}
		}
	}
	return result, nil
}

// extractGoSlice reads a Go file and extracts a []string variable by name.
func extractGoSlice(filePath, varName string) ([]string, error) {
	fset := token.NewFileSet()
	f, err := parser.ParseFile(fset, filePath, nil, parser.AllErrors)
	if err != nil {
		return nil, fmt.Errorf("parse %s: %w", filePath, err)
	}

	for _, decl := range f.Decls {
		genDecl, ok := decl.(*ast.GenDecl)
		if !ok || genDecl.Tok != token.VAR {
			continue
		}
		for _, spec := range genDecl.Specs {
			valueSpec, ok := spec.(*ast.ValueSpec)
			if !ok {
				continue
			}
			for _, name := range valueSpec.Names {
				if name.Name != varName {
					continue
				}
				if len(valueSpec.Values) == 0 {
					continue
				}
				composite, ok := valueSpec.Values[0].(*ast.CompositeLit)
				if !ok {
					continue
				}
				var items []string
				for _, elt := range composite.Elts {
					if lit, ok := elt.(*ast.BasicLit); ok && lit.Kind == token.STRING {
						items = append(items, strings.Trim(lit.Value, `"`))
					}
				}
				return items, nil
			}
		}
	}
	return nil, fmt.Errorf("variable %s not found in %s", varName, filePath)
}

func (v *validator) deployConstantsMatchE2E() error {
	goConsts, err := extractGoConst(v.deployFile(), []string{"branchName", "prTitle"})
	if err != nil {
		return err
	}

	content, err := os.ReadFile(v.e2eFile())
	if err != nil {
		return fmt.Errorf("read E2E test: %w", err)
	}
	text := string(content)

	branchRe := regexp.MustCompile(`DEPLOY_BRANCH\s*=\s*"([^"]+)"`)
	titleRe := regexp.MustCompile(`DEPLOY_PR_TITLE\s*=\s*"([^"]+)"`)

	branchMatches := branchRe.FindStringSubmatch(text)
	titleMatches := titleRe.FindStringSubmatch(text)

	if len(branchMatches) < 2 {
		return fmt.Errorf("DEPLOY_BRANCH not found in E2E test")
	}
	if len(titleMatches) < 2 {
		return fmt.Errorf("DEPLOY_PR_TITLE not found in E2E test")
	}

	wantBranch := goConsts["branchName"]
	wantTitle := goConsts["prTitle"]

	if branchMatches[1] != wantBranch {
		return fmt.Errorf("branch mismatch: deploy=%q, e2e=%q", wantBranch, branchMatches[1])
	}
	if titleMatches[1] != wantTitle {
		return fmt.Errorf("title mismatch: deploy=%q, e2e=%q", wantTitle, titleMatches[1])
	}

	return nil
}

func (v *validator) fixDeployConstantsMatchE2E() error {
	goConsts, err := extractGoConst(v.deployFile(), []string{"branchName", "prTitle"})
	if err != nil {
		return err
	}

	content, err := os.ReadFile(v.e2eFile())
	if err != nil {
		return err
	}
	text := string(content)

	branchRe := regexp.MustCompile(`DEPLOY_BRANCH\s*=\s*"([^"]+)"`)
	titleRe := regexp.MustCompile(`DEPLOY_PR_TITLE\s*=\s*"([^"]+)"`)

	text = branchRe.ReplaceAllString(text, `DEPLOY_BRANCH = "`+goConsts["branchName"]+`"`)
	text = titleRe.ReplaceAllString(text, `DEPLOY_PR_TITLE = "`+goConsts["prTitle"]+`"`)

	return os.WriteFile(v.e2eFile(), []byte(text), 0o644)
}

func (v *validator) autoDeployPathsCoverExtraFiles() error {
	extraFiles, err := extractGoSlice(v.deployFile(), "extraFiles")
	if err != nil {
		return err
	}

	paths, err := v.extractAutoDeployPaths()
	if err != nil {
		return err
	}

	for _, ef := range extraFiles {
		covered := false
		for _, tp := range paths {
			if ef == tp {
				covered = true
				break
			}
			tpClean := strings.TrimSuffix(tp, "/**")
			if strings.HasPrefix(filepath.Dir(ef), tpClean) || filepath.Dir(ef) == tpClean {
				covered = true
				break
			}
		}
		if !covered {
			return fmt.Errorf("extraFile %q not covered by 34_auto-deploy.yml paths", ef)
		}
	}

	return nil
}

func (v *validator) fixAutoDeployPaths() error {
	extraFiles, err := extractGoSlice(v.deployFile(), "extraFiles")
	if err != nil {
		return err
	}

	paths, err := v.extractAutoDeployPaths()
	if err != nil {
		return err
	}

	pathSet := make(map[string]bool)
	for _, p := range paths {
		pathSet[p] = true
	}

	var missing []string
	for _, ef := range extraFiles {
		covered := false
		for _, tp := range paths {
			if ef == tp {
				covered = true
				break
			}
			tpClean := strings.TrimSuffix(tp, "/**")
			if strings.HasPrefix(filepath.Dir(ef), tpClean) || filepath.Dir(ef) == tpClean {
				covered = true
				break
			}
		}
		if !covered {
			dir := filepath.Dir(ef)
			glob := dir + "/**"
			if !pathSet[glob] {
				missing = append(missing, glob)
				pathSet[glob] = true
			}
		}
	}

	if len(missing) == 0 {
		return nil
	}

	content, err := os.ReadFile(v.autoDeployFile())
	if err != nil {
		return err
	}

	text := string(content)
	// Insert missing paths before the first non-path, non-comment line after paths section
	lines := strings.Split(text, "\n")
	insertIdx := -1
	for i, line := range lines {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "- '") || strings.HasPrefix(trimmed, "-\"") {
			insertIdx = i + 1
		}
	}
	if insertIdx == -1 {
		return fmt.Errorf("could not find insertion point in 34_auto-deploy.yml")
	}

	var newLines []string
	for _, m := range missing {
		newLines = append(newLines, fmt.Sprintf("      - '%s'", m))
	}

	lines = append(lines[:insertIdx], append(newLines, lines[insertIdx:]...)...)
	return os.WriteFile(v.autoDeployFile(), []byte(strings.Join(lines, "\n")), 0o644)
}

func (v *validator) codeownersCoversExtraFiles() error {
	extraFiles, err := extractGoSlice(v.deployFile(), "extraFiles")
	if err != nil {
		return err
	}

	content, err := os.ReadFile(v.codeownersFile())
	if err != nil {
		return fmt.Errorf("read CODEOWNERS: %w", err)
	}

	lines := strings.Split(string(content), "\n")
	var patterns []string
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		parts := strings.Fields(line)
		if len(parts) >= 2 {
			patterns = append(patterns, parts[0])
		}
	}

	for _, ef := range extraFiles {
		dir := "/" + filepath.Dir(ef) + "/"
		covered := false
		for _, pattern := range patterns {
			patDir := filepath.Dir(pattern)
			if patDir == "." {
				patDir = pattern
			}
			patDir = strings.TrimSuffix(patDir, "/")
			checkDir := strings.TrimSuffix(dir, "/")
			if strings.HasPrefix(checkDir, patDir) || checkDir == patDir {
				covered = true
				break
			}
		}
		if !covered {
			return fmt.Errorf("extraFile %q directory %q not covered by CODEOWNERS patterns", ef, dir)
		}
	}

	return nil
}

func (v *validator) fixCodeowners() error {
	extraFiles, err := extractGoSlice(v.deployFile(), "extraFiles")
	if err != nil {
		return err
	}

	content, err := os.ReadFile(v.codeownersFile())
	if err != nil {
		return err
	}

	lines := strings.Split(string(content), "\n")
	var patterns []string
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		parts := strings.Fields(line)
		if len(parts) >= 2 {
			patterns = append(patterns, parts[0])
		}
	}

	var missing []string
	for _, ef := range extraFiles {
		dir := "/" + filepath.Dir(ef) + "/"
		covered := false
		for _, pattern := range patterns {
			patDir := filepath.Dir(pattern)
			if patDir == "." {
				patDir = pattern
			}
			patDir = strings.TrimSuffix(patDir, "/")
			checkDir := strings.TrimSuffix(dir, "/")
			if strings.HasPrefix(checkDir, patDir) || checkDir == patDir {
				covered = true
				break
			}
		}
		if !covered && !contains(missing, dir) {
			missing = append(missing, dir)
		}
	}

	if len(missing) == 0 {
		return nil
	}

	// Append missing entries before the last blank line or at end
	insertIdx := len(lines)
	for i := len(lines) - 1; i >= 0; i-- {
		if strings.TrimSpace(lines[i]) != "" {
			insertIdx = i + 1
			break
		}
	}

	var newLines []string
	for _, m := range missing {
		newLines = append(newLines, fmt.Sprintf("%s\t@jclee941", m))
	}

	lines = append(lines[:insertIdx], append(newLines, lines[insertIdx:]...)...)
	return os.WriteFile(v.codeownersFile(), []byte(strings.Join(lines, "\n")), 0o644)
}

func (v *validator) issueTemplatesKebabCase() error {
	templateDir := filepath.Join(v.rootDir, ".github", "ISSUE_TEMPLATE")
	entries, err := os.ReadDir(templateDir)
	if err != nil {
		return fmt.Errorf("read ISSUE_TEMPLATE dir: %w", err)
	}

	kebabRe := regexp.MustCompile(`^[0-9]+-[a-z0-9]+(-[a-z0-9]+)*\.yml$`)
	for _, entry := range entries {
		name := entry.Name()
		if name == "config.yml" {
			continue
		}
		if !kebabRe.MatchString(name) {
			return fmt.Errorf("issue template %q does not follow kebab-case.yml convention", name)
		}
	}

	return nil
}

func (v *validator) workflowsNamingConvention() error {
	workflowsDir := filepath.Join(v.rootDir, ".github", "workflows")
	entries, err := os.ReadDir(workflowsDir)
	if err != nil {
		return fmt.Errorf("read workflows dir: %w", err)
	}

	kebabRe := regexp.MustCompile(`^([0-9]+_)?[a-z0-9]+(-[a-z0-9]+)*\.yml$`)
	reusableRe := regexp.MustCompile(`^reusable-[a-z0-9]+(-[a-z0-9]+)*\.yml$`)

	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		name := entry.Name()
		if strings.HasPrefix(name, "_") {
			continue
		}
		if reusableRe.MatchString(name) {
			continue
		}
		if !kebabRe.MatchString(name) {
			return fmt.Errorf("workflow %q does not follow kebab-case.yml convention", name)
		}
	}

	return nil
}

func (v *validator) extraFilesExtensions() error {
	extraFiles, err := extractGoSlice(v.deployFile(), "extraFiles")
	if err != nil {
		return err
	}

	allowed := map[string]bool{
		".yml":  true,
		".yaml": true,
		".md":   true,
		".json": true,
		"":      true,
	}

	for _, ef := range extraFiles {
		ext := filepath.Ext(ef)
		if !allowed[ext] {
			return fmt.Errorf("extraFile %q has disallowed extension %q", ef, ext)
		}
	}

	return nil
}

func (v *validator) requiredStatusChecksMatchWorkflowContexts() error {
	produced, err := v.producedWorkflowContexts()
	if err != nil {
		return err
	}

	producedSet := make(map[string]bool, len(produced))
	for _, context := range produced {
		producedSet[context] = true
	}

	requiredBySource, err := v.requiredStatusCheckContexts()
	if err != nil {
		return err
	}

	for source, required := range requiredBySource {
		for _, context := range required {
			if !producedSet[context] {
				return fmt.Errorf("%s requires status check %q, but produced workflow contexts are %v", source, context, produced)
			}
		}
	}

	return nil
}

func (v *validator) requiredStatusCheckContexts() (map[string][]string, error) {
	branchContexts, err := v.branchProtectionRequiredContexts()
	if err != nil {
		return nil, err
	}
	rulesetContexts, err := v.rulesetsManagerRequiredContexts()
	if err != nil {
		return nil, err
	}

	return map[string][]string{
		"branch-protection": branchContexts,
		"rulesets-manager":  rulesetContexts,
	}, nil
}

func (v *validator) branchProtectionRequiredContexts() ([]string, error) {
	goConsts, err := extractGoConst(v.branchProtectionFile(), []string{"protectionPayload"})
	if err != nil {
		return nil, err
	}

	var payload struct {
		RequiredStatusChecks struct {
			Contexts []string `json:"contexts"`
		} `json:"required_status_checks"`
	}
	if err := json.Unmarshal([]byte(goConsts["protectionPayload"]), &payload); err != nil {
		return nil, fmt.Errorf("parse branch protection payload: %w", err)
	}
	if len(payload.RequiredStatusChecks.Contexts) == 0 {
		return nil, fmt.Errorf("branch protection payload has no required status checks")
	}
	return payload.RequiredStatusChecks.Contexts, nil
}

func (v *validator) rulesetsManagerRequiredContexts() ([]string, error) {
	goConsts, err := extractGoConst(v.rulesetsManagerFile(), []string{"rulesetPayload"})
	if err != nil {
		return nil, err
	}

	var payload struct {
		Rules []struct {
			Type       string `json:"type"`
			Parameters struct {
				RequiredStatusChecks []struct {
					Context string `json:"context"`
				} `json:"required_status_checks"`
			} `json:"parameters"`
		} `json:"rules"`
	}
	if err := json.Unmarshal([]byte(goConsts["rulesetPayload"]), &payload); err != nil {
		return nil, fmt.Errorf("parse rulesets manager payload: %w", err)
	}

	var contexts []string
	for _, rule := range payload.Rules {
		if rule.Type != "required_status_checks" {
			continue
		}
		for _, check := range rule.Parameters.RequiredStatusChecks {
			contexts = append(contexts, check.Context)
		}
	}
	if len(contexts) == 0 {
		return nil, fmt.Errorf("rulesets manager payload has no required status checks")
	}
	return contexts, nil
}

func (v *validator) producedWorkflowContexts() ([]string, error) {
	// Guard against the fleet-blocking drift where rulesets required bare
	// "scan" while GitHub produced "Gitleaks / scan" for the reusable workflow.
	// Keep this derived from workflow files so renaming caller/called jobs fails
	// validation before branch protection or rulesets are redeployed.
	workflowPairs := []struct {
		caller string
		jobKey string
	}{
		{caller: "03_pr-checks.yml", jobKey: "pr-checks"},
		{caller: "05_gitleaks.yml", jobKey: "Gitleaks"},
	}

	var contexts []string
	for _, pair := range workflowPairs {
		callerJobs, err := parseWorkflowJobs(v.workflowFile(pair.caller))
		if err != nil {
			return nil, err
		}
		callerJob, ok := callerJobs[pair.jobKey]
		if !ok {
			return nil, fmt.Errorf("workflow %s missing caller job %q", pair.caller, pair.jobKey)
		}
		if callerJob.Uses == "" {
			return nil, fmt.Errorf("workflow %s job %q does not call a reusable workflow", pair.caller, pair.jobKey)
		}

		calledFile := filepath.Base(callerJob.Uses)
		calledJobs, err := parseWorkflowJobs(v.workflowFile(calledFile))
		if err != nil {
			return nil, err
		}
		for _, job := range calledJobs {
			displayName := job.Key
			if job.Name != "" {
				displayName = job.Name
			}
			contexts = append(contexts, pair.jobKey+" / "+displayName)
		}
	}
	sort.Strings(contexts)
	return contexts, nil
}

type workflowJob struct {
	Key  string
	Name string
	Uses string
}

// notifyOnFailureRequiresCheckout enforces a deployment invariant: any job that
// uses the local composite action ./.github/actions/notify-on-failure MUST run
// an actions/checkout step (to a non-custom path) BEFORE it, otherwise the
// composite action file is absent on the runner workspace and the notify step
// itself fails. A custom `path:` checkout (e.g. path: pr-agent-src) does NOT
// satisfy this because the action is resolved from the workspace root.
func (v *validator) notifyOnFailureRequiresCheckout() error {
	dirs := []string{
		filepath.Join(v.rootDir, ".github", "workflows"),
		filepath.Join(v.rootDir, ".github", "workflows", "security"),
	}
	var files []string
	for _, d := range dirs {
		entries, err := os.ReadDir(d)
		if err != nil {
			continue
		}
		for _, e := range entries {
			if e.IsDir() {
				continue
			}
			if strings.HasSuffix(e.Name(), ".yml") || strings.HasSuffix(e.Name(), ".yaml") {
				files = append(files, filepath.Join(d, e.Name()))
			}
		}
	}
	sort.Strings(files)

	jobRe := regexp.MustCompile(`^  ([A-Za-z0-9_-]+):\s*$`)
	stepRe := regexp.MustCompile(`^      - `)
	checkoutRe := regexp.MustCompile(`uses:\s*actions/checkout@`)
	pathRe := regexp.MustCompile(`^          path:\s*\S`)
	notifyRe := regexp.MustCompile(`uses:\s*\./\.github/actions/notify-on-failure`)

	var offenders []string
	for _, f := range files {
		content, err := os.ReadFile(f)
		if err != nil {
			return fmt.Errorf("read workflow %s: %w", f, err)
		}
		lines := strings.Split(string(content), "\n")
		inJobs := false
		currentJob := ""
		// per-job state
		sawDefaultCheckout := false
		inCheckoutStep := false
		checkoutHasPath := false
		flushCheckout := func() {
			if inCheckoutStep && !checkoutHasPath {
				sawDefaultCheckout = true
			}
			inCheckoutStep = false
			checkoutHasPath = false
		}
		for _, line := range lines {
			trimmed := strings.TrimSpace(line)
			if trimmed == "jobs:" {
				inJobs = true
				continue
			}
			if !inJobs {
				continue
			}
			if m := jobRe.FindStringSubmatch(line); len(m) == 2 {
				flushCheckout()
				currentJob = m[1]
				sawDefaultCheckout = false
				continue
			}
			if currentJob == "" {
				continue
			}
			if stepRe.MatchString(line) {
				flushCheckout()
			}
			if checkoutRe.MatchString(line) {
				inCheckoutStep = true
			}
			if inCheckoutStep && pathRe.MatchString(line) {
				checkoutHasPath = true
			}
			if notifyRe.MatchString(line) && !sawDefaultCheckout {
				offenders = append(offenders, fmt.Sprintf("%s :: job %q", filepath.Base(f), currentJob))
			}
		}
		flushCheckout()
	}

	if len(offenders) > 0 {
		return fmt.Errorf("jobs use ./.github/actions/notify-on-failure without a prior default-path checkout: %s", strings.Join(offenders, "; "))
	}
	return nil
}

func parseWorkflowJobs(filePath string) (map[string]workflowJob, error) {
	content, err := os.ReadFile(filePath)
	if err != nil {
		return nil, fmt.Errorf("read workflow %s: %w", filePath, err)
	}

	jobs := make(map[string]workflowJob)
	inJobs := false
	currentKey := ""
	jobRe := regexp.MustCompile(`^  ([A-Za-z0-9_-]+):\s*$`)
	propRe := regexp.MustCompile(`^    ([A-Za-z0-9_-]+):\s*(.*)$`)

	for _, line := range strings.Split(string(content), "\n") {
		trimmed := strings.TrimSpace(line)
		if trimmed == "" || strings.HasPrefix(trimmed, "#") {
			continue
		}
		if trimmed == "jobs:" {
			inJobs = true
			continue
		}
		if !inJobs {
			continue
		}
		if !strings.HasPrefix(line, " ") {
			break
		}
		if matches := jobRe.FindStringSubmatch(line); len(matches) == 2 {
			currentKey = matches[1]
			jobs[currentKey] = workflowJob{Key: currentKey}
			continue
		}
		if currentKey == "" {
			continue
		}
		if matches := propRe.FindStringSubmatch(line); len(matches) == 3 {
			job := jobs[currentKey]
			switch matches[1] {
			case "name":
				job.Name = strings.Trim(matches[2], `"'`)
			case "uses":
				job.Uses = strings.Trim(matches[2], `"'`)
			}
			jobs[currentKey] = job
		}
	}

	if len(jobs) == 0 {
		return nil, fmt.Errorf("workflow %s has no jobs", filePath)
	}
	return jobs, nil
}

// extractAutoDeployPaths extracts trigger paths from 34_auto-deploy.yml content.
func (v *validator) extractAutoDeployPaths() ([]string, error) {
	content, err := os.ReadFile(v.autoDeployFile())
	if err != nil {
		return nil, fmt.Errorf("read 34_auto-deploy.yml: %w", err)
	}

	var paths []string
	inPaths := false
	for _, line := range strings.Split(string(content), "\n") {
		trimmed := strings.TrimSpace(line)
		if trimmed == "paths:" {
			inPaths = true
			continue
		}
		if inPaths {
			if path, ok := strings.CutPrefix(trimmed, "-"); ok {
				path = strings.TrimSpace(path)
				paths = append(paths, strings.Trim(path, `"'`))
			} else if trimmed != "" && !strings.HasPrefix(trimmed, "#") {
				break
			}
		}
	}
	return paths, nil
}

// Helper methods for file paths
func (v *validator) deployFile() string {
	return filepath.Join(v.rootDir, "scripts", "cmd", "deploy-to-repos", "main.go")
}

func (v *validator) branchProtectionFile() string {
	return filepath.Join(v.rootDir, "scripts", "cmd", "branch-protection", "main.go")
}

func (v *validator) rulesetsManagerFile() string {
	return filepath.Join(v.rootDir, "scripts", "cmd", "rulesets-manager", "main.go")
}

func (v *validator) workflowFile(name string) string {
	return filepath.Join(v.rootDir, ".github", "workflows", name)
}

func (v *validator) e2eFile() string {
	return filepath.Join(v.rootDir, "tests", "e2e_live", "test_deploy_path.py")
}

func (v *validator) autoDeployFile() string {
	return filepath.Join(v.rootDir, ".github", "workflows", "34_auto-deploy.yml")
}

func (v *validator) codeownersFile() string {
	return filepath.Join(v.rootDir, ".github", "CODEOWNERS")
}

func contains(slice []string, item string) bool {
	return slices.Contains(slice, item)
}
