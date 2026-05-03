// main_test.go — table-driven tests for the pure-logic helpers in
// cmd/branch-protection/main.go. Network-bound helpers (protectRepo,
// defaultBranch, putBranchProtection, runGH) are intentionally out of
// scope: gh CLI is not guaranteed to be present + authenticated in CI.

package main

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestNormalizeRepos(t *testing.T) {
	cases := []struct {
		name    string
		raw     string
		want    []string
		wantErr string
	}{
		{
			name: "all default repos",
			raw:  strings.Join(publicRepos, ","),
			want: publicRepos,
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
			got, err := normalizeRepos(tc.raw)

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

func TestPublicReposInvariants(t *testing.T) {
	if len(publicRepos) == 0 {
		t.Fatal("publicRepos must not be empty")
	}

	seen := make(map[string]struct{}, len(publicRepos))
	for _, r := range publicRepos {
		if r == "" {
			t.Errorf("publicRepos contains an empty entry")
		}
		if strings.ContainsAny(r, "/ \t") {
			t.Errorf("publicRepos entry %q must not contain '/' or whitespace (org prefix is added later)", r)
		}
		if _, dup := seen[r]; dup {
			t.Errorf("publicRepos duplicate entry: %q", r)
		}
		seen[r] = struct{}{}
	}

	want := ".github"
	found := false
	for _, r := range publicRepos {
		if r == want {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("publicRepos missing source repo %q (branch-protection.go expects to protect itself)", want)
	}
}

func TestProtectionPayloadIsValidJSON(t *testing.T) {
	var parsed map[string]any
	if err := json.Unmarshal([]byte(protectionPayload), &parsed); err != nil {
		t.Fatalf("protectionPayload is not valid JSON: %v\npayload:\n%s", err, protectionPayload)
	}

	rsc, ok := parsed["required_status_checks"].(map[string]any)
	if !ok {
		t.Fatalf("required_status_checks missing or wrong type: %T", parsed["required_status_checks"])
	}

	contextsAny, ok := rsc["contexts"].([]any)
	if !ok {
		t.Fatalf("required_status_checks.contexts missing or wrong type: %T", rsc["contexts"])
	}

	contexts := make([]string, 0, len(contextsAny))
	for _, c := range contextsAny {
		s, ok := c.(string)
		if !ok {
			t.Fatalf("contexts entry is not a string: %T (%v)", c, c)
		}
		contexts = append(contexts, s)
	}

	want := []string{
		"pr-checks / Check PR Title",
		"pr-checks / Check Branch Name",
		"Gitleaks / scan",
	}
	if len(contexts) != len(want) {
		t.Fatalf("contexts count: want %d, got %d (%v)", len(want), len(contexts), contexts)
	}
	for i, w := range want {
		if contexts[i] != w {
			t.Errorf("context[%d]: want %q, got %q", i, w, contexts[i])
		}
	}

	if v, ok := parsed["enforce_admins"].(bool); !ok || v {
		t.Errorf("enforce_admins must be present and false; got %v", parsed["enforce_admins"])
	}

	for _, key := range []string{"allow_force_pushes", "allow_deletions"} {
		v, ok := parsed[key].(bool)
		if !ok {
			t.Errorf("%s must be present as bool; got %T", key, parsed[key])
		}
		if v {
			t.Errorf("%s must be false; got true", key)
		}
	}
}

func TestPublicReposCount(t *testing.T) {
	const expected = 12
	if got := len(publicRepos); got != expected {
		t.Fatalf("publicRepos has %d entries; expected %d (1 source + 11 downstream).\n"+
			"If this is intentional, update AGENTS.md and this test.\nCurrent entries: %v",
			got, expected, publicRepos)
	}
}
