package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/jclee941/.github/scripts/internal/repos"
)

type config struct {
	format string
}

type driftResult struct {
	Repo   string `json:"repo"`
	File   string `json:"file"`
	Status string `json:"status"` // missing, modified, extra
}

func main() {
	var cfg config
	flag.StringVar(&cfg.format, "format", "text", "Output format: text, markdown, json")
	flag.Parse()

	rootDir, err := findRepoRoot()
	if err != nil {
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}

	// Read managed files from deploy-to-repos
	managedFiles, err := getManagedFiles(rootDir)
	if err != nil {
		fmt.Fprintf(os.Stderr, "error reading managed files: %v\n", err)
		os.Exit(1)
	}

	// Get deployable repos
	repos, err := getDeployableRepos()
	if err != nil {
		fmt.Fprintf(os.Stderr, "error getting repos: %v\n", err)
		os.Exit(1)
	}

	var drifts []driftResult
	for _, repo := range repos {
		repoDrifts, err := checkRepoDrift(rootDir, repo, managedFiles)
		if err != nil {
			fmt.Fprintf(os.Stderr, "warning: drift check failed for %s: %v\n", repo, err)
			continue
		}
		drifts = append(drifts, repoDrifts...)
	}

	if len(drifts) == 0 {
		os.Exit(0)
	}

	if cfg.format == "json" {
		printJSON(drifts)
	} else if cfg.format == "markdown" {
		printMarkdown(drifts)
	} else {
		printText(drifts)
	}
	os.Exit(1)
}

func findRepoRoot() (string, error) {
	wd, err := os.Getwd()
	if err != nil {
		return "", err
	}
	current := wd
	for {
		candidate := filepath.Join(current, ".github", "workflows", "pr-checks.yml")
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

func getManagedFiles(rootDir string) ([]string, error) {
	// Read from deploy-to-repos allowlist
	deployFile := filepath.Join(rootDir, "scripts", "cmd", "deploy-to-repos", "main.go")
	content, err := os.ReadFile(deployFile)
	if err != nil {
		return nil, err
	}

	var files []string
	// Simple text extraction - look for allowlist entries
	lines := strings.Split(string(content), "\n")
	inAllowlist := false
	inExtraFiles := false
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if strings.Contains(line, "downstreamWorkflowAllowlist") {
			inAllowlist = true
		}
		if strings.Contains(line, "extraFiles") {
			inAllowlist = false
			inExtraFiles = true
		}
		if inAllowlist || inExtraFiles {
			if strings.Contains(trimmed, `".github/`) {
				// Extract quoted string
				start := strings.Index(trimmed, `"`)
				end := strings.LastIndex(trimmed, `"`)
				if start != -1 && end > start {
					files = append(files, trimmed[start+1:end])
				}
			}
		}
		if inExtraFiles && trimmed == "}" {
			break
		}
	}
	return files, nil
}

func getDeployableRepos() ([]string, error) {
	return repos.Names(repos.DeployableRepos()), nil
}

func checkRepoDrift(rootDir, repo string, managedFiles []string) ([]driftResult, error) {
	var drifts []driftResult

	// Clone repo to temp
	tmpDir, err := os.MkdirTemp("", "drift-check-*")
	if err != nil {
		return nil, err
	}
	defer os.RemoveAll(tmpDir)

	cmd := exec.Command("gh", "repo", "clone", fmt.Sprintf("jclee941/%s", repo), tmpDir, "--", "--depth", "1")
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		// Repo might be private or inaccessible
		return nil, fmt.Errorf("clone %s: %w (stderr: %s)", repo, err, stderr.String())
	}

	for _, mf := range managedFiles {
		srcPath := filepath.Join(rootDir, mf)
		dstPath := filepath.Join(tmpDir, mf)

		srcContent, srcErr := os.ReadFile(srcPath)
		dstContent, dstErr := os.ReadFile(dstPath)

		if srcErr != nil && dstErr != nil {
			continue // Both missing
		}
		if srcErr == nil && dstErr != nil {
			drifts = append(drifts, driftResult{repo, mf, "missing"})
			continue
		}
		if srcErr != nil && dstErr == nil {
			drifts = append(drifts, driftResult{repo, mf, "extra"})
			continue
		}
		if !bytes.Equal(srcContent, dstContent) {
			drifts = append(drifts, driftResult{repo, mf, "modified"})
		}
	}

	return drifts, nil
}

func printText(drifts []driftResult) {
	fmt.Println("=== DRIFT DETECTED ===")
	for _, d := range drifts {
		fmt.Printf("[%s] %s: %s\n", d.Repo, d.File, d.Status)
	}
}

func printMarkdown(drifts []driftResult) {
	fmt.Println("## Downstream Automation Drift Report")
	fmt.Println()
	fmt.Println("| Repo | File | Status |")
	fmt.Println("|------|------|--------|")
	for _, d := range drifts {
		fmt.Printf("| %s | %s | %s |\n", d.Repo, d.File, d.Status)
	}
	fmt.Println()
	fmt.Println("**Action required**: Run `(cd scripts && go run ./cmd/deploy-to-repos)` to sync.")
}

func uniqueDriftRepos(drifts []driftResult) []string {
	seen := make(map[string]bool)
	var result []string
	for _, d := range drifts {
		if !seen[d.Repo] {
			seen[d.Repo] = true
			result = append(result, d.Repo)
		}
	}
	return result
}

func printJSON(drifts []driftResult) {
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetIndent("", "  ")
	type jsonOutput struct {
		Repos  []string       `json:"repos"`
		Drifts []driftResult `json:"drifts"`
	}
	out := jsonOutput{
		Repos:  uniqueDriftRepos(drifts),
		Drifts: drifts,
	}
	if err := encoder.Encode(out); err != nil {
		fmt.Fprintf(os.Stderr, "error encoding JSON: %v\n", err)
		os.Exit(1)
	}
}
