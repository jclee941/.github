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
	name  string
	check func() error
	fix   func() error
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
		{"issue templates follow kebab-case", v.issueTemplatesKebabCase, nil},
		{"workflows follow naming convention", v.workflowsNamingConvention, nil},
		{"required status checks match workflow check-run names", v.requiredStatusChecksMatchWorkflowContexts, nil},
		{"notify-on-failure jobs checkout local actions first", v.notifyOnFailureRequiresCheckout, nil},
		{"workflows query users/ not orgs/ for jclee941", v.noOrgEndpointForUserAccount, nil},
		{"no orphaned reusable workflows", v.orphanReusableWorkflows, nil},
		{"README workflow inventory unique and complete", v.readmeWorkflowInventoryUnique, nil},
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
		candidate := filepath.Join(current, ".pr_agent.toml")
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

// extractGoStringLiterals reads a Go file and returns ALL string literals that
// appear in the composite literal assigned to varName. It works for both
// []string slices (literal elements) and map[string]T maps (the literal keys),
// so it can read either an allowlist slice or a map-keyed manifest.
func extractGoStringLiterals(filePath, varName string) ([]string, error) {
	fset := token.NewFileSet()
	f, err := parser.ParseFile(fset, filePath, nil, parser.AllErrors)
	if err != nil {
		return nil, fmt.Errorf("parse %s: %w", filePath, err)
	}

	var items []string
	found := false
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
			targetIdx := -1
			for i, name := range valueSpec.Names {
				if name.Name == varName {
					targetIdx = i
					break
				}
			}
			if targetIdx == -1 || targetIdx >= len(valueSpec.Values) {
				continue
			}
			composite, ok := valueSpec.Values[targetIdx].(*ast.CompositeLit)
			if !ok {
				continue
			}
			found = true
			for _, elt := range composite.Elts {
				switch e := elt.(type) {
				case *ast.BasicLit:
					if e.Kind == token.STRING {
						items = append(items, strings.Trim(e.Value, `"`))
					}
				case *ast.KeyValueExpr:
					if lit, ok := e.Key.(*ast.BasicLit); ok && lit.Kind == token.STRING {
						items = append(items, strings.Trim(lit.Value, `"`))
					}
				}
			}
		}
	}
	if !found {
		return nil, fmt.Errorf("variable %s not found in %s", varName, filePath)
	}
	return items, nil
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
	// Required merge gates are now produced by the jclee-bot GitHub App Checks
	// runner (jclee_bot package), not per-repo workflows. Derive the produced
	// context names from the App check modules so renaming a check name fails
	// validation before branch protection requires a context that no longer
	// exists.
	checkFiles := []string{
		"jclee_bot/checks/pr_metadata.py",
		"jclee_bot/checks/secret_scan.py",
		"jclee_bot/checks/actionlint_check.py",
	}
	re := regexp.MustCompile(`CHECK_NAME\s*=\s*"([^"]+)"`)
	var contexts []string
	for _, rel := range checkFiles {
		b, err := os.ReadFile(filepath.Join(v.rootDir, rel))
		if err != nil {
			return nil, fmt.Errorf("read App check %s: %w", rel, err)
		}
		m := re.FindSubmatch(b)
		if m == nil {
			return nil, fmt.Errorf("App check %s has no CHECK_NAME constant", rel)
		}
		contexts = append(contexts, string(m[1]))
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

// noOrgEndpointForUserAccount guards against a recurring bug: jclee941 is a
// USER account, not an organization, so `gh api orgs/jclee941/...` returns 404
// and silently (2>/dev/null) yields empty repo lists or hard-fails matrix jobs.
// All repo discovery must use the users/ endpoint.
func (v *validator) noOrgEndpointForUserAccount() error {
	dirs := []string{
		filepath.Join(v.rootDir, ".github", "workflows"),
		filepath.Join(v.rootDir, ".github", "workflows", "security"),
	}
	var offenders []string
	for _, d := range dirs {
		entries, err := os.ReadDir(d)
		if err != nil {
			continue
		}
		for _, e := range entries {
			if e.IsDir() || !(strings.HasSuffix(e.Name(), ".yml") || strings.HasSuffix(e.Name(), ".yaml")) {
				continue
			}
			p := filepath.Join(d, e.Name())
			b, err := os.ReadFile(p)
			if err != nil {
				return fmt.Errorf("read workflow %s: %w", p, err)
			}
			if strings.Contains(string(b), "orgs/jclee941") {
				offenders = append(offenders, e.Name())
			}
		}
	}
	if len(offenders) > 0 {
		return fmt.Errorf("workflows query the orgs/ endpoint for the jclee941 USER account (use users/jclee941): %s", strings.Join(offenders, ", "))
	}
	return nil
}

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

// readmeWorkflowInventoryUnique verifies that the README workflow inventory
// tables enumerate each workflow exactly once and that the set of enumerated
// workflows matches the actual files on disk. This guards against the LLM
// README generator emitting duplicate rows or stale/missing entries.
func (v *validator) readmeWorkflowInventoryUnique() error {
	readmePath := filepath.Join(v.rootDir, "README.md")
	b, err := os.ReadFile(readmePath)
	if err != nil {
		return fmt.Errorf("read README.md: %w", err)
	}
	rowRe := regexp.MustCompile("(?m)^\\| `([^`]+\\.ya?ml)` \\|")
	counts := map[string]int{}
	for _, m := range rowRe.FindAllStringSubmatch(string(b), -1) {
		counts[m[1]]++
	}
	if len(counts) == 0 {
		return fmt.Errorf("README.md contains no workflow inventory rows")
	}

	var dups []string
	listed := map[string]bool{}
	for name, c := range counts {
		listed[name] = true
		if c > 1 {
			dups = append(dups, fmt.Sprintf("%s (x%d)", name, c))
		}
	}
	if len(dups) > 0 {
		sort.Strings(dups)
		return fmt.Errorf("README workflow inventory has duplicate rows: %s", strings.Join(dups, ", "))
	}

	// Build actual workflow set (relative to .github/workflows, slash-joined).
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
		return fmt.Errorf("walk workflows dir: %w", walkErr)
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

// isWorkflowCallOnly reports whether a workflow's on: triggers contain ONLY
// workflow_call (plus the always-allowed manual workflow_dispatch). Any other
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

// Helper methods for file paths
func (v *validator) branchProtectionFile() string {
	return filepath.Join(v.rootDir, "scripts", "cmd", "branch-protection", "main.go")
}

func (v *validator) rulesetsManagerFile() string {
	return filepath.Join(v.rootDir, "scripts", "cmd", "rulesets-manager", "main.go")
}

func contains(slice []string, item string) bool {
	return slices.Contains(slice, item)
}
