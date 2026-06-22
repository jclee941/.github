package main

import (
	"bytes"
	"fmt"
	"os/exec"
	"strings"
)

func findRulesetID(fullRepo, name string) (string, error) {
	endpoint := fmt.Sprintf("repos/%s/rulesets", fullRepo)
	cmd := exec.Command("gh", "api", endpoint, "--jq", fmt.Sprintf(".[] | select(.name == %q) | .id", name))
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		if stderr.Len() > 0 {
			msg := strings.TrimSpace(stderr.String())
			if strings.Contains(msg, "Not Found") || strings.Contains(msg, "not found") {
				return "", nil
			}
			return "", fmt.Errorf("%s: %s", err, msg)
		}
		return "", err
	}
	id := strings.TrimSpace(stdout.String())
	return id, nil
}

func postRuleset(endpoint string) error {
	cmd := exec.Command("gh", "api", "-X", "POST", endpoint, "--input", "-", "--silent")
	cmd.Stdin = strings.NewReader(rulesetPayload)
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		if stderr.Len() > 0 {
			return fmt.Errorf("%s: %s", err, strings.TrimSpace(stderr.String()))
		}
		return err
	}
	return nil
}

func putRuleset(endpoint string) error {
	cmd := exec.Command("gh", "api", "-X", "PUT", endpoint, "--input", "-", "--silent")
	cmd.Stdin = strings.NewReader(rulesetPayload)
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		if stderr.Len() > 0 {
			return fmt.Errorf("%s: %s", err, strings.TrimSpace(stderr.String()))
		}
		return err
	}
	return nil
}

func deleteRulesetByName(repo, name string, dryRun bool) error {
	full := "jclee941/" + repo
	id, err := findRulesetID(full, name)
	if err != nil {
		return fmt.Errorf("find ruleset: %w", err)
	}
	if id == "" {
		fmt.Printf("[skip] jclee941/%s: no ruleset named %q\n", repo, name)
		return nil
	}

	endpoint := fmt.Sprintf("repos/%s/rulesets/%s", full, id)
	if dryRun {
		fmt.Printf("[dry-run] gh api -X DELETE %s\n", endpoint)
		return nil
	}

	cmd := exec.Command("gh", "api", "-X", "DELETE", endpoint, "--silent")
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		if stderr.Len() > 0 {
			return fmt.Errorf("%s: %s", err, strings.TrimSpace(stderr.String()))
		}
		return err
	}
	return nil
}
