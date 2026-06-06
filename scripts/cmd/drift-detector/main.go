package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"

	"github.com/jclee941/.github/scripts/internal/repos"
)

type config struct {
	format string
}

type driftResult struct {
	Repo     string `json:"repo"`
	File     string `json:"file"`
	Status   string `json:"status"`   // missing, modified, extra
	Severity string `json:"severity"` // critical, warning, info
}

func main() {
	var cfg config
	flag.StringVar(&cfg.format, "format", "text", "Output format: text, markdown, json, mermaid")
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
		// For mermaid we still emit a full "all clean" standardization map so
		// the visual artifact is always renderable. Other formats preserve the
		// historical no-output-on-zero-drift behavior.
		if cfg.format == "mermaid" {
			renderMermaid(os.Stdout, repos, nil)
		}
		os.Exit(0)
	}

	if cfg.format == "json" {
		printJSON(drifts)
	} else if cfg.format == "markdown" {
		printMarkdown(drifts)
	} else if cfg.format == "mermaid" {
		renderMermaid(os.Stdout, repos, drifts)
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
		// Stable marker: config/repos.yaml is the single source of truth and does
		// not change when workflows are renamed (e.g. pr-checks.yml -> 03_pr-checks.yml).
		if _, err := os.Stat(filepath.Join(current, "config", "repos.yaml")); err == nil {
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
			drifts = append(drifts, driftResult{repo, mf, "missing", "critical"})
			continue
		}
		if srcErr != nil && dstErr == nil {
			drifts = append(drifts, driftResult{repo, mf, "extra", "info"})
			continue
		}
		if !bytes.Equal(srcContent, dstContent) {
			drifts = append(drifts, driftResult{repo, mf, "modified", "warning"})
		}
	}

	return drifts, nil
}

func printText(drifts []driftResult) {
	fmt.Println("=== DRIFT DETECTED ===")
	for _, d := range drifts {
		fmt.Printf("[%s] %s: %s (severity: %s)\n", d.Repo, d.File, d.Status, d.Severity)
	}
}

func printMarkdown(drifts []driftResult) {
	fmt.Println("## Downstream Automation Drift Report")
	fmt.Println()
	fmt.Println("| Repo | File | Status | Severity |")
	fmt.Println("|------|------|--------|----------|")
	for _, d := range drifts {
		fmt.Printf("| %s | %s | %s | %s |\n", d.Repo, d.File, d.Status, d.Severity)
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
		Repos  []string      `json:"repos"`
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

// sanitizeMermaidID converts a repo/file name into a Mermaid-safe identifier
// (Mermaid node ids cannot contain '-' or '.').
func sanitizeMermaidID(name string) string {
	repl := strings.NewReplacer("-", "_", ".", "_", "/", "_", " ", "_")
	return repl.Replace(name)
}

// severityRank orders severities so we can aggregate the worst per repo.
func severityRank(sev string) int {
	switch sev {
	case "critical":
		return 3
	case "warning":
		return 2
	case "info":
		return 1
	default:
		return 0
	}
}

// escapeMermaidLabel makes a string safe inside a Mermaid "..." label.
func escapeMermaidLabel(s string) string {
	s = strings.ReplaceAll(s, "\\", "")
	s = strings.ReplaceAll(s, "\"", "'")
	s = strings.ReplaceAll(s, "\n", " ")
	return s
}

// renderMermaid emits a GitHub-native Mermaid standardization map: one node per
// deployable repo colored by its worst drift severity (clean if none), with
// drifted files shown as child nodes. Output is deterministic (inventory order
// for repos, path order for files). When drifts is nil/empty every repo renders
// clean, so the diagram is always a valid all-clean map.
func renderMermaid(w io.Writer, repoNames []string, drifts []driftResult) {
	// Aggregate worst severity + collect drifted files per repo.
	worst := make(map[string]string)
	files := make(map[string][]driftResult)
	for _, d := range drifts {
		if severityRank(d.Severity) > severityRank(worst[d.Repo]) {
			worst[d.Repo] = d.Severity
		}
		files[d.Repo] = append(files[d.Repo], d)
	}

	classOf := func(repo string) string {
		switch worst[repo] {
		case "critical":
			return "critical"
		case "warning":
			return "warning"
		case "info":
			return "info"
		default:
			return "clean"
		}
	}

	fmt.Fprintln(w, "```mermaid")
	fmt.Fprintln(w, "flowchart TB")
	fmt.Fprintln(w, `    SOURCE["표준 소스<br/>jclee941/.github"]`)
	fmt.Fprintln(w, `    subgraph DOWNSTREAM["다운스트림 리포 표준화 상태"]`)

	for _, repo := range repoNames {
		rid := "repo_" + sanitizeMermaidID(repo)
		cls := classOf(repo)
		statusLabel := "clean"
		if cls != "clean" {
			statusLabel = worst[repo]
		}
		fmt.Fprintf(w, "        %s[\"jclee941/%s<br/>%s\"]\n", rid, escapeMermaidLabel(repo), statusLabel)
		// drifted file child nodes (sorted by path for stable output)
		rf := files[repo]
		sort.Slice(rf, func(i, j int) bool { return rf[i].File < rf[j].File })
		for n, d := range rf {
			fid := fmt.Sprintf("file_%s_%d", sanitizeMermaidID(repo), n)
			fmt.Fprintf(w, "        %s[\"%s<br/>%s/%s\"]\n", fid,
				escapeMermaidLabel(d.File), d.Status, d.Severity)
			fmt.Fprintf(w, "        %s --> %s\n", rid, fid)
		}
	}
	fmt.Fprintln(w, "    end")

	// edges: source standardizes every downstream repo
	for _, repo := range repoNames {
		rid := "repo_" + sanitizeMermaidID(repo)
		fmt.Fprintf(w, "    SOURCE --> %s\n", rid)
	}

	// severity classes (colors match docs/architecture.md palette)
	fmt.Fprintln(w, "    classDef clean fill:#6ba06a,stroke:#333,color:#fff")
	fmt.Fprintln(w, "    classDef info fill:#4a90d9,stroke:#333,color:#fff")
	fmt.Fprintln(w, "    classDef warning fill:#d9b430,stroke:#333,color:#000")
	fmt.Fprintln(w, "    classDef critical fill:#e74c3c,stroke:#333,color:#fff")

	for _, repo := range repoNames {
		rid := "repo_" + sanitizeMermaidID(repo)
		fmt.Fprintf(w, "    class %s %s\n", rid, classOf(repo))
	}
	fmt.Fprintln(w, "```")
}
