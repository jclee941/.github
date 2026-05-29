package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"sort"
	"strings"

	"github.com/jclee941/.github/scripts/internal/repos"
)

const owner = "jclee941"

type config struct {
	dryRun bool
	repos  []string
}

type liveMetadata struct {
	Description string   `json:"description"`
	Homepage    string   `json:"homepage"`
	Topics      []string `json:"names"`
}

type repoResult struct {
	name   string
	status string
	err    error
}

type runner struct {
	dryRun bool
	out    io.Writer
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}
}

func run() error {
	cfg, err := parseFlags()
	if err != nil {
		return err
	}

	metadataByName := make(map[string]repos.Repo, len(repos.ReposWithMetadata()))
	for _, repo := range repos.ReposWithMetadata() {
		metadataByName[repo.Name] = repo
	}

	r := runner{dryRun: cfg.dryRun, out: os.Stdout}
	results := make([]repoResult, 0, len(cfg.repos))
	for _, name := range cfg.repos {
		repo := metadataByName[name]
		result := repoResult{name: name}
		status, err := syncRepoMetadata(r, repo)
		result.status = status
		result.err = err
		results = append(results, result)
	}

	printSummary(os.Stdout, cfg.dryRun, results)

	failures := 0
	for _, result := range results {
		if result.err != nil {
			failures++
		}
	}
	if failures > 0 {
		return fmt.Errorf("%d repo(s) failed", failures)
	}
	return nil
}

func parseFlags() (config, error) {
	var cfg config
	var reposFlag string
	managedRepos := repos.Names(repos.ReposWithMetadata())
	defaultReposCSV := strings.Join(managedRepos, ",")

	flag.BoolVar(&cfg.dryRun, "dry-run", false, "preview metadata changes without mutating GitHub")
	flag.StringVar(&reposFlag, "repos", defaultReposCSV, "comma-separated repo names: resume,safetywallet,youtube")
	flag.Parse()

	selectedRepos, err := normalizeRepos(reposFlag, managedRepos)
	if err != nil {
		return config{}, err
	}
	cfg.repos = selectedRepos
	return cfg, nil
}

func normalizeRepos(raw string, allowedRepoNames []string) ([]string, error) {
	allowed := make(map[string]struct{}, len(allowedRepoNames))
	for _, repo := range allowedRepoNames {
		allowed[repo] = struct{}{}
	}

	parts := strings.Split(raw, ",")
	seen := make(map[string]struct{}, len(parts))
	selected := make([]string, 0, len(parts))
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
		selected = append(selected, repo)
	}
	if len(selected) == 0 {
		return nil, errors.New("no repos selected")
	}
	return selected, nil
}

func syncRepoMetadata(r runner, repo repos.Repo) (string, error) {
	live, err := getLiveMetadata(repo.Name)
	if err != nil {
		fmt.Fprintf(r.out, "[%s] error: %v\n", repo.Name, err)
		return "error", err
	}

	changes := diffMetadata(repo.Metadata, live)
	if len(changes) == 0 {
		fmt.Fprintf(r.out, "[%s] in-sync\n", repo.Name)
		return "in-sync", nil
	}

	fmt.Fprintf(r.out, "[%s] drift detected:\n", repo.Name)
	for _, change := range changes {
		fmt.Fprintf(r.out, "  - %s\n", change)
	}

	if r.dryRun {
		return "drift", nil
	}

	if err := patchRepoMetadata(repo); err != nil {
		fmt.Fprintf(r.out, "[%s] error: %v\n", repo.Name, err)
		return "error", err
	}
	if err := putRepoTopics(repo); err != nil {
		fmt.Fprintf(r.out, "[%s] error: %v\n", repo.Name, err)
		return "error", err
	}

	fmt.Fprintf(r.out, "[%s] updated\n", repo.Name)
	return "updated", nil
}

func getLiveMetadata(repo string) (liveMetadata, error) {
	repoPath := fmt.Sprintf("repos/%s/%s", owner, repo)
	metadataJSON, err := ghAPI(repoPath, "--jq", "{description: .description, homepage: .homepage}")
	if err != nil {
		return liveMetadata{}, err
	}
	topicsJSON, err := ghAPI(repoPath + "/topics")
	if err != nil {
		return liveMetadata{}, err
	}

	var metadata liveMetadata
	if err := json.Unmarshal([]byte(metadataJSON), &metadata); err != nil {
		return liveMetadata{}, fmt.Errorf("parse repo metadata for %s: %w", repo, err)
	}
	if err := json.Unmarshal([]byte(topicsJSON), &metadata); err != nil {
		return liveMetadata{}, fmt.Errorf("parse repo topics for %s: %w", repo, err)
	}
	return metadata, nil
}

func patchRepoMetadata(repo repos.Repo) error {
	_, err := ghAPI(
		fmt.Sprintf("repos/%s/%s", owner, repo.Name),
		"--method", "PATCH",
		"-f", "description="+repo.Metadata.Description,
		"-f", "homepage="+repo.Metadata.Homepage,
	)
	return err
}

func putRepoTopics(repo repos.Repo) error {
	args := []string{
		"repos/" + owner + "/" + repo.Name + "/topics",
		"--method", "PUT",
		"-H", "Accept: application/vnd.github+json",
	}
	for _, topic := range repo.Metadata.Topics {
		args = append(args, "-f", "names[]="+topic)
	}
	_, err := ghAPI(args...)
	return err
}

func ghAPI(args ...string) (string, error) {
	cmd := exec.Command("gh", append([]string{"api"}, args...)...)
	var stdout bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	err := cmd.Run()
	if err != nil {
		if stderr.Len() > 0 {
			return "", fmt.Errorf("gh api: %s", strings.TrimSpace(stderr.String()))
		}
		return "", fmt.Errorf("gh api: %w", err)
	}
	return strings.TrimSpace(stdout.String()), nil
}

func diffMetadata(want repos.Metadata, got liveMetadata) []string {
	changes := []string{}
	if want.Description != got.Description {
		changes = append(changes, fmt.Sprintf("description: %q -> %q", got.Description, want.Description))
	}
	if want.Homepage != got.Homepage {
		changes = append(changes, fmt.Sprintf("homepage: %q -> %q", got.Homepage, want.Homepage))
	}
	if !sameStringSet(want.Topics, got.Topics) {
		changes = append(changes, fmt.Sprintf("topics: [%s] -> [%s]", strings.Join(got.Topics, ", "), strings.Join(want.Topics, ", ")))
	}
	return changes
}

func sameStringSet(left, right []string) bool {
	if len(left) != len(right) {
		return false
	}
	leftCopy := append([]string(nil), left...)
	rightCopy := append([]string(nil), right...)
	sort.Strings(leftCopy)
	sort.Strings(rightCopy)
	for i := range leftCopy {
		if leftCopy[i] != rightCopy[i] {
			return false
		}
	}
	return true
}

func printSummary(w io.Writer, dryRun bool, results []repoResult) {
	mode := "apply"
	if dryRun {
		mode = "dry-run"
	}
	fmt.Fprintf(w, "\nSummary (%s):\n", mode)
	for _, result := range results {
		if result.err != nil {
			fmt.Fprintf(w, "- %s: error (%v)\n", result.name, result.err)
			continue
		}
		fmt.Fprintf(w, "- %s: %s\n", result.name, result.status)
	}
}
