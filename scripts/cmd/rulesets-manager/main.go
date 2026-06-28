// rulesets-manager.go creates and manages GitHub Rulesets for repositories
// marked automation.branch_protection=true in config/repos.yaml.
//
// Usage:
//
//	(cd scripts && go run ./cmd/rulesets-manager --dry-run)
//	(cd scripts && go run ./cmd/rulesets-manager --repos=resume,terraform)
//	(cd scripts && go run ./cmd/rulesets-manager --mode=list)
//	(cd scripts && go run ./cmd/rulesets-manager)         # apply to all
//
// Behavior per repo:
//  1. GET existing rulesets
//  2. PUT a ruleset named "Default Branch Protection" with:
//     - required_status_checks: 3 App contexts (jclee-bot / pr-metadata, jclee-bot / secret-scan, jclee-bot / actionlint)
//     - deletion: prevent branch deletion
//     - non_fast_forward: prevent force push
//     - bypass_actors: RepositoryRole actor_id 5 bypasses as repository admin
//
// Rulesets coexist with branch protection. This tool supplements (not replaces)
// the existing branch-protection.go to enable ruleset-based controls.
package main

import (
	"bytes"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"strings"

	"github.com/jclee941/jclee-bot/scripts/internal/repos"
)

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
			fmt.Println(rulesetDryRunCommand("PUT", updateEndpoint))
			return nil
		}
		return putRuleset(updateEndpoint)
	}

	// Create new
	if dryRun {
		fmt.Println(rulesetDryRunCommand("POST", endpoint))
		return nil
	}
	return postRuleset(endpoint)
}

func rulesetDryRunCommand(method, endpoint string) string {
	return fmt.Sprintf("[dry-run] gh api -X %s %s --input - <<<%q", method, endpoint, rulesetPayload)
}
