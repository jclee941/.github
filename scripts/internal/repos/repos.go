package repos

import (
	"bufio"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
)

type Repo struct {
	Name          string
	Visibility    string
	DefaultBranch string
	Automation    Automation
	Metadata      Metadata
}

type Automation struct {
	DeployWorkflows  bool
	BranchProtection bool
	HealthCheck      bool
	AutoMerge        bool
}

type Metadata struct {
	Description string
	Topics      []string
	Homepage    string
}

var (
	cachedRepos []Repo
	cachedErr   error
	loadOnce    sync.Once
)

func AllRepos() []Repo {
	return cloneRepos(mustLoad())
}

func PublicRepos() []Repo {
	return filterRepos(func(repo Repo) bool { return repo.Visibility == "public" })
}

func PrivateRepos() []Repo {
	return filterRepos(func(repo Repo) bool { return repo.Visibility == "private" })
}

func DeployableRepos() []Repo {
	return filterRepos(func(repo Repo) bool { return repo.Automation.DeployWorkflows })
}

func ProtectedRepos() []Repo {
	return filterRepos(func(repo Repo) bool { return repo.Automation.BranchProtection })
}

func HealthCheckRepos() []Repo {
	return filterRepos(func(repo Repo) bool { return repo.Automation.HealthCheck })
}

func ReposWithMetadata() []Repo {
	return filterRepos(func(repo Repo) bool { return repo.Metadata.Description != "" })
}

func Names(repoList []Repo) []string {
	names := make([]string, 0, len(repoList))
	for _, repo := range repoList {
		names = append(names, repo.Name)
	}
	return names
}

func mustLoad() []Repo {
	loadOnce.Do(func() {
		cachedRepos, cachedErr = loadFromConfig()
	})
	if cachedErr != nil {
		panic(cachedErr)
	}
	return cachedRepos
}

func filterRepos(include func(Repo) bool) []Repo {
	repos := mustLoad()
	filtered := make([]Repo, 0, len(repos))
	for _, repo := range repos {
		if include(repo) {
			filtered = append(filtered, repo)
		}
	}
	return filtered
}

func cloneRepos(repos []Repo) []Repo {
	clone := make([]Repo, len(repos))
	copy(clone, repos)
	for i := range clone {
		clone[i].Metadata.Topics = append([]string(nil), repos[i].Metadata.Topics...)
	}
	return clone
}

func loadFromConfig() ([]Repo, error) {
	path, err := findConfigPath()
	if err != nil {
		return nil, err
	}
	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open repo inventory %s: %w", path, err)
	}
	defer file.Close()

	var repos []Repo
	var current *Repo
	inAutomation := false
	inMetadata := false

	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := stripInlineComment(scanner.Text())
		trimmed := strings.TrimSpace(line)
		if trimmed == "" || trimmed == "repositories:" {
			continue
		}

		if strings.HasPrefix(trimmed, "- name:") {
			if current != nil {
				repos = append(repos, *current)
			}
			current = &Repo{Name: strings.TrimSpace(strings.TrimPrefix(trimmed, "- name:"))}
			inAutomation = false
			inMetadata = false
			continue
		}

		if current == nil {
			continue
		}

		switch {
		case trimmed == "automation:":
			inAutomation = true
			inMetadata = false
		case trimmed == "metadata:":
			inAutomation = false
			inMetadata = true
		case strings.HasPrefix(trimmed, "visibility:"):
			current.Visibility = strings.TrimSpace(strings.TrimPrefix(trimmed, "visibility:"))
		case strings.HasPrefix(trimmed, "default_branch:"):
			current.DefaultBranch = strings.TrimSpace(strings.TrimPrefix(trimmed, "default_branch:"))
		case inAutomation && strings.Contains(trimmed, ":"):
			key, value, _ := strings.Cut(trimmed, ":")
			setAutomationFlag(&current.Automation, strings.TrimSpace(key), parseBool(strings.TrimSpace(value)))
		case inMetadata && strings.Contains(trimmed, ":"):
			key, value, _ := strings.Cut(trimmed, ":")
			setMetadataField(&current.Metadata, strings.TrimSpace(key), strings.TrimSpace(value))
		}
	}
	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("read repo inventory %s: %w", path, err)
	}
	if current != nil {
		repos = append(repos, *current)
	}
	if err := validate(repos); err != nil {
		return nil, fmt.Errorf("validate repo inventory %s: %w", path, err)
	}
	return repos, nil
}

func findConfigPath() (string, error) {
	wd, err := os.Getwd()
	if err != nil {
		return "", fmt.Errorf("get working directory: %w", err)
	}

	current := wd
	for {
		candidate := filepath.Join(current, "config", "repos.yaml")
		if _, err := os.Stat(candidate); err == nil {
			return candidate, nil
		}
		parent := filepath.Dir(current)
		if parent == current {
			return "", errors.New("config/repos.yaml not found from working directory")
		}
		current = parent
	}
}

func stripInlineComment(line string) string {
	if before, _, ok := strings.Cut(line, "#"); ok {
		return strings.TrimRight(before, " \t")
	}
	return line
}

func parseBool(value string) bool {
	return strings.EqualFold(value, "true")
}

func setAutomationFlag(automation *Automation, key string, value bool) {
	switch key {
	case "deploy_workflows":
		automation.DeployWorkflows = value
	case "branch_protection":
		automation.BranchProtection = value
	case "health_check":
		automation.HealthCheck = value
	case "auto_merge":
		automation.AutoMerge = value
	}
}

func setMetadataField(metadata *Metadata, key, value string) {
	switch key {
	case "description":
		metadata.Description = parseScalar(value)
	case "topics":
		metadata.Topics = parseInlineList(value)
	case "homepage":
		metadata.Homepage = parseScalar(value)
	}
}

func parseScalar(value string) string {
	value = strings.TrimSpace(value)
	if len(value) >= 2 {
		if (value[0] == '"' && value[len(value)-1] == '"') || (value[0] == '\'' && value[len(value)-1] == '\'') {
			return value[1 : len(value)-1]
		}
	}
	return value
}

func parseInlineList(value string) []string {
	value = strings.TrimSpace(value)
	value = strings.TrimPrefix(value, "[")
	value = strings.TrimSuffix(value, "]")
	if strings.TrimSpace(value) == "" {
		return nil
	}
	parts := strings.Split(value, ",")
	items := make([]string, 0, len(parts))
	for _, part := range parts {
		item := parseScalar(strings.TrimSpace(part))
		if item != "" {
			items = append(items, item)
		}
	}
	return items
}

func validate(repos []Repo) error {
	if len(repos) == 0 {
		return errors.New("no repositories configured")
	}
	seen := make(map[string]struct{}, len(repos))
	for _, repo := range repos {
		if repo.Name == "" {
			return errors.New("repository with empty name")
		}
		if repo.Visibility != "public" && repo.Visibility != "private" {
			return fmt.Errorf("%s has unsupported visibility %q", repo.Name, repo.Visibility)
		}
		if repo.DefaultBranch == "" {
			return fmt.Errorf("%s has empty default_branch", repo.Name)
		}
		if _, exists := seen[repo.Name]; exists {
			return fmt.Errorf("duplicate repository %q", repo.Name)
		}
		seen[repo.Name] = struct{}{}
	}
	return nil
}
