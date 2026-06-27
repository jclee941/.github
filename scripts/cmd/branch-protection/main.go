// branch-protection.go enables auto-merge and applies branch protection rules
// on repositories marked automation.branch_protection=true in config/repos.yaml.
//
// Usage:
//
//	(cd scripts && go run ./cmd/branch-protection --dry-run)
//	(cd scripts && go run ./cmd/branch-protection --repos=resume,terraform)
//	(cd scripts && go run ./cmd/branch-protection)         # apply to all
//
// Behavior per repo:
//  1. PATCH /repos/{r}  allow_auto_merge=true, delete_branch_on_merge=true
//  2. PUT   /repos/{r}/branches/master/protection  with safe defaults:
//     - required_status_checks: 3 contexts (see protectionPayload below):
//     "jclee-bot / pr-metadata", "jclee-bot / secret-scan", and
//     "jclee-bot / actionlint" (reported by the jclee-bot App Checks runner).
//     Sanity is fork-only and excluded.
//     - enforce_admins: false
//     - required_pull_request_reviews: null
//     - restrictions: null
//     - allow_force_pushes: false
//     - allow_deletions: false
//     - lock_branch: false
//     - required_linear_history: false
//     - required_conversation_resolution: false
package main

import (
	"bytes"
	"errors"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"sort"
	"strings"

	"github.com/jclee941/.github/scripts/internal/repos"
)

// protectionPayload is the JSON body for the branch protection PUT call.
// Free-tier-safe. Required status checks (3 contexts), reported by the jclee-bot
// GitHub App's Checks-API runner (jclee_bot package) — installing the App
// provides these with zero per-repo workflow files:
//  1. "jclee-bot / pr-metadata" - conventional title + PR size + sensitive files
//  2. "jclee-bot / secret-scan" - gitleaks secret-pattern detection on the PR
//  3. "jclee-bot / actionlint" - workflow YAML validation when workflows change
//
// Sanity ("Sanity / import-check") is fork-specific to .github (imports
// pr_agent) and is NOT a required check on downstream repos.
//
// Dependabot PRs satisfy the required contexts automatically:
//   - Conventional Commits titles (chore(deps): bump X)
//   - secret-scan passes since dependabot doesn't introduce secrets
//   - actionlint returns neutral when no workflow files changed
//
// CodeQL is intentionally NOT required: it only runs on .py changes and
// would block non-Python PRs. Results surface via Security tab + PR comments.
const protectionPayload = `{
  "required_status_checks": {
    "strict": false,
    "contexts": [
      "jclee-bot / pr-metadata",
      "jclee-bot / secret-scan",
      "jclee-bot / actionlint"
    ]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_linear_history": false,
  "required_conversation_resolution": false,
  "lock_branch": false,
  "allow_fork_syncing": true
}`

const targetBranch = "master"

type result struct {
	repo   string
	status string
	err    error
}

func main() {
	protectedRepos := repos.Names(repos.ProtectedRepos())
	dryRun := flag.Bool("dry-run", false, "preview API calls without making changes")
	reposFlag := flag.String("repos", strings.Join(protectedRepos, ","), "comma-separated repo names")
	flag.Parse()

	repos, err := normalizeRepos(*reposFlag, protectedRepos)
	if err != nil {
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}

	results := make([]result, 0, len(repos))
	for _, r := range repos {
		res := result{repo: r}
		if err := protectRepo(r, *dryRun); err != nil {
			res.status = "failed"
			res.err = err
		} else {
			if *dryRun {
				res.status = "previewed"
			} else {
				res.status = "applied"
			}
		}
		results = append(results, res)
	}

	mode := "apply"
	if *dryRun {
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

func normalizeRepos(raw string, allowedRepoNames []string) ([]string, error) {
	allowed := make(map[string]struct{}, len(allowedRepoNames))
	for _, repo := range allowedRepoNames {
		allowed[repo] = struct{}{}
	}
	parts := strings.Split(raw, ",")
	seen := make(map[string]struct{}, len(parts))
	repos := make([]string, 0, len(parts))
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
		repos = append(repos, repo)
	}
	if len(repos) == 0 {
		return nil, errors.New("no repos selected")
	}
	return repos, nil
}

func protectRepo(repo string, dryRun bool) error {
	full := "jclee941/" + repo

	// Step 1: enable auto-merge + delete branch on merge
	if err := patchRepoSettings(full, dryRun); err != nil {
		return fmt.Errorf("patch repo settings: %w", err)
	}

	if err := putBranchProtection(full, targetBranch, dryRun); err != nil {
		return fmt.Errorf("apply protection on %s: %w", targetBranch, err)
	}

	return nil
}

func patchRepoSettings(fullRepo string, dryRun bool) error {
	args := []string{
		"api", "-X", "PATCH", "repos/" + fullRepo,
		"-F", "allow_auto_merge=true",
		"-F", "delete_branch_on_merge=true",
		"--silent",
	}
	if dryRun {
		fmt.Printf("[dry-run] gh %s\n", strings.Join(args, " "))
		return nil
	}
	return runGH(args...)
}

func putBranchProtection(fullRepo, branch string, dryRun bool) error {
	endpoint := fmt.Sprintf("repos/%s/branches/%s/protection", fullRepo, branch)
	if dryRun {
		fmt.Printf("[dry-run] gh api -X PUT %s --input - <<<%q\n", endpoint, protectionPayload)
		return nil
	}
	cmd := exec.Command("gh", "api", "-X", "PUT", endpoint, "--input", "-", "--silent")
	cmd.Stdin = strings.NewReader(protectionPayload)
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

func runGH(args ...string) error {
	cmd := exec.Command("gh", args...)
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
