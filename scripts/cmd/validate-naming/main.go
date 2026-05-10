package main

import (
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

// validation checks cross-file invariants for the deployment system.
type validation struct {
	name   string
	check  func() error
}

func main() {
	rootDir, err := findRepoRoot()
	if err != nil {
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}

	v := &validator{rootDir: rootDir}

	validations := []validation{
		{"deploy constants match E2E test", v.deployConstantsMatchE2E},
		{"auto-deploy paths cover extraFiles", v.autoDeployPathsCoverExtraFiles},
		{"CODEOWNERS covers extraFiles directories", v.codeownersCoversExtraFiles},
		{"issue templates follow kebab-case", v.issueTemplatesKebabCase},
		{"workflows follow naming convention", v.workflowsNamingConvention},
		{"extraFiles have allowed extensions", v.extraFilesExtensions},
	}

	failed := 0
	for _, val := range validations {
		if err := val.check(); err != nil {
			fmt.Fprintf(os.Stderr, "FAIL: %s: %v\n", val.name, err)
			failed++
		} else {
			fmt.Printf("PASS: %s\n", val.name)
		}
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
		candidate := filepath.Join(current, ".github", "workflows", "pr-checks.yml")
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
						result[name.Name] = strings.Trim(lit.Value, `"`)
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
	deployFile := filepath.Join(v.rootDir, "scripts", "cmd", "deploy-to-repos", "main.go")
	goConsts, err := extractGoConst(deployFile, []string{"branchName", "prTitle"})
	if err != nil {
		return err
	}

	e2eFile := filepath.Join(v.rootDir, "tests", "e2e_live", "test_deploy_path.py")
	content, err := os.ReadFile(e2eFile)
	if err != nil {
		return fmt.Errorf("read E2E test: %w", err)
	}
	text := string(content)

	// Extract Python constants via regex
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

func (v *validator) autoDeployPathsCoverExtraFiles() error {
	deployFile := filepath.Join(v.rootDir, "scripts", "cmd", "deploy-to-repos", "main.go")
	extraFiles, err := extractGoSlice(deployFile, "extraFiles")
	if err != nil {
		return err
	}

	// Read auto-deploy.yml trigger paths
	autoDeployPath := filepath.Join(v.rootDir, ".github", "workflows", "auto-deploy.yml")
	content, err := os.ReadFile(autoDeployPath)
	if err != nil {
		return fmt.Errorf("read auto-deploy.yml: %w", err)
	}

	// Extract paths from YAML
	paths := extractYamlPaths(string(content))

	// Check that each extraFiles directory is covered by a trigger path
	for _, ef := range extraFiles {
		dir := filepath.Dir(ef)
		covered := false
		for _, tp := range paths {
			// Handle exact file match
			if ef == tp {
				covered = true
				break
			}
			// Handle glob patterns like '.github/ISSUE_TEMPLATE/**'
			tpClean := strings.TrimSuffix(tp, "/**")
			if strings.HasPrefix(dir, tpClean) || dir == tpClean {
				covered = true
				break
			}
		}
		if !covered {
			return fmt.Errorf("extraFile %q directory %q not covered by auto-deploy.yml paths %v", ef, dir, paths)
		}
	}

	return nil
}

func (v *validator) codeownersCoversExtraFiles() error {
	deployFile := filepath.Join(v.rootDir, "scripts", "cmd", "deploy-to-repos", "main.go")
	extraFiles, err := extractGoSlice(deployFile, "extraFiles")
	if err != nil {
		return err
	}

	codeownersPath := filepath.Join(v.rootDir, ".github", "CODEOWNERS")
	content, err := os.ReadFile(codeownersPath)
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
			// Simple matching: check if directory starts with pattern
			patDir := filepath.Dir(pattern)
			if patDir == "." {
				patDir = pattern
			}
			if strings.HasSuffix(patDir, "/") {
				patDir = strings.TrimSuffix(patDir, "/")
			}
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

func (v *validator) issueTemplatesKebabCase() error {
	templateDir := filepath.Join(v.rootDir, ".github", "ISSUE_TEMPLATE")
	entries, err := os.ReadDir(templateDir)
	if err != nil {
		return fmt.Errorf("read ISSUE_TEMPLATE dir: %w", err)
	}

	kebabRe := regexp.MustCompile(`^[a-z0-9]+(-[a-z0-9]+)*\.yml$`)
	for _, entry := range entries {
		name := entry.Name()
		if name == "config.yml" {
			continue // GitHub standard, exempt from kebab-case
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

	kebabRe := regexp.MustCompile(`^[a-z0-9]+(-[a-z0-9]+)*\.yml$`)
	reusableRe := regexp.MustCompile(`^reusable-[a-z0-9]+(-[a-z0-9]+)*\.yml$`)

	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		name := entry.Name()
		if strings.HasPrefix(name, "_") {
			continue // local-only workflows exempt
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
	deployFile := filepath.Join(v.rootDir, "scripts", "cmd", "deploy-to-repos", "main.go")
	extraFiles, err := extractGoSlice(deployFile, "extraFiles")
	if err != nil {
		return err
	}

	allowed := map[string]bool{
		".yml": true,
		".yaml": true,
		".md":  true,
		"":     true, // no extension (CODEOWNERS)
	}

	for _, ef := range extraFiles {
		ext := filepath.Ext(ef)
		if !allowed[ext] {
			return fmt.Errorf("extraFile %q has disallowed extension %q", ef, ext)
		}
	}

	return nil
}

// extractYamlPaths extracts trigger paths from auto-deploy.yml content.
func extractYamlPaths(content string) []string {
	var paths []string
	inPaths := false
	for _, line := range strings.Split(content, "\n") {
		trimmed := strings.TrimSpace(line)
		if trimmed == "paths:" {
			inPaths = true
			continue
		}
		if inPaths {
			if strings.HasPrefix(trimmed, "-") {
				path := strings.TrimSpace(strings.TrimPrefix(trimmed, "-"))
				paths = append(paths, strings.Trim(path, `"'`))
			} else if trimmed != "" && !strings.HasPrefix(trimmed, "#") {
				// End of paths section
				break
			}
		}
	}
	return paths
}

func contains(slice []string, item string) bool {
	for _, s := range slice {
		if s == item {
			return true
		}
	}
	return false
}
