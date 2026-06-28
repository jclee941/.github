package main

import (
	"encoding/json"
	"reflect"
	"strings"
	"testing"

	repoinventory "github.com/jclee941/jclee-bot/scripts/internal/repos"
)

func TestNormalizeRepos(t *testing.T) {
	allowed := repoinventory.Names(repoinventory.ProtectedRepos())

	tests := []struct {
		name    string
		input   string
		want    []string
		wantErr bool
	}{
		{
			name:    "single repo",
			input:   "resume",
			want:    []string{"resume"},
			wantErr: false,
		},
		{
			name:    "multiple repos",
			input:   "resume,bug,terraform",
			want:    []string{"resume", "bug", "terraform"},
			wantErr: false,
		},
		{
			name:    "with spaces",
			input:   " resume , bug ",
			want:    []string{"resume", "bug"},
			wantErr: false,
		},
		{
			name:    "duplicate repos",
			input:   "resume,resume,bug",
			want:    []string{"resume", "bug"},
			wantErr: false,
		},
		{
			name:    "unsupported repo",
			input:   "unsupported-repo",
			want:    nil,
			wantErr: true,
		},
		{
			name:    "empty input",
			input:   "",
			want:    nil,
			wantErr: true,
		},
		{
			name:    "mixed valid and invalid",
			input:   "resume,invalid,bug",
			want:    nil,
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := normalizeRepos(tt.input, allowed)
			if (err != nil) != tt.wantErr {
				t.Errorf("normalizeRepos(%q) error = %v, wantErr %v", tt.input, err, tt.wantErr)
				return
			}
			if !tt.wantErr {
				if len(got) != len(tt.want) {
					t.Errorf("normalizeRepos(%q) = %v, want %v", tt.input, got, tt.want)
					return
				}
				for i := range got {
					if got[i] != tt.want[i] {
						t.Errorf("normalizeRepos(%q)[%d] = %q, want %q", tt.input, i, got[i], tt.want[i])
					}
				}
			}
		})
	}
}

func TestRulesetPayloadJSON(t *testing.T) {
	// Verify the payload is valid JSON and has expected structure
	var payload rulesetPayloadStruct
	if err := json.Unmarshal([]byte(rulesetPayload), &payload); err != nil {
		t.Fatalf("rulesetPayload is invalid JSON: %v", err)
	}

	if payload.Name != "Default Branch Protection" {
		t.Errorf("payload.Name = %q, want %q", payload.Name, "Default Branch Protection")
	}

	if payload.Target != "branch" {
		t.Errorf("payload.Target = %q, want %q", payload.Target, "branch")
	}

	if payload.Enforcement != "active" {
		t.Errorf("payload.Enforcement = %q, want %q", payload.Enforcement, "active")
	}

	if len(payload.Rules) != 3 {
		t.Errorf("len(payload.Rules) = %d, want 3", len(payload.Rules))
	}

	// Check rule types
	ruleTypes := make(map[string]bool)
	for _, rule := range payload.Rules {
		ruleTypes[rule.Type] = true
	}

	expectedTypes := []string{"required_status_checks", "deletion", "non_fast_forward"}
	for _, expected := range expectedTypes {
		if !ruleTypes[expected] {
			t.Errorf("missing rule type: %q", expected)
		}
	}

	// Check required_status_checks parameters
	for _, rule := range payload.Rules {
		if rule.Type == "required_status_checks" {
			if rule.Parameters == nil {
				t.Error("required_status_checks rule missing parameters")
				continue
			}
			if len(rule.Parameters.RequiredStatusChecks) != 3 {
				t.Errorf("expected 3 status checks, got %d", len(rule.Parameters.RequiredStatusChecks))
			}
		}
	}
}

func TestRulesetPayloadRequiredStatusCheckContexts(t *testing.T) {
	var payload rulesetPayloadStruct
	if err := json.Unmarshal([]byte(rulesetPayload), &payload); err != nil {
		t.Fatalf("rulesetPayload is invalid JSON: %v", err)
	}

	var got []string
	for _, rule := range payload.Rules {
		if rule.Type != "required_status_checks" {
			continue
		}
		if rule.Parameters == nil {
			t.Fatal("required_status_checks rule missing parameters")
		}
		for _, check := range rule.Parameters.RequiredStatusChecks {
			got = append(got, check.Context)
		}
	}

	want := []string{
		"jclee-bot / pr-metadata",
		"jclee-bot / secret-scan",
		"jclee-bot / actionlint",
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("required status check contexts = %v, want %v", got, want)
	}
}

func TestRulesetDryRunCommandIncludesPayloadContexts(t *testing.T) {
	got := rulesetDryRunCommand("PUT", "repos/jclee941/resume/rulesets/123")
	for _, context := range []string{
		"jclee-bot / pr-metadata",
		"jclee-bot / secret-scan",
		"jclee-bot / actionlint",
	} {
		if !strings.Contains(got, context) {
			t.Fatalf("dry-run command missing context %q: %s", context, got)
		}
	}
	if strings.Contains(got, "ruleset_payload") {
		t.Fatalf("dry-run command must include the actual payload, got placeholder: %s", got)
	}
}

func TestRulesetConditions(t *testing.T) {
	var payload rulesetPayloadStruct
	if err := json.Unmarshal([]byte(rulesetPayload), &payload); err != nil {
		t.Fatalf("rulesetPayload is invalid JSON: %v", err)
	}

	if len(payload.Conditions.RefName.Include) != 1 {
		t.Errorf("len(Conditions.RefName.Include) = %d, want 1", len(payload.Conditions.RefName.Include))
	}

	if payload.Conditions.RefName.Include[0] != "refs/heads/master" {
		t.Errorf("Conditions.RefName.Include[0] = %q, want %q", payload.Conditions.RefName.Include[0], "refs/heads/master")
	}
}
