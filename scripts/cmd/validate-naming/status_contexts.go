package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
)

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
		"jclee_bot/checks/docs_policy.py",
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
