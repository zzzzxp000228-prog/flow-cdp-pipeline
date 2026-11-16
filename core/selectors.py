"""Selector 与几何参数集中配置。

Flow 前端一改版，只改 config/settings.json 的 selectors 段，不必翻遍各模块。
DEFAULT 里所有值 = 2026-11 版 Flow 实测值；未配置 selectors 时行为与旧版完全一致。

分四组：
  text      界面文案正则（中英文用 | 连接，注入 JS new RegExp）
  dom       CSS 选择器
  geometry  坐标 / 尺寸阈值（跟 viewport 强相关，改分辨率时同步调）
  timing    轮询间隔、重试次数、Blob 阈值
"""
import json
from types import SimpleNamespace


DEFAULT = {
    "text": {
        "all_media": "所有媒体|All media",
        "add_ingredients": "在提示框中输入配料|Add ingredients",
        "ingredient_image_alt": "Ingredient image",
        "asset_search": "搜索资产|Search assets",
        "result_image": "图像|Image|图片",
        "clear_prompt": "Clear prompt|清除提示",
        "add_media_menu": "添加媒体菜单|Add media menu",
        "upload_item": "上传|Upload image|Upload",
        "settings_trigger": "设置触发器|Settings trigger",
        "video": "视频|Video",
        "ingredients": "原料|Ingredients",
        "aspect": "9:16",
        "credit": "消耗|积分|credits",
        "download": "Download media|下载",
        "download_option": "720p|Original|原片",
        "download_exclude": "Animated GIF",
        "start_generation": "启动世代|Start generation",
        "gen_arrow": "arrow_forward",
        "back": "Done editing|Back button",
        "back_done": "Done",
        "failed": "失敗|无法生成|政策|Failed|violate|Unable to generate",
        "fresh_video": "Generated video",
    },
    "dom": {
        "prompt_editor": '[contenteditable="true"], textarea',
        "prompt_box": "flow-base-prompt-box",
        "upload_menu_item": 'flow-menu-item button, [role="menu"] button',
        "download_option": 'button, [role="menuitem"]',
        "gallery_media": "img, video",
        "slider": '[role="slider"], input[type="range"]',
    },
    "geometry": {
        "tile_min_w": 80,
        "tile_min_h": 80,
        "tile_min_x": 50,
        "search_offset_x": 30,
        "search_offset_y": 15,
        "prompt_tap_offset_x": 40,
        "prompt_tap_offset_y": 20,
        "result_row_min_w": 60,
        "result_row_min_h": 18,
        "result_row_min_y": 200,
        "result_row_max_y": 620,
        "fresh_tile_max_y": 340,
        "fresh_tile_max_x": 550,
        "progress_max_y": 880,
        "progress_min_x": 50,
        "failed_min_y": 60,
        "failed_max_y": 320,
        "settings_pop_min_y": 450,
        "settings_pop_max_y": 965,
        "settings_pop_min_w": 15,
        "gen_arrow_min_y": 880,
    },
    "timing": {
        "blob_min_size": 300000,
        "blob_wait_rounds": 90,
        "blob_wait_interval": 0.5,
        "poll_interval": 5.0,
        "fresh_min_elapsed": 25,
        "failed_min_elapsed": 15,
        "settings_dur_idx_10": 7,
        "settings_dur_idx_8": 5,
        "settings_dur_steps": 15,
        "asset_wait_sec": 45,
        "picker_retries": 8,
        "attach_retries": 4,
        "clear_retries": 20,
    },
}


def _deep_merge(base, override):
    out = {k: dict(v) if isinstance(v, dict) else v for k, v in base.items()}
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def q(value):
    """把字符串转成可安全嵌入 JS 的字符串字面量（处理引号和反斜杠）。"""
    return json.dumps(value, ensure_ascii=False)


class Selectors:
    """运行时 selector 对象：sel.text.* / sel.dom.* / sel.geometry.* / sel.timing.*。"""

    def __init__(self, raw=None):
        merged = _deep_merge(DEFAULT, raw or {})
        self.text = SimpleNamespace(**merged["text"])
        self.dom = SimpleNamespace(**merged["dom"])
        self.geometry = SimpleNamespace(**merged["geometry"])
        self.timing = SimpleNamespace(**merged["timing"])
        self.raw = merged
