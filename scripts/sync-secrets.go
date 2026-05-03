// sync-secrets.go pushes shared organization-style secrets to all 12 public
// jclee941 repos so the standard automation workflows (pr-review.yml, etc.)
// can run on each downstream repo.
//
// Usage:
//
//	CLIPROXY_API_KEY=xxx go run scripts/sync-secrets.go --dry-run
//	CLIPROXY_API_KEY=xxx go run scripts/sync-secrets.go
//	CLIPROXY_API_KEY=xxx go run scripts/sync-secrets.go --repos=resume
//
// Behavior per repo:
//
//	gh secret set CLIPROXY_API_KEY --repo jclee941/{r} --body "$CLIPROXY_API_KEY"
//
// The script reads CLIPROXY_API_KEY from the local environment so the
// secret never lands in shell history or in the repo.
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

// publicRepos covers all jclee941/* public repos that receive the
// shared automation stack and therefore need the cli_proxy API key.
// Kept in sync with branch-protection.go.
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

// secretsToSync names the env vars to sync. Each must be present in the
// caller's environment; missing values fail loud rather than silently
// erasing the downstream secret.
var secretsToSync = []string{
	"CLIPROXY_API_KEY",
}

type result struct {
	repo   string
	secret string
	status string
	err    error
}

func main() {
	dryRun := flag.Bool("dry-run", false, "preview gh secret set calls without invoking them")
	reposFlag := flag.String("repos", strings.Join(publicRepos, ","), "comma-separated repo names")
	flag.Parse()

	repos, err := normalizeRepos(*reposFlag)
	if err != nil {
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}

	missing := []string{}
	for _, name := range secretsToSync {
		if os.Getenv(name) == "" {
			missing = append(missing, name)
		}
	}
	if len(missing) > 0 {
		fmt.Fprintf(os.Stderr, "error: required env vars not set: %s\n", strings.Join(missing, ", "))
		fmt.Fprintln(os.Stderr, "  set them locally before running, e.g.:")
		fmt.Fprintln(os.Stderr, "    export CLIPROXY_API_KEY=$(op read 'op://Personal/cliproxy/credential')")
		os.Exit(1)
	}

	results := make([]result, 0, len(repos)*len(secretsToSync))
	for _, r := range repos {
		for _, name := range secretsToSync {
			res := result{repo: r, secret: name}
			if err := setSecret(r, name, os.Getenv(name), *dryRun); err != nil {
				res.status = "failed"
				res.err = err
			} else if *dryRun {
				res.status = "previewed"
			} else {
				res.status = "set"
			}
			results = append(results, res)
		}
	}

	mode := "apply"
	if *dryRun {
		mode = "dry-run"
	}
	fmt.Printf("\nSummary (%s):\n", mode)
	failures := 0
	for _, res := range results {
		if res.err != nil {
			fmt.Printf("- jclee941/%s :: %s :: %s - %v\n", res.repo, res.secret, res.status, res.err)
			failures++
			continue
		}
		fmt.Printf("- jclee941/%s :: %s :: %s\n", res.repo, res.secret, res.status)
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

func setSecret(repo, name, value string, dryRun bool) error {
	full := "jclee941/" + repo
	if dryRun {
		fmt.Printf("[dry-run] gh secret set %s --repo %s --body <%d bytes>\n", name, full, len(value))
		return nil
	}
	cmd := exec.Command("gh", "secret", "set", name, "--repo", full, "--body", value)
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
