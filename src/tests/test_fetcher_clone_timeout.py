import os
import re
import sys
import types
import tempfile
import unittest
from unittest.mock import patch


class _Logger:
    def error(self, *args, **kwargs):
        return None

    def debug(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None


yaml_module = types.ModuleType("yaml")


def _safe_load(stream):
    text = stream.read() if hasattr(stream, "read") else str(stream)
    match = re.search(r"clone_timeout:\s*(\d+)", text)
    if match:
        return {"fetcher": {"clone_timeout": int(match.group(1))}}
    return {}


yaml_module.safe_load = _safe_load
sys.modules["yaml"] = yaml_module

loguru_module = types.ModuleType("loguru")
loguru_module.logger = _Logger()
sys.modules["loguru"] = loguru_module

models_module = types.ModuleType("core.models")
models_module.ProjectInfo = object
models_module.FetchObject = object
sys.modules["core.models"] = models_module

base_module = types.ModuleType("core.base")


class _BaseFetcher:
    def __init__(self, name: str):
        self.name = name

    def fetch(self, target: str, work_dir: str):
        return self._do_fetch(target, work_dir)


base_module.BaseFetcher = _BaseFetcher
sys.modules["core.base"] = base_module

project_parser_module = types.ModuleType("fetcher.project_parser")


class _GithubUrlParser:
    def __init__(self, original_url):
        self.info = None


project_parser_module.GithubUrlParser = _GithubUrlParser
sys.modules["fetcher.project_parser"] = project_parser_module

git_module = types.ModuleType("git")
git_module.Repo = types.SimpleNamespace(clone_from=lambda *args, **kwargs: None)
sys.modules["git"] = git_module

github_module = types.ModuleType("github")
github_module.Github = object
github_module.Auth = types.SimpleNamespace(Token=lambda *args, **kwargs: None)
sys.modules["github"] = github_module

from fetcher.code_fetcher import DEFAULT_CLONE_TIMEOUT, GithubFetcher, _load_fetcher_clone_timeout


class TestFetcherCloneTimeout(unittest.TestCase):
    def test_load_timeout_from_config(self):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write("fetcher:\n  clone_timeout: 25\n")
            config_path = f.name
        try:
            self.assertEqual(_load_fetcher_clone_timeout(config_path), 25)
        finally:
            os.unlink(config_path)

    def test_load_timeout_fallback_when_config_missing(self):
        self.assertEqual(
            _load_fetcher_clone_timeout("/tmp/forge-non-existent-config.yaml"),
            DEFAULT_CLONE_TIMEOUT,
        )

    @patch("fetcher.code_fetcher.GithubFetcher._parse_url")
    @patch("fetcher.code_fetcher.git.Repo.clone_from")
    def test_clone_uses_configured_timeout(self, mock_clone_from, mock_parse_url):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write("fetcher:\n  clone_timeout: 33\n")
            config_path = f.name

        class _UrlInfo:
            git_url = "https://github.com/octo-org/octo-repo.git"
            repo = "octo-repo"
            branch = None

        mock_parse_url.return_value = _UrlInfo()

        try:
            fetcher = GithubFetcher()
            fetcher.clone_timeout = _load_fetcher_clone_timeout(config_path)
            with tempfile.TemporaryDirectory() as work_dir:
                success, _ = fetcher._do_fetch("https://github.com/octo-org/octo-repo", work_dir)
            self.assertTrue(success)
            mock_clone_from.assert_called_once()
            _, kwargs = mock_clone_from.call_args
            self.assertEqual(kwargs["kill_after_timeout"], 33)
        finally:
            os.unlink(config_path)


if __name__ == "__main__":
    unittest.main()
