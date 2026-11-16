"""配置加载：所有路径、端口、URL、参数外置，支持环境变量覆盖。

优先级（高到低）：
  1. 环境变量 FLOW_CONFIG / FLOW_PROJECT_ROOT / FLOW_CDP_URL / CHROME_DEVTOOLS_FILE
  2. config/settings.json（用户本地）
  3. config/settings.example.json（仓库默认示例）
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_DIR = os.path.join(ROOT, "config")


def _default_devtools_file():
    """按平台给出 Chrome DevToolsActivePort 的常见位置。"""
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
        return os.path.join(local, "Google", "Chrome", "User Data", "DevToolsActivePort")
    if sys_is_macos():
        return os.path.expanduser(
            "~/Library/Application Support/Google/Chrome/DevToolsActivePort"
        )
    return os.path.expanduser("~/.config/google-chrome/DevToolsActivePort")


def sys_is_macos():
    return os.uname().sysname == "Darwin" if hasattr(os, "uname") else False


def _deep_merge(base, override):
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class Config:
    """运行时配置对象。所有派生路径在构造时一次性算好。"""

    def __init__(self, data):
        self.raw = data
        project_root = data.get("project_root") or os.getcwd()
        self.project_root = os.path.abspath(os.path.expanduser(project_root))

        dirs = data.get("dirs", {})
        self.dirs = {
            name: os.path.join(self.project_root, os.path.expanduser(path))
            for name, path in dirs.items()
        }
        for name in ("assets", "candidates", "frames", "audio", "output", "selected"):
            self.dirs.setdefault(name, os.path.join(self.project_root, name))

        self.manifest_path = os.path.join(self.project_root, data.get("manifest", "flow_manifest.json"))
        self.devtools_file = os.path.expanduser(
            data.get("devtools_file") or _default_devtools_file()
        )
        self.cdp_url = data.get("cdp_url")  # 可选：直接给 ws:// 覆盖 DevToolsActivePort
        self.target_url_match = data.get("target_url_match", "flow.google.com/project/")
        self.viewport = data.get("viewport", {"width": 1920, "height": 1080})
        self.count_lock = data.get("count_lock", "x1")
        self.allowed_counts = data.get("allowed_counts", ["x1", "x2", "x3", "x4"])
        self.fonts = data.get("fonts", {})

        self.assets = data.get("assets", {})          # key -> 文件名
        self.asset_search = data.get("asset_search", {})  # 新版 picker 文案正则

    def ws_url(self):
        """解析 CDP WebSocket 地址。优先用显式 cdp_url，否则读 DevToolsActivePort。"""
        if self.cdp_url:
            return self.cdp_url
        env_url = os.environ.get("FLOW_CDP_URL")
        if env_url:
            return env_url
        path = os.environ.get("CHROME_DEVTOOLS_FILE", self.devtools_file)
        with open(path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        if len(lines) < 2:
            raise RuntimeError(
                f"DevToolsActivePort 格式异常（需要 port + path 两行）: {path}"
            )
        return f"ws://127.0.0.1:{lines[0]}{lines[1]}"

    def path(self, name, *parts):
        base = self.dirs.get(name, os.path.join(self.project_root, name))
        return os.path.join(base, *parts) if parts else base

    def ensure_dirs(self):
        for d in self.dirs.values():
            os.makedirs(d, exist_ok=True)


def load_config(path=None):
    """加载配置：默认示例 + 本地覆盖 + 环境变量。"""
    explicit = path or os.environ.get("FLOW_CONFIG")
    example_path = os.path.join(_CONFIG_DIR, "settings.example.json")
    local_path = os.path.join(_CONFIG_DIR, "settings.json")

    with open(example_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for candidate in (local_path, explicit):
        if candidate and os.path.exists(candidate):
            with open(candidate, "r", encoding="utf-8") as f:
                data = _deep_merge(data, json.load(f))

    root_env = os.environ.get("FLOW_PROJECT_ROOT")
    if root_env:
        data["project_root"] = root_env

    return Config(data)
