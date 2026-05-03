// branch-protection.go enables auto-merge and applies a Free-tier-safe
// branch protection rule on the default branch of every public repo
// listed in publicRepos.
//
// Usage:
//
//	go run scripts/branch-protection.go --dry-run
//	go run scripts/branch-protection.go --repos=resume,terraform
//	go run scripts/branch-protection.go         # apply to all
//
// Behavior per repo:
//  1. PATCH /repos/{r}  allow_auto_merge=true, delete_branch_on_merge=true
//  2. GET   /repos/{r}  -> default_branch
//  3. PUT   /repos/{r}/branches/{b}/protection  with safe defaults:
//     - required_status_checks: 3 contexts (see protectionPayload below):
//       "pr-checks / Check PR Title", "pr-checks / Check Branch Name",
//       "Gitleaks / scan". Sanity is fork-only and excluded; CodeQL is
//       advisory (Python-only) and excluded.
//     - enforce_admins: false
//     - required_pull_request_reviews: null
//     - restrictions: null
//     - allow_force_pushes: false
//     - allow_deletions: false
//     - lock_branch: false
//     - required_linear_history: false
//     - required_conversation_resolution: false
//
// Private repos are deliberately excluded — branch protection on personal
// private repos requires GitHub Pro.
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
)

// publicRepos covers all jclee941/* public repos eligible for auto-merge.
var publicRepos = []string{
	".github",
	"account",
	"blacklist",
	"bug",
	"hycu_fsds",
	"idle-outpost",
	"opencode",
	"resume",
	"safetywallet",
	"splunk",
	"terraform",
	"tmux",
}

// protectionPayload is the JSON body for the branch protection PUT call.
// Free-tier-safe. Required status checks (3 contexts):
//   1. "pr-checks / Check PR Title"   - Conventional Commits enforcement
//   2. "pr-checks / Check Branch Name" - branch prefix enforcement
//   3. "Gitleaks / scan"              - secret-pattern detection
//
// Sanity ("Sanity / import-check") is fork-specific to .github (imports
// pr_agent) and is NOT a required check on downstream repos.
//
// The other four pr-checks jobs (Size, Description, Large Files,
// Sensitive Files) are advisory: they comment but always succeed.
//
// Dependabot PRs satisfy all three required contexts automatically:
//   - Conventional Commits titles (chore(deps): bump X)
//   - dependabot/ prefix (allowlisted in reusable-pr-checks.yml)
//   - Gitleaks passes since dependabot doesn't introduce secrets
//
// CodeQL is intentionally NOT required: it only runs on .py changes and
// would block non-Python PRs. Results surface via Security tab + PR comments.
const protectionPayload = `{
  "required_status_checks": {
    "strict": false,
    "contexts": [
      "pr-checks / Check PR Title",
      "pr-checks / Check Branch Name",
      "Gitleaks / scan"
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

type result struct {
	repo   string
	status string
	err    error
}

func main() {
	dryRun := flag.Bool("dry-run", false, "preview API calls without making changes")
	reposFlag := flag.String("repos", strings.Join(publicRepos, ","), "comma-separated repo names")
	flag.Parse()

	repos, err := normalizeRepos(*reposFlag)
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

func normalizeRepos(raw string) ([]string, error) {
	allowed := make(map[string]struct{}, len(publicRepos))
	for _, repo := range publicRepos {
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
			valid := append([]string(nil), publicRepos...)
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

	// Step 2: detect default branch
	branch, err := defaultBranch(full)
	if err != nil {
		return fmt.Errorf("detect default branch: %w", err)
	}

	// Step 3: apply branch protection
	if err := putBranchProtection(full, branch, dryRun); err != nil {
		return fmt.Errorf("apply protection on %s: %w", branch, err)
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

func defaultBranch(fullRepo string) (string, error) {
	cmd := exec.Command("gh", "api", "repos/"+fullRepo, "--jq", ".default_branch")
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		if stderr.Len() > 0 {
			return "", fmt.Errorf("%s: %s", err, strings.TrimSpace(stderr.String()))
		}
		return "", err
	}
	branch := strings.TrimSpace(stdout.String())
	if branch == "" {
		return "", errors.New("empty default branch")
	}
	return branch, nil
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
