package main

import (
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"strconv"
	"strings"
)

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
