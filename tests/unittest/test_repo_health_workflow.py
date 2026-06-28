from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

WORKFLOW = Path(".github/workflows/31_repo-health.yml")


def _repo_health_script() -> str:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = data["jobs"]["check-health"]["steps"]
    for step in steps:
        if step.get("name") == "Check repository health":
            return str(step["with"]["script"])
    raise AssertionError("Check repository health step not found")


def test_repo_health_leaves_recovered_issue_closure_to_app() -> None:
    script = _repo_health_script()
    runner = f"""
const vm = require("node:vm");
const workflowScript = {json.dumps(script)};

const calls = [];
const logs = [];
const sandbox = {{
  context: {{ repo: {{ owner: "jclee941" }} }},
  process: {{ env: {{ REPO_NAME: "bug" }} }},
  console: {{ log: (message) => logs.push(String(message)) }},
  github: {{
    rest: {{
      repos: {{
        getContent: async (params) => {{
          calls.push({{ method: "repos.getContent", path: params.path }});
          return {{ data: {{ sha: "ok" }} }};
        }},
      }},
      issues: {{
        listForRepo: async () => {{
          calls.push({{ method: "issues.listForRepo" }});
          return {{ data: [{{ title: "[BOT] 필수 문서 누락: README.md", number: 42 }}] }};
        }},
        update: async () => calls.push({{ method: "issues.update" }}),
        create: async () => calls.push({{ method: "issues.create" }}),
      }},
    }},
  }},
}};

const wrappedScript = "(async () => {{\\n" + workflowScript + "\\n}})()";
Promise.resolve(vm.runInNewContext(wrappedScript, sandbox)).then(() => {{
  console.log(JSON.stringify({{ calls, logs }}));
}}).catch((error) => {{
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
}});
"""
    completed = subprocess.run(
        ["node", "-e", runner],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    mutation_methods = {"issues.update", "issues.create"}

    assert [call["method"] for call in result["calls"]].count("repos.getContent") == 3
    assert any(call["method"] == "issues.listForRepo" for call in result["calls"])
    assert not any(call["method"] in mutation_methods for call in result["calls"])
    assert any("jclee-bot App issue maintenance handles closure" in log for log in result["logs"])
