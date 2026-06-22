package main

import (
	"reflect"
	"strings"
	"testing"

	repoinventory "github.com/jclee941/.github/scripts/internal/repos"
)

func TestNormalizeReposUsesProtectedInventory(t *testing.T) {
	allowed := repoinventory.Names(repoinventory.ProtectedRepos())
	got, err := normalizeRepos("resume, tmux,resume,hycu", allowed)
	if err != nil {
		t.Fatalf("normalizeRepos returned error: %v", err)
	}
	want := []string{"resume", "tmux", "hycu"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("normalizeRepos = %v, want %v", got, want)
	}
}

func TestProtectedInventoryIncludesPrivateAndExcludesPrAgent(t *testing.T) {
	allowed := repoinventory.Names(repoinventory.ProtectedRepos())
	allowedSet := map[string]struct{}{}
	for _, repo := range allowed {
		allowedSet[repo] = struct{}{}
	}
	for _, repo := range []string{"hycu", "youtube", "propose"} {
		if _, ok := allowedSet[repo]; !ok {
			t.Fatalf("protected inventory should include private repo %q", repo)
		}
	}
	if _, ok := allowedSet["pr-agent"]; ok {
		t.Fatal("protected inventory should exclude pr-agent")
	}
}

func TestNormalizeReposRejectsReposOutsideProtectedInventory(t *testing.T) {
	allowed := repoinventory.Names(repoinventory.ProtectedRepos())
	if _, err := normalizeRepos("pr-agent", allowed); err == nil {
		t.Fatal("expected pr-agent to be rejected")
	}
	if _, err := normalizeRepos("../resume", allowed); err == nil {
		t.Fatal("expected path-like repo to be rejected")
	}
}

func TestSecretSetArgsOmitSecretValue(t *testing.T) {
	secretValue := "super-secret-value"
	args := strings.Join(secretSetArgs("GH_PAT", "jclee941/resume"), " ")

	if strings.Contains(args, secretValue) {
		t.Fatalf("secret value leaked into argv: %s", args)
	}
	if strings.Contains(args, "--body") {
		t.Fatalf("secret set args must use stdin, got argv body flag: %s", args)
	}
}

func TestSetSecretPassesSecretValueToRunner(t *testing.T) {
	secretValue := "super-secret-value"
	var seenFullRepo string
	var seenName string
	var seenValue string

	oldRunner := runSecretSet
	runSecretSet = func(fullRepo, name, value string) error {
		seenFullRepo = fullRepo
		seenName = name
		seenValue = value
		return nil
	}
	t.Cleanup(func() { runSecretSet = oldRunner })

	if err := setSecret("resume", "GH_PAT", secretValue, false); err != nil {
		t.Fatalf("setSecret returned error: %v", err)
	}
	if seenFullRepo != "jclee941/resume" {
		t.Fatalf("full repo = %q, want jclee941/resume", seenFullRepo)
	}
	if seenName != "GH_PAT" {
		t.Fatalf("secret name = %q, want GH_PAT", seenName)
	}
	if seenValue != secretValue {
		t.Fatalf("runner value = %q, want secret value", seenValue)
	}
}
