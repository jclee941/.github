package main

import (
	"path/filepath"
	"slices"
)

// Helper methods for file paths
func (v *validator) branchProtectionFile() string {
	return filepath.Join(v.rootDir, "scripts", "cmd", "branch-protection", "main.go")
}

func (v *validator) rulesetsManagerFile() string {
	return filepath.Join(v.rootDir, "scripts", "cmd", "rulesets-manager", "payload.go")
}

func contains(slice []string, item string) bool {
	return slices.Contains(slice, item)
}
