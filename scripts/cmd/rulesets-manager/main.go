// rulesets-manager.go creates and manages GitHub Rulesets for repositories
// marked automation.branch_protection=true in config/repos.yaml.
//
// Usage:
//
//	go run ./scripts/cmd/rulesets-manager --dry-run
//	go run ./scripts/cmd/rulesets-manager --repos=resume,terraform
//	go run ./scripts/cmd/rulesets-manager --mode=list
//	go run ./scripts/cmd/rulesets-manager         # apply to all
//
// Behavior per repo:
//  1. GET existing rulesets
//  2. PUT a ruleset named "Default Branch Protection" with:
//     - required_status_checks: 3 contexts (PR Title, Branch Name, Gitleaks scan)
//     - deletion: prevent branch deletion
//     - non_fast_forward: prevent force push
//     - bypass_actors: none (same as current branch protection)
//
// Rulesets coexist with branch protection. This tool supplements (not replaces)
// the existing branch-protection.go to enable ruleset-based controls.
package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"sort"
	"strings"

	"github.com/jclee941/.github/scripts/internal/repos"
)

// rulesetPayload defines the ruleset to apply.
// Enforcement: "active" | "disabled" | "evaluate"
// Target: "branch" | "tag"
// Conditions.ref_name.include supports: ~DEFAULT_BRANCH, ~ALL, ~ALL_PROTECTION_RULES
const rulesetPayload = `{
  "name": "Default Branch Protection",
  "target": "branch",
  "enforcement": "active",
  "bypass_actors": [],
  "conditions": {
    "ref_name": {
      "include": ["~DEFAULT_BRANCH"],
      "exclude": []
    }
  },
  "rules": [
    {
      "type": "required_status_checks",
      "parameters": {
        "required_status_checks": [
          {
            "context": "pr-checks / Check PR Title",
            "integration_id": null
          },
          {
            "context": "pr-checks / Check Branch Name",
            "integration_id": null
          },
          {
            "context": "scan",
            "integration_id": null
          }
        ],
        "strict_required_status_checks_policy": false
      }
    },
    {
      "type": "deletion"
    },
    {
      "type": "non_fast_forward"
    }
  ]
}`

type result struct {
	repo   string
	status string
	err    error
}

func main() {
	protectedRepos := repos.Names(repos.ProtectedRepos())
	dryRun := flag.Bool("dry-run", false, "preview API calls without making changes")
	reposFlag := flag.String("repos", strings.Join(protectedRepos, ","), "comma-separated repo names")
	mode := flag.String("mode", "apply", "Mode: apply | list | delete")
	flag.Parse()

	repoList, err := normalizeRepos(*reposFlag, protectedRepos)
	if err != nil {
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}

	switch *mode {
	case "list":
		listRulesets(repoList)
	case "apply":
		applyRulesets(repoList, *dryRun)
	case "delete":
		deleteRulesets(repoList, *dryRun)
	default:
		fmt.Fprintf(os.Stderr, "error: unknown mode %q (allowed: apply, list, delete)\n", *mode)
		os.Exit(1)
	}
}

func normalizeRepos(raw string, allowedRepoNames []string) ([]string, error) {
	allowed := make(map[string]struct{}, len(allowedRepoNames))
	for _, repo := range allowedRepoNames {
		allowed[repo] = struct{}{}
	}
	parts := strings.Split(raw, ",")
	seen := make(map[string]struct{}, len(parts))
	repoList := make([]string, 0, len(parts))
	for _, part := range parts {
		repo := strings.TrimSpace(part)
		if repo == "" {
			continue
		}
		if _, ok := allowed[repo]; !ok {
			valid := append([]string(nil), allowedRepoNames...)
			sort.Strings(valid)
			return nil, fmt.Errorf("unsupported repo %q (allowed: %s)", repo, strings.Join(valid, ", "))
		}
		if _, ok := seen[repo]; ok {
			continue
		}
		seen[repo] = struct{}{}
		repoList = append(repoList, repo)
	}
	if len(repoList) == 0 {
		return nil, errors.New("no repos selected")
	}
	return repoList, nil
}

func listRulesets(repoList []string) {
	fmt.Println("=== RULESETS LIST ===")
	for _, repo := range repoList {
		full := "jclee941/" + repo
		endpoint := fmt.Sprintf("repos/%s/rulesets", full)
		cmd := exec.Command("gh", "api", endpoint, "--jq", ".[] | \"\\(.id): \\(.name) (\\(.enforcement))\"")
		var stdout, stderr bytes.Buffer
		cmd.Stdout = &stdout
		cmd.Stderr = &stderr
		if err := cmd.Run(); err != nil {
			if stderr.Len() > 0 {
				fmt.Printf("- jclee941/%s: error - %s\n", repo, strings.TrimSpace(stderr.String()))
			} else {
				fmt.Printf("- jclee941/%s: error - %v\n", repo, err)
			}
			continue
		}
		output := strings.TrimSpace(stdout.String())
		if output == "" {
			fmt.Printf("- jclee941/%s: no rulesets\n", repo)
		} else {
			fmt.Printf("- jclee941/%s:\n", repo)
			for _, line := range strings.Split(output, "\n") {
				fmt.Printf("    %s\n", line)
			}
		}
	}
}

func applyRulesets(repoList []string, dryRun bool) {
	results := make([]result, 0, len(repoList))
	for _, repo := range repoList {
		res := result{repo: repo}
		if err := upsertRuleset(repo, dryRun); err != nil {
			res.status = "failed"
			res.err = err
		} else {
			if dryRun {
				res.status = "previewed"
			} else {
				res.status = "applied"
			}
		}
		results = append(results, res)
	}

	mode := "apply"
	if dryRun {
		mode = "dry-run"
	}
	fmt.Printf("\nSummary (%s):\n", mode)
	failures := 0
	for _, res := range results {
		if res.err != nil {
			fmt.Printf("- jclee941/%s: %s - %v\n", res.repo, res.status, res.err)
			failures++
			continue
		}
		fmt.Printf("- jclee941/%s: %s\n", res.repo, res.status)
	}
	if failures > 0 {
		os.Exit(1)
	}
}

func deleteRulesets(repoList []string, dryRun bool) {
	results := make([]result, 0, len(repoList))
	for _, repo := range repoList {
		res := result{repo: repo}
		if err := deleteRulesetByName(repo, "Default Branch Protection", dryRun); err != nil {
			res.status = "failed"
			res.err = err
		} else {
			if dryRun {
				res.status = "previewed"
			} else {
				res.status = "deleted"
			}
		}
		results = append(results, res)
	}

	mode := "delete"
	if dryRun {
		mode = "dry-run"
	}
	fmt.Printf("\nSummary (%s):\n", mode)
	failures := 0
	for _, res := range results {
		if res.err != nil {
			fmt.Printf("- jclee941/%s: %s - %v\n", res.repo, res.status, res.err)
			failures++
			continue
		}
		fmt.Printf("- jclee941/%s: %s\n", res.repo, res.status)
	}
	if failures > 0 {
		os.Exit(1)
	}
}

func upsertRuleset(repo string, dryRun bool) error {
	full := "jclee941/" + repo
	endpoint := fmt.Sprintf("repos/%s/rulesets", full)

	// Check if ruleset already exists
	existingID, err := findRulesetID(full, "Default Branch Protection")
	if err != nil {
		return fmt.Errorf("find existing ruleset: %w", err)
	}

	if existingID != "" {
		// Update existing
		updateEndpoint := fmt.Sprintf("repos/%s/rulesets/%s", full, existingID)
		if dryRun {
			fmt.Printf("[dry-run] gh api -X PUT %s --input - <<<ruleset_payload\n", updateEndpoint)
			return nil
		}
		return putRuleset(updateEndpoint)
	}

	// Create new
	if dryRun {
		fmt.Printf("[dry-run] gh api -X POST %s --input - <<<ruleset_payload\n", endpoint)
		return nil
	}
	return postRuleset(endpoint)
}

func findRulesetID(fullRepo, name string) (string, error) {
	endpoint := fmt.Sprintf("repos/%s/rulesets", fullRepo)
	cmd := exec.Command("gh", "api", endpoint, "--jq", fmt.Sprintf(".[] | select(.name == %q) | .id", name))
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		if stderr.Len() > 0 {
			msg := strings.TrimSpace(stderr.String())
			// Not found is OK
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

// rulesetListItem is used for JSON parsing in list mode.
type rulesetListItem struct {
	ID          int64  `json:"id"`
	Name        string `json:"name"`
	Enforcement string `json:"enforcement"`
}

// rulesetPayloadStruct is used for JSON marshaling of the payload.
type rulesetPayloadStruct struct {
	Name           string              `json:"name"`
	Target         string              `json:"target"`
	Enforcement    string              `json:"enforcement"`
	BypassActors   []interface{}       `json:"bypass_actors"`
	Conditions     rulesetConditions   `json:"conditions"`
	Rules          []rulesetRule       `json:"rules"`
}

type rulesetConditions struct {
	RefName struct {
		Include []string `json:"include"`
		Exclude []string `json:"exclude"`
	} `json:"ref_name"`
}

type rulesetRule struct {
	Type       string                 `json:"type"`
	Parameters map[string]interface{} `json:"parameters,omitempty"`
}

func init() {
	// Validate the payload is valid JSON at init time
	var payload rulesetPayloadStruct
	if err := json.Unmarshal([]byte(rulesetPayload), &payload); err != nil {
		fmt.Fprintf(os.Stderr, "FATAL: invalid ruleset payload JSON: %v\n", err)
		os.Exit(1)
	}
}
