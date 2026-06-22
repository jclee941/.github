package main

import (
	"encoding/json"
	"fmt"
	"os"
)

const rulesetPayload = `{
"name": "Default Branch Protection",
"target": "branch",
"enforcement": "active",
"bypass_actors": [
    {
      "actor_id": 5,
      "actor_type": "RepositoryRole",
      "bypass_mode": "always"
    }
  ],
"conditions": {
"ref_name": {
"include": ["refs/heads/master"],
"exclude": []
}
},
"rules": [
    {
      "type": "required_status_checks",
      "parameters": {
        "required_status_checks": [
          {
            "context": "jclee-bot / pr-metadata"
          },
          {
            "context": "jclee-bot / secret-scan"
          },
          {
            "context": "jclee-bot / actionlint"
          }
        ],
        "strict_required_status_checks_policy": false
      }
    },
    {
"type": "deletion"
},
{
"type": "non_fast_forward"
}
]
}`

type rulesetPayloadStruct struct {
	Name         string               `json:"name"`
	Target       string               `json:"target"`
	Enforcement  string               `json:"enforcement"`
	BypassActors []rulesetBypassActor `json:"bypass_actors"`
	Conditions   rulesetConditions    `json:"conditions"`
	Rules        []rulesetRule        `json:"rules"`
}

type rulesetBypassActor struct {
	ActorID    int    `json:"actor_id"`
	ActorType  string `json:"actor_type"`
	BypassMode string `json:"bypass_mode"`
}

type rulesetConditions struct {
	RefName struct {
		Include []string `json:"include"`
		Exclude []string `json:"exclude"`
	} `json:"ref_name"`
}

type rulesetRule struct {
	Type       string                    `json:"type"`
	Parameters *rulesetStatusCheckParams `json:"parameters,omitempty"`
}

type rulesetStatusCheckParams struct {
	RequiredStatusChecks             []rulesetRequiredStatusCheck `json:"required_status_checks"`
	StrictRequiredStatusChecksPolicy bool                         `json:"strict_required_status_checks_policy"`
}

type rulesetRequiredStatusCheck struct {
	Context string `json:"context"`
}

func init() {
	var payload rulesetPayloadStruct
	if err := json.Unmarshal([]byte(rulesetPayload), &payload); err != nil {
		fmt.Fprintf(os.Stderr, "FATAL: invalid ruleset payload JSON: %v\n", err)
		os.Exit(1)
	}
}
