package main

import (
	"slices"
	"testing"

	"github.com/jclee941/.github/scripts/internal/repos"
)

func TestMetadataLoadedFromYAML(t *testing.T) {
	var account repos.Repo
	for _, repo := range repos.AllRepos() {
		if repo.Name == "account" {
			account = repo
			break
		}
	}

	if account.Name == "" {
		t.Fatal("account repo not found")
	}
	if account.Metadata.Description != "Gmail automation workspace" {
		t.Fatalf("account description = %q", account.Metadata.Description)
	}
	if len(account.Metadata.Topics) != 4 {
		t.Fatalf("account topics length = %d, want 4 (%v)", len(account.Metadata.Topics), account.Metadata.Topics)
	}
}

func TestReposWithMetadataExcludesSourceAndFork(t *testing.T) {
	metadataRepos := repos.Names(repos.ReposWithMetadata())
	for _, excluded := range []string{".github", "pr-agent", "automation-e2e-public"} {
		if slices.Contains(metadataRepos, excluded) {
			t.Fatalf("%s should not be metadata-managed: %v", excluded, metadataRepos)
		}
	}
}

func TestAllManagedReposHaveDescription(t *testing.T) {
	metadataByName := make(map[string]repos.Metadata)
	for _, repo := range repos.ReposWithMetadata() {
		metadataByName[repo.Name] = repo.Metadata
	}

	for _, repo := range repos.AllRepos() {
		if !repo.Automation.DeployWorkflows || repo.Name == "automation-e2e-public" {
			continue
		}
		metadata := metadataByName[repo.Name]
		if metadata.Description == "" {
			t.Fatalf("%s has deploy_workflows=true but no metadata.description", repo.Name)
		}
	}
}

func TestDiffMetadataIgnoresTopicOrder(t *testing.T) {
	want := repos.Metadata{
		Description: "repo description",
		Homepage:    "https://example.com",
		Topics:      []string{"automation", "python", "security"},
	}
	got := liveMetadata{
		Description: "repo description",
		Homepage:    "https://example.com",
		Topics:      []string{"security", "automation", "python"},
	}

	if diff := diffMetadata(want, got); len(diff) != 0 {
		t.Fatalf("diffMetadata returned drift for same topic set: %v", diff)
	}
}
