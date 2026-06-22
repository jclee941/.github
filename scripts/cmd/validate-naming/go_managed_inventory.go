package main

import (
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

func (v *validator) goCommandsDeriveManagedRepoInventoryFromConfig() error {
	files, err := v.goCommandFiles()
	if err != nil {
		return err
	}

	protected := managedRepoNameSet()
	var offenders []string
	for _, file := range files {
		hits, hitErr := hardcodedManagedRepoGoHits(file, protected)
		if hitErr != nil {
			return hitErr
		}
		for _, hit := range hits {
			rel, relErr := filepath.Rel(v.rootDir, file)
			if relErr != nil {
				rel = file
			}
			offenders = append(offenders, fmt.Sprintf("%s:%d embeds managed repos %q", rel, hit.line, strings.Join(hit.repos, ",")))
		}
	}
	if len(offenders) > 0 {
		return fmt.Errorf("Go commands hardcode managed repo inventory; derive it from config/repos.yaml instead: %s", strings.Join(offenders, "; "))
	}
	return nil
}

func (v *validator) goCommandFiles() ([]string, error) {
	root := filepath.Join(v.rootDir, "scripts", "cmd")
	var files []string
	if err := filepath.WalkDir(root, func(file string, d os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if d.IsDir() || !strings.HasSuffix(d.Name(), ".go") || strings.HasSuffix(d.Name(), "_test.go") {
			return nil
		}
		files = append(files, file)
		return nil
	}); err != nil {
		return nil, fmt.Errorf("walk Go command path %s: %w", root, err)
	}
	return files, nil
}

func hardcodedManagedRepoGoHits(file string, protected map[string]struct{}) ([]hardcodedRepoInventoryHit, error) {
	fset := token.NewFileSet()
	parsed, err := parser.ParseFile(fset, file, nil, parser.AllErrors)
	if err != nil {
		return nil, fmt.Errorf("parse Go command %s: %w", file, err)
	}

	var hits []hardcodedRepoInventoryHit
	for _, decl := range parsed.Decls {
		gen, ok := decl.(*ast.GenDecl)
		if !ok || (gen.Tok != token.VAR && gen.Tok != token.CONST) {
			continue
		}
		for _, spec := range gen.Specs {
			valueSpec, ok := spec.(*ast.ValueSpec)
			if !ok {
				continue
			}
			repos := managedRepoStringLiterals(valueSpec.Values, protected)
			if len(repos) >= 3 {
				hits = append(hits, hardcodedRepoInventoryHit{
					line:  fset.Position(valueSpec.Pos()).Line,
					repos: repos,
				})
			}
		}
	}
	return hits, nil
}

func managedRepoStringLiterals(exprs []ast.Expr, protected map[string]struct{}) []string {
	seen := map[string]struct{}{}
	for _, expr := range exprs {
		ast.Inspect(expr, func(node ast.Node) bool {
			lit, ok := node.(*ast.BasicLit)
			if !ok || lit.Kind != token.STRING {
				return true
			}
			value, err := strconv.Unquote(lit.Value)
			if err != nil {
				return true
			}
			if _, ok := protected[value]; !ok {
				return true
			}
			seen[value] = struct{}{}
			return true
		})
	}
	repos := make([]string, 0, len(seen))
	for repo := range seen {
		repos = append(repos, repo)
	}
	sort.Strings(repos)
	return repos
}
