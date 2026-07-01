from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Final

from pydantic import TypeAdapter

from jclee_bot.json_boundary import JsonObject, object_dict, object_list
from tests.unittest.workflow_policy_helpers import read_workflow_yaml

WORKFLOW = Path(".github/workflows/31_repo-health.yml")
JSON_OBJECT_ADAPTER: Final[TypeAdapter[JsonObject]] = TypeAdapter(JsonObject)


def _repo_health_script() -> str:
    data = read_workflow_yaml(WORKFLOW.name)
    jobs = object_dict(data["jobs"])
    check_health = object_dict(jobs["check-health"])
    steps = object_list(check_health["steps"], "repo health workflow must contain steps")
    for step_value in steps:
        step = object_dict(step_value)
        if step.get("name") == "Check repository health":
            step_with = object_dict(step["with"])
            return str(step_with["script"])
    raise AssertionError("Check repository health step not found")


def test_repo_health_is_read_only_when_required_files_exist() -> None:
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
    result = JSON_OBJECT_ADAPTER.validate_json(completed.stdout)
    calls = object_list(result["calls"], "repo health runner must return calls")
    logs = object_list(result["logs"], "repo health runner must return logs")
    methods = [str(object_dict(call)["method"]) for call in calls]
    log_lines = [str(log) for log in logs]

    assert methods.count("repos.getContent") == 3
    assert all(not method.startswith("issues.") for method in methods)
    assert any("jclee-bot App issue maintenance handles" in log for log in log_lines)


def test_repo_health_missing_files_are_reported_without_issue_mutation() -> None:
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
          if (params.path === "README.md") {{
            throw {{ status: 404 }};
          }}
          return {{ data: {{ sha: "ok" }} }};
        }},
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
    result = JSON_OBJECT_ADAPTER.validate_json(completed.stdout)
    calls = object_list(result["calls"], "repo health runner must return calls")
    logs = object_list(result["logs"], "repo health runner must return logs")
    methods = [str(object_dict(call)["method"]) for call in calls]
    log_lines = [str(log) for log in logs]

    assert methods.count("repos.getContent") == 3
    assert all(not method.startswith("issues.") for method in methods)
    assert any("missing required repo-health files: README.md (required)" in log for log in log_lines)
    assert any("jclee-bot App standardization and issue-maintenance paths own remediation" in log for log in log_lines)


def test_repo_health_fails_on_non_missing_content_lookup_error() -> None:
    script = _repo_health_script()
    runner = f"""
const vm = require("node:vm");
const workflowScript = {json.dumps(script)};

const calls = [];
const sandbox = {{
  context: {{ repo: {{ owner: "jclee941" }} }},
  process: {{ env: {{ REPO_NAME: "bug" }} }},
  console: {{ log: () => undefined }},
  github: {{
    rest: {{
      repos: {{
        getContent: async (params) => {{
          calls.push({{ method: "repos.getContent", path: params.path }});
          throw {{ status: 403, message: "forbidden" }};
        }},
      }},
    }},
  }},
}};

const wrappedScript = "(async () => {{\\n" + workflowScript + "\\n}})()";
Promise.resolve(vm.runInNewContext(wrappedScript, sandbox)).then(() => {{
  console.log(JSON.stringify({{ calls, ok: true }}));
}}).catch((error) => {{
  console.log(JSON.stringify({{ calls, ok: false, status: error.status, message: error.message }}));
}});
"""
    completed = subprocess.run(
        ["node", "-e", runner],
        check=True,
        capture_output=True,
        text=True,
    )
    result = JSON_OBJECT_ADAPTER.validate_json(completed.stdout)
    calls = object_list(result["calls"], "repo health runner must return calls")
    methods = [str(object_dict(call)["method"]) for call in calls]

    assert methods == ["repos.getContent"]
    assert result["ok"] is False
    assert result["status"] == 403
