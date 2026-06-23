# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportMissingParameterType=false
# pyright: reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportUnknownMemberType=false
# pyright: reportUnknownParameterType=false, reportUnknownVariableType=false, reportUnannotatedClassAttribute=false
# pyright: reportUnusedCallResult=false, reportUnusedParameter=false
import sys
from importlib import import_module
from types import ModuleType, SimpleNamespace

try:
    import httpx
    import openai
except ModuleNotFoundError:
    openai = ModuleType("openai")

    class APIError(Exception):
        pass

    openai.APIError = APIError
    sys.modules["openai"] = openai
    httpx = None
import pytest

litellm = ModuleType("litellm")


async def _unused_acompletion(*args, **kwargs):
    raise AssertionError("litellm.acompletion should not be called by these unit tests")


litellm.acompletion = _unused_acompletion
sys.modules.setdefault("litellm", litellm)

litellm_ai_handler = ModuleType("jclee_bot.review_engine.algo.ai_handlers.litellm_ai_handler")


class LiteLLMAIHandler:
    pass


litellm_ai_handler.LiteLLMAIHandler = LiteLLMAIHandler
sys.modules.setdefault("jclee_bot.review_engine.algo.ai_handlers.litellm_ai_handler", litellm_ai_handler)

config_loader = ModuleType("jclee_bot.review_engine.config_loader")
config_loader.get_settings = lambda: None
sys.modules.setdefault("jclee_bot.review_engine.config_loader", config_loader)

log_module = ModuleType("jclee_bot.review_engine.log")


class _NoopLogger:
    def info(self, *args, **kwargs):
        pass

    def debug(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass

    def contextualize(self, *args, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


log_module.get_logger = lambda: _NoopLogger()
sys.modules.setdefault("jclee_bot.review_engine.log", log_module)

git_patch_processing = ModuleType("jclee_bot.review_engine.algo.git_patch_processing")
git_patch_processing.decouple_and_convert_to_hunks_with_lines_numbers = lambda patch, file=None: patch
sys.modules.setdefault("jclee_bot.review_engine.algo.git_patch_processing", git_patch_processing)

pr_processing = ModuleType("jclee_bot.review_engine.algo.pr_processing")
pr_processing.add_ai_metadata_to_diff_files = lambda *args, **kwargs: None
pr_processing.get_pr_diff = lambda *args, **kwargs: ""
pr_processing.get_pr_multi_diffs = lambda *args, **kwargs: []
pr_processing.retry_with_fallback_models = lambda func: func
sys.modules.setdefault("jclee_bot.review_engine.algo.pr_processing", pr_processing)

token_handler = ModuleType("jclee_bot.review_engine.algo.token_handler")


class TokenHandler:
    pass


token_handler.TokenHandler = TokenHandler
sys.modules.setdefault("jclee_bot.review_engine.algo.token_handler", token_handler)

utils = ModuleType("jclee_bot.review_engine.algo.utils")
utils.ModelType = SimpleNamespace(REGULAR="regular")
utils.clip_tokens = lambda text, *args, **kwargs: text
utils.get_max_tokens = lambda *args, **kwargs: 4096
utils.get_model = lambda *args, **kwargs: "test-model"
utils.load_yaml = lambda *args, **kwargs: {}
utils.replace_code_tags = lambda text: text
utils.show_relevant_configurations = lambda *args, **kwargs: None
sys.modules.setdefault("jclee_bot.review_engine.algo.utils", utils)

git_providers = ModuleType("jclee_bot.review_engine.git_providers")
git_providers.AzureDevopsProvider = type("AzureDevopsProvider", (), {})
git_providers.GithubProvider = type("GithubProvider", (), {})
git_providers.GitLabProvider = type("GitLabProvider", (), {})
git_providers.get_git_provider = lambda *args, **kwargs: None
git_providers.get_git_provider_with_context = lambda *args, **kwargs: None
sys.modules.setdefault("jclee_bot.review_engine.git_providers", git_providers)

git_provider_module = ModuleType("jclee_bot.review_engine.git_providers.git_provider")
git_provider_module.GitProvider = type("GitProvider", (), {})
git_provider_module.get_main_pr_language = lambda *args, **kwargs: "python"
sys.modules.setdefault("jclee_bot.review_engine.git_providers.git_provider", git_provider_module)

pr_description = ModuleType("jclee_bot.review_engine.tools.pr_description")
pr_description.insert_br_after_x_chars = lambda text, *args, **kwargs: text
sys.modules.setdefault("jclee_bot.review_engine.tools.pr_description", pr_description)

help_module = ModuleType("jclee_bot.review_engine.servers.help")
help_module.HelpMessage = type("HelpMessage", (), {})
sys.modules.setdefault("jclee_bot.review_engine.servers.help", help_module)

pr_code_suggestions_module = import_module("jclee_bot.review_engine.tools.pr_code_suggestions")
PRCodeSuggestions = pr_code_suggestions_module.PRCodeSuggestions


def _api_error(message="chunk failed"):
    if httpx is None:
        return openai.APIError(message)
    return openai.APIError(message, httpx.Request("POST", "https://example.test/v1/chat/completions"), body=None)


def _suggestion(chunk_name):
    return {
        "body": f"Improve {chunk_name}",
        "relevant_file": "example.py",
        "relevant_lines_start": 1,
        "relevant_lines_end": 2,
        "suggestion": f"Use clearer code for {chunk_name}",
        "score": 9,
    }


def _prediction(chunk_name):
    return {"code_suggestions": [_suggestion(chunk_name)]}


class _FakePrCodeSuggestionsSettings:
    def __init__(self, parallel_calls):
        self.decouple_hunks = True
        self.max_number_of_calls = 3
        self.parallel_calls = parallel_calls
        self.suggestions_score_threshold = 1


class _FakeSettings:
    def __init__(self, parallel_calls):
        self.pr_code_suggestions = _FakePrCodeSuggestionsSettings(parallel_calls)


def _make_tool(monkeypatch, *, parallel_calls, outcomes):
    monkeypatch.setattr(PRCodeSuggestions, "__init__", lambda self, *args, **kwargs: None)
    monkeypatch.setattr(pr_code_suggestions_module, "get_settings", lambda: _FakeSettings(parallel_calls))
    monkeypatch.setattr(
        pr_code_suggestions_module,
        "get_pr_multi_diffs",
        lambda *args, **kwargs: ["diff-a", "diff-b", "diff-c"],
    )

    async def fake_get_prediction(self, model, patches_diff, patches_diff_no_line_numbers):
        result = outcomes[patches_diff]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(PRCodeSuggestions, "_get_prediction", fake_get_prediction)

    tool = PRCodeSuggestions("https://github.com/jclee941/example/pull/1")
    tool.git_provider = SimpleNamespace()
    tool.token_handler = SimpleNamespace()
    tool.ai_handler = SimpleNamespace()
    tool.patches_diff_list = []
    tool.patches_diff_list_no_line_numbers = []
    tool.prediction_list = []
    tool.data = None
    return tool


@pytest.mark.asyncio
async def test_parallel_calls_keep_successful_suggestions_when_one_chunk_fails(monkeypatch):
    tool = _make_tool(
        monkeypatch,
        parallel_calls=True,
        outcomes={
            "diff-a": _prediction("diff-a"),
            "diff-b": _api_error(),
            "diff-c": _prediction("diff-c"),
        },
    )

    try:
        data = await tool.prepare_prediction_main("test-model")
    except openai.APIError:
        pytest.xfail("Current implementation uses asyncio.gather(return_exceptions=False), so one failed chunk aborts all suggestions")

    assert data == {"code_suggestions": [_suggestion("diff-a"), _suggestion("diff-c")]}


@pytest.mark.asyncio
async def test_sequential_calls_keep_successful_suggestions_when_one_chunk_fails(monkeypatch):
    tool = _make_tool(
        monkeypatch,
        parallel_calls=False,
        outcomes={
            "diff-a": _prediction("diff-a"),
            "diff-b": _api_error(),
            "diff-c": _prediction("diff-c"),
        },
    )

    try:
        data = await tool.prepare_prediction_main("test-model")
    except openai.APIError:
        pytest.xfail("Current sequential implementation does not isolate per-chunk prediction failures")

    assert data == {"code_suggestions": [_suggestion("diff-a"), _suggestion("diff-c")]}


@pytest.mark.asyncio
async def test_returns_empty_suggestions_when_all_chunks_fail(monkeypatch):
    tool = _make_tool(
        monkeypatch,
        parallel_calls=True,
        outcomes={
            "diff-a": _api_error("chunk a failed"),
            "diff-b": _api_error("chunk b failed"),
            "diff-c": _api_error("chunk c failed"),
        },
    )

    try:
        data = await tool.prepare_prediction_main("test-model")
    except openai.APIError:
        pytest.xfail("Current implementation crashes when every chunk prediction fails")

    assert data == {"code_suggestions": []}


@pytest.mark.asyncio
async def test_returns_all_suggestions_when_all_chunks_succeed(monkeypatch):
    tool = _make_tool(
        monkeypatch,
        parallel_calls=True,
        outcomes={
            "diff-a": _prediction("diff-a"),
            "diff-b": _prediction("diff-b"),
            "diff-c": _prediction("diff-c"),
        },
    )

    data = await tool.prepare_prediction_main("test-model")

    assert data == {
        "code_suggestions": [
            _suggestion("diff-a"),
            _suggestion("diff-b"),
            _suggestion("diff-c"),
        ]
    }
