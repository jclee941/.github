// main_test.go — table-driven tests for the pure-logic helpers in
// cmd/branch-protection/main.go. Network-bound helpers (protectRepo,
// putBranchProtection, runGH) are intentionally out of
// scope: gh CLI is not guaranteed to be present + authenticated in CI.

package main

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/jclee941/jclee-bot/scripts/internal/repos"
)

var protectedRepoNames = repos.Names(repos.ProtectedRepos())

func TestNormalizeRepos(t *testing.T) {
	cases := []struct {
		name    string
		raw     string
		want    []string
		wantErr string
	}{
		{
			name: "all default repos",
			raw:  strings.Join(protectedRepoNames, ","),
			want: protectedRepoNames,
		},
		{
			name: "single repo",
			raw:  "resume",
			want: []string{"resume"},
		},
		{
			name: "multiple repos preserve order",
			raw:  "tmux,resume,blacklist",
			want: []string{"tmux", "resume", "blacklist"},
		},
		{
			name: "deduplicate within input",
			raw:  "resume,resume,tmux,resume",
			want: []string{"resume", "tmux"},
		},
		{
			name: "trim whitespace",
			raw:  " resume , tmux ",
			want: []string{"resume", "tmux"},
		},
		{
			name: "skip empty segments",
			raw:  "resume,,tmux,",
			want: []string{"resume", "tmux"},
		},
		{
			name:    "reject unknown repo",
			raw:     "resume,nonexistent",
			wantErr: `unsupported repo "nonexistent"`,
		},
		{
			name:    "reject when only empty",
			raw:     ",,, ",
			wantErr: "no repos selected",
		},
		{
			name:    "reject empty string",
			raw:     "",
			wantErr: "no repos selected",
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, err := normalizeRepos(tc.raw, protectedRepoNames)

			if tc.wantErr != "" {
				if err == nil {
					t.Fatalf("expected error containing %q, got nil (result=%v)", tc.wantErr, got)
				}
				if !strings.Contains(err.Error(), tc.wantErr) {
					t.Fatalf("error mismatch: want substring %q, got %q", tc.wantErr, err.Error())
				}
				return
			}

			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if len(got) != len(tc.want) {
				t.Fatalf("length mismatch: want %d (%v), got %d (%v)", len(tc.want), tc.want, len(got), got)
			}
			for i := range got {
				if got[i] != tc.want[i] {
					t.Errorf("index %d: want %q, got %q", i, tc.want[i], got[i])
				}
			}
		})
	}
}

func TestProtectedReposInvariants(t *testing.T) {
	if len(protectedRepoNames) == 0 {
		t.Fatal("protected repo list must not be empty")
	}

	seen := make(map[string]struct{}, len(protectedRepoNames))
	for _, r := range protectedRepoNames {
		if r == "" {
			t.Errorf("protected repo list contains an empty entry")
		}
		if strings.ContainsAny(r, "/ \t") {
			t.Errorf("protected repo entry %q must not contain '/' or whitespace (org prefix is added later)", r)
		}
		if _, dup := seen[r]; dup {
			t.Errorf("protected repo duplicate entry: %q", r)
		}
		seen[r] = struct{}{}
	}

	want := "jclee-bot"
	found := false
	for _, r := range protectedRepoNames {
		if r == want {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("protected repo list missing source repo %q (branch-protection.go expects to protect itself)", want)
	}
}

func TestProtectionPayloadIsValidJSON(t *testing.T) {
	type requiredStatusChecks struct {
		Contexts []string `json:"contexts"`
	}
	type protectionConfig struct {
		RequiredStatusChecks requiredStatusChecks `json:"required_status_checks"`
		EnforceAdmins        bool                 `json:"enforce_admins"`
		AllowForcePushes     bool                 `json:"allow_force_pushes"`
		AllowDeletions       bool                 `json:"allow_deletions"`
	}

	var parsed protectionConfig
	if err := json.Unmarshal([]byte(protectionPayload), &parsed); err != nil {
		t.Fatalf("protectionPayload is not valid JSON: %v\npayload:\n%s", err, protectionPayload)
	}

	want := []string{
		"jclee-bot / pr-metadata",
		"jclee-bot / secret-scan",
		"jclee-bot / actionlint",
	}
	contexts := parsed.RequiredStatusChecks.Contexts
	if len(contexts) != len(want) {
		t.Fatalf("contexts count: want %d, got %d (%v)", len(want), len(contexts), contexts)
	}
	for i, w := range want {
		if contexts[i] != w {
			t.Errorf("context[%d]: want %q, got %q", i, w, contexts[i])
		}
	}

	if parsed.EnforceAdmins {
		t.Errorf("enforce_admins must be false")
	}

	if parsed.AllowForcePushes {
		t.Errorf("allow_force_pushes must be false")
	}
	if parsed.AllowDeletions {
		t.Errorf("allow_deletions must be false")
	}
}

func TestProtectedReposExcludePrAgentAndIncludePrivateRepos(t *testing.T) {
	seen := make(map[string]bool, len(protectedRepoNames))
	for _, repo := range protectedRepoNames {
		seen[repo] = true
	}
	if seen["pr-agent"] {
		t.Fatal("protected repo list must exclude pr-agent")
	}
	for _, repo := range []string{"hycu", "youtube", "propose"} {
		if !seen[repo] {
			t.Fatalf("protected repo list missing private managed repo %q: %v", repo, protectedRepoNames)
		}
	}
}
