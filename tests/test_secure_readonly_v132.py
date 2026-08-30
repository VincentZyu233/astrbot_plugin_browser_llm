"""v1.3.2 安全只读运行时、搜索路由与强制命令测试。"""

import asyncio
import re
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
from astrbot.api.provider import ProviderRequest

from core.browser import BrowserCore
from main import _READ_ONLY_BLOCKED_TOOLS, BrowserLLMPlugin, _make_browser_tool


def _run(coro):
    return asyncio.run(coro)


class _Event:
    unified_msg_origin = "discord:FriendMessage:admin-user"

    def __init__(self, *, admin=True, message=""):
        self.admin = admin
        self.message = message

    def is_admin(self):
        return self.admin

    def get_message_str(self):
        return self.message

    def get_group_id(self):
        return ""

    def get_sender_id(self):
        return "admin-user"

    def plain_result(self, text):
        return text


def _plugin(**overrides):
    config = {
        "read_only_mode": True,
        "enable_local_page_preview": False,
        "session_whitelist": [],
        "session_blacklist": [],
        "page_perception": "text",
    }
    config.update(overrides)
    return BrowserLLMPlugin(context=SimpleNamespace(), config=config)


def test_browser_permission_requires_admin_before_session_rules():
    plugin = _plugin()
    allowed, reason = plugin._is_browser_allowed(_Event(admin=False))
    assert not allowed
    assert "仅限 AstrBot 管理员" in reason
    assert plugin._is_browser_allowed(_Event(admin=True)) == (True, "")


def test_wrapped_tool_denies_before_handler_runs():
    plugin = _plugin()
    plugin._refresh_config = lambda: None
    called = []

    async def fake_open(event, **kwargs):
        called.append(True)
        return "opened"

    plugin.browse_open = fake_open
    tool = _make_browser_tool(
        plugin,
        {
            "name": "browse_open",
            "description": "d",
            "parameters": {},
            "method": "browse_open",
        },
    )
    context = SimpleNamespace(context=SimpleNamespace(event=_Event(admin=False)))
    assert "仅限 AstrBot 管理员" in _run(tool.call(context=context))
    assert called == []


def test_read_only_toolset_removes_state_changing_tools():
    plugin = _plugin()
    plugin._configure_browser_tools()
    names = {tool.name for tool in plugin._browser_tools}
    assert len(names) == 16
    assert not names.intersection(_READ_ONLY_BLOCKED_TOOLS)
    prompt = plugin._build_subagent_instruction("text")
    assert "只读网页浏览器子代理" in prompt
    for name in _READ_ONLY_BLOCKED_TOOLS:
        assert name not in prompt


def test_full_mode_keeps_all_upstream_tools():
    plugin = _plugin(read_only_mode=False)
    plugin._configure_browser_tools()
    assert len(plugin._browser_tools) == 24


def test_local_page_preview_disabled_before_browser_launch():
    plugin = _plugin()
    plugin._refresh_config = lambda: None
    result = _run(plugin.browse_local_page(_Event(), path="/tmp/example.html"))
    assert "本地页面预览已被管理员关闭" in result


@pytest.mark.parametrize(
    "message",
    [
        "帮我联网搜索 AstrBot 最新版本",
        "上网查一下今天的新闻",
        "搜索一下最新的 Playwright 版本",
        "用浏览器帮我查官方文档",
        "打开 https://example.com 看看",
        "search the web for the latest AstrBot release",
    ],
)
def test_explicit_web_intent_detected(message):
    assert BrowserLLMPlugin._has_explicit_web_intent(message)


@pytest.mark.parametrize("message", ["Python 是什么", "讲讲列表推导式", "你好"])
def test_stable_knowledge_does_not_force_browser(message):
    assert not BrowserLLMPlugin._has_explicit_web_intent(message)


def test_llm_instruction_forces_browser_for_explicit_request():
    plugin = _plugin()
    req = ProviderRequest()
    _run(
        plugin.inject_browser_instruction(
            _Event(message="帮我联网搜索 AstrBot 最新版本"), req
        )
    )
    assert "本轮强制联网" in req.system_prompt
    assert "必须调用 browse_web" in req.system_prompt


def test_browse_command_is_deterministic_and_returns_result():
    plugin = _plugin()
    captured = []

    async def fake_browse(event, input=""):
        captured.append(input)
        return "已核实：example"

    plugin.browse_web = fake_browse

    async def collect():
        return [item async for item in plugin.browse_command(_Event(), "查询最新资料")]

    assert _run(collect()) == ["已核实：example"]
    assert captured == ["查询最新资料"]


def test_browse_command_empty_task_returns_usage():
    plugin = _plugin()

    async def collect():
        return [item async for item in plugin.browse_command(_Event(), None)]

    assert "用法：/browse" in _run(collect())[0]


class _FakeEngine:
    def __init__(self):
        self.kwargs = None

    async def launch(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(is_connected=lambda: True)


class _FakePlaywright:
    def __init__(self):
        self.chromium = _FakeEngine()
        self.firefox = _FakeEngine()
        self.webkit = _FakeEngine()
        self.stopped = False

    async def stop(self):
        self.stopped = True


def _install_fake_playwright(monkeypatch):
    playwright = _FakePlaywright()

    class _Starter:
        async def start(self):
            return playwright

    async_api = types.ModuleType("playwright.async_api")
    async_api.async_playwright = lambda: _Starter()
    package = types.ModuleType("playwright")
    package.async_api = async_api
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.async_api", async_api)
    return playwright


def test_system_chrome_path_and_sandbox_launch_args(monkeypatch):
    playwright = _install_fake_playwright(monkeypatch)
    core = BrowserCore(
        {"browser_type": "chromium", "browser_executable_path": "/bin/true"}
    )
    _run(core.ensure_browser())
    kwargs = playwright.chromium.kwargs
    assert kwargs["executable_path"] == "/bin/true"
    assert "--disable-dev-shm-usage" in kwargs["args"]
    assert "--no-sandbox" not in kwargs["args"]


def test_empty_system_browser_path_is_omitted(monkeypatch):
    playwright = _install_fake_playwright(monkeypatch)
    core = BrowserCore({"browser_type": "chromium"})
    _run(core.ensure_browser())
    assert "executable_path" not in playwright.chromium.kwargs


def test_invalid_system_browser_path_has_readable_error(monkeypatch):
    _install_fake_playwright(monkeypatch)
    core = BrowserCore(
        {"browser_type": "chromium", "browser_executable_path": "/missing/chrome"}
    )
    with pytest.raises(ValueError, match="不存在或不可执行"):
        _run(core.ensure_browser())


def test_system_browser_path_rejects_non_chromium(monkeypatch):
    _install_fake_playwright(monkeypatch)
    core = BrowserCore(
        {"browser_type": "firefox", "browser_executable_path": "/bin/true"}
    )
    with pytest.raises(ValueError, match="仅支持 chromium"):
        _run(core.ensure_browser())


def test_metadata_and_runtime_versions_match():
    root = Path(__file__).resolve().parent.parent
    metadata = (root / "metadata.yaml").read_text(encoding="utf-8")
    match = re.search(r"^version:\s*(\S+)$", metadata, re.MULTILINE)
    assert match and match.group(1) == "v1.3.2"
    assert "PLUGIN_VERSION = \"v1.3.2\"" in (root / "main.py").read_text(
        encoding="utf-8"
    )
