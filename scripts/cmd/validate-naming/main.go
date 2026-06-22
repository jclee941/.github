package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
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
		{"workflow run blocks use env for dispatch inputs", v.workflowRunBlocksUseEnvForDispatchInputs, nil},
		{"workflows derive managed repo inventory from config", v.workflowsDeriveManagedRepoInventoryFromConfig, nil},
		{"active workflows avoid stale control-plane surfaces", v.activeWorkflowsAvoidStaleControlPlaneSurfaces, nil},
		{"Go commands derive managed repo inventory from config", v.goCommandsDeriveManagedRepoInventoryFromConfig, nil},
		{"documentation uses current App required checks", v.docsUseCurrentAppRequiredChecks, nil},
		{"no orphaned reusable workflows", v.orphanReusableWorkflows, nil},
		{"README workflow inventory unique and complete", v.readmeWorkflowInventoryUnique, nil},
		{"README workflow inventory triggers match workflow files", v.readmeWorkflowInventoryTriggers, nil},
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
