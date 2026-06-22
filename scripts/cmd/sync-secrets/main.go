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

	repoinventory "github.com/jclee941/.github/scripts/internal/repos"
)

// secretsToSync names the env vars to sync. Each must be present in the
// caller's environment; missing values fail loud rather than silently
// erasing the downstream secret.
//
var secretsToSync = []string{
	"CLIPROXY_API_KEY",
	"GH_PAT",
}

var runSecretSet = runGHSecretSet

type result struct {
	repo   string
	secret string
	status string
	err    error
}

func main() {
	defaultRepos := repoinventory.Names(repoinventory.ProtectedRepos())
	dryRun := flag.Bool("dry-run", false, "preview gh secret set calls without invoking them")
	reposFlag := flag.String("repos", strings.Join(defaultRepos, ","), "comma-separated repo names")
	flag.Parse()

	repos, err := normalizeRepos(*reposFlag, defaultRepos)
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
		fmt.Fprintln(os.Stderr, "    export CLIPROXY_API_KEY=$(op read 'op://homelab/cliproxy/credential')")
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
		if strings.Contains(repo, "/") || strings.Contains(repo, "\\") || strings.Contains(repo, "..") {
			return nil, fmt.Errorf("repo %q must be a managed repo name, not a path or owner-qualified name", repo)
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

func setSecret(repo, name, value string, dryRun bool) error {
	full := "jclee941/" + repo
	if value == "" {
		return fmt.Errorf("refusing to set empty value for secret %q (would overwrite downstream secret)", name)
	}
	if dryRun {
		fmt.Printf("[dry-run] printf '<%d bytes>' | gh secret set %s --repo %s\n", len(value), name, full)
		return nil
	}
	return runSecretSet(full, name, value)
}

func secretSetArgs(name, fullRepo string) []string {
	return []string{"secret", "set", name, "--repo", fullRepo}
}

func runGHSecretSet(fullRepo, name, value string) error {
	cmd := exec.Command("gh", secretSetArgs(name, fullRepo)...)
	cmd.Stdin = strings.NewReader(value)
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
