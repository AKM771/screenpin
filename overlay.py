# -*- coding: utf-8 -*-
"""屏幕贴图 / ScreenPin —— 把图片或视频贴在屏幕上置顶显示的小工具。
功能：随意改大小、吸附屏幕九宫格位置、半透明、置顶(占最高)、右键菜单修改一切、
点击穿透(热键 Ctrl+Alt+P)、循环/静音/音量、拖放打开、多实例拖放打开、配置记忆。
依赖：PyQt5 (Qt5 WMF 视频后端)。"""
import sys
import os
import json
import ctypes
import signal
import time
import tempfile

from PyQt5.QtCore import (QByteArray, QObject, Qt, QPoint, QRect, QSize, QTimer,
                          QUrl)
from PyQt5.QtNetwork import QLocalServer, QLocalSocket
from PyQt5.QtGui import (QColor, QCursor, QDesktopServices, QFont, QFontMetricsF,
                         QIcon, QImage, QKeySequence, QMovie, QPainter, QPixmap)
from PyQt5.QtWidgets import (QAction, QApplication, QCheckBox, QColorDialog,
                             QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                             QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem,
                             QMenu, QMessageBox, QPushButton, QScrollArea, QSlider,
                             QSpinBox,
                             QSystemTrayIcon, QTextEdit, QVBoxLayout, QWidget)
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtMultimediaWidgets import QVideoWidget

try:
    from av_player import AvPlayer, HAVE_AV   # PyAV 回退后端（可选依赖）
    _AV_ERR = None
except Exception as _e:
    AvPlayer = None
    HAVE_AV = False
    _AV_ERR = repr(_e)

APP_NAME = "屏幕贴图"
VERSION = "1.9"          # 单一版本源：关于框/托盘/官网/安装程序统一从这取
SITE_URL = "https://akm771.github.io/screenpin/"   # 官网（GitHub Pages）
AFDIAN_URL = "https://afdian.com/a/AKM771"        # 爱发电支持页
FEEDBACK_MAIL = "jjonju361999@qq.com"
UPDATE_API = "https://api.github.com/repos/AKM771/screenpin/releases/latest"
SETTINGS = {"theme": 0, "restore": 0, "autoupdate": 1}   # 主题/启动恢复(默认关)/启动检查更新(默认开)
# 主题：中性灰/低饱和成组配色（自写，非界面截图抄袭；无渐变无发光）
THEMES = [
    ("深灰", dict(bg="#202022", card="#2a2a2e", btn="#333338", btnh="#3d3d45",
                  text="#e8e8ea", dim="#9a9aa2", line="#45454c")),
    ("炭黑", dict(bg="#141416", card="#1f1f23", btn="#2a2a2f", btnh="#34343b",
                  text="#e6e6ea", dim="#8a8a92", line="#3a3a41")),
    ("雾灰", dict(bg="#45454d", card="#52525a", btn="#5d5d66", btnh="#6a6a74",
                  text="#f2f2f4", dim="#c8c8d0", line="#6d6d77")),
    ("石板", dict(bg="#1e2430", card="#272e3c", btn="#2f3644", btnh="#39415200"[:7],
                  text="#e6e9ef", dim="#97a0b0", line="#3c4557")),
    ("棕灰", dict(bg="#26221e", card="#2e2a25", btn="#37322c", btnh="#423b34",
                  text="#ece8e2", dim="#a89f94", line="#47403a")),
]
IPC_NAME = "ScreenPin_SingleInstance_v1"

# —— 锚点（屏幕九宫格，用户叫法）：索引 0=自由，1..9 对应 ANCHOR_RC ——
ANCHORS = ["自由", "左上角", "上方", "右上角", "左边", "居中",
           "右边", "左下角", "下方", "右下角"]
ANCHORS_EN = ["Free", "Top-left", "Top", "Top-right", "Left", "Center",
              "Right", "Bottom-left", "Bottom", "Bottom-right"]
ANCHOR_RC = [(-1, -1), (0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (2, 0), (2, 1), (2, 2)]
# 逻辑码（配置里持久化，跟语言无关）：free tl t tr l c r bl b br
ANCHOR_EN = ["free", "tl", "t", "tr", "l", "c", "r", "bl", "b", "br"]
# 英文文案的方位短名（贴图 hover 文本用）：anchor_short_en[i]
SIZE_PRESETS = [50, 75, 100, 125, 150, 200, 300]
VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".wmv", ".m4v", ".mpg", ".mpeg", ".ts", ".flv", ".3gp"}
GIF_EXTS = {".gif"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif", ".tif", ".tiff", ".ico", ".svg",
              ".pbm", ".pgm", ".ppm", ".xbm", ".xpm"}
MEDIA_EXTS = VIDEO_EXTS | IMAGE_EXTS | GIF_EXTS

MARGIN = 10          # 吸附时素材离屏幕边缘的像素
SNAP_DIST = 40       # 拖动结束时的吸附判定距离
MIN_W, MIN_H = 48, 48
OPAC_STEPS = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]

# —— 全局热键（串可在「设置」里改，解析见 parse_hk；要求带修饰键） ——
HK_KEYS = ("pass", "shot", "panel", "save", "switch", "del", "delall", "color", "region")
HK_DEF = {"pass": "Ctrl+Alt+P", "shot": "Ctrl+Alt+S", "panel": "Ctrl+Alt+Q",
          # ↓ 临时截图四键 / 取色 / 框选：默认空 = 不绑定，用户自己在设置里按（须带修饰键）
          "save": "", "switch": "", "del": "", "delall": "", "color": "", "region": ""}
HK = dict(HK_DEF)                       # 当前生效（用户可改，存配置）
HKC = {"pass": None, "shot": None, "panel": None,
       "save": None, "switch": None, "del": None, "delall": None,
       "color": None, "region": None}   # (ctrl,alt,shift,meta,vk)
SHOT_SLOTS = 16                         # 临时截图最多同时存几张（纯内存循环）
# —— 临时截图设置（存配置） ——
SHOT_DEF = {"anchor": 3, "pct": 33, "opacity": 100, "cursor": 1}   # 右上、33% 屏宽、不透明、抓鼠标指针
SHOT_CFG = dict(SHOT_DEF)
# 文字贴图默认样式（中性灰安全组合；颜色由用户自己改）
TXT_DEF = {"text": "双击编辑文字", "font_px": 56, "color": "#F2F2F2",
           "bold": True, "bg": True, "bgcolor": "#202022"}
# 文字贴图内容颜色的常用色板（用户素材的可选颜色，非界面配色）
TXT_SWATCH = ["#F2F2F2", "#202022", "#E53935", "#FB8C00",
              "#FDD835", "#43A047", "#1E88E5", "#8E24AA"]
# 符号面板（排版符号，插进用户文字内容里，非界面图标）
SYMBOL_GROUPS = [
    ("箭头", "→←↑↓↔↕↗↙↖↘⇒⇐⟲⟳↥↧⟵⟶"),
    ("数学", "+−×÷=≠≈±∞√∑∫π≤≥%‰"),
    ("图形", "●○■□▲△▼▽◆◇★☆♠♣♥♦✓✗⚠⚑"),
    ("括号", "【】（）〔〕「」『』《》〈〉…·"),
    ("标记", "※№℃℉°′″｜＃％＆＠＊"),
    ("货币", "¥€$£¢©®™†‡"),
]
# 常用标点：字符 → Windows VK（QKeySequence 解析不到时的兜底）
_VK_PUNCT = {",": 0xBC, ".": 0xBE, ";": 0xBA, "'": 0xDE, "[": 0xDB, "]": 0xDD,
             "-": 0xBD, "=": 0xBB, "\\": 0xDC, "`": 0xC0, "/": 0xBF, " ": 0x20}

# —— 临时截图多槽（纯内存，不落盘；切换/删除/保存全走热键或右键） ——
_shots = []             # [ShotOverlay,...] 最多 SHOT_SLOTS，满则顶掉最老；_shot[0]=当前显示

# —— 配色（自写：中性灰单色系，深灰底+浅灰字；不使用渐变/发光/玻璃拟态）——
PLACE_BG = QColor(24, 24, 26, 255)
PLACE_FG = QColor(213, 213, 213, 255)

# —— 语言（中英切换；KEY=中文原文，EN=英文；D() 未命中回退中文） ——
LANG = {"code": "zh"}
_STARTUP_LANG = {"code": "zh"}   # main 里取启动期配置（QApplication 前读盘）


def _en_table():
    app_ = "ScreenPin"
    return {
        # 应用/标题
        "屏幕贴图": app_, "app": app_,
        "关于 " + app_: "About " + app_,
        # 启动面板/托盘/单实例
        "把图片或视频拖到本窗口，\n或点下面的按钮选择。":
            "Drag an image/video onto this window,\nor click the button below.",
        "选择图片/视频…": "Open image/video…",
        "新建文字贴图": "New text overlay",
        "设置": "Settings",
        "关于": "About", "退出": "Quit",
        "已经有一个「" + app_ + "」在运行了。\n右下角托盘里能找到它，右键素材可改一切。":
            "A \"" + app_ + "\" is already running.\nFind it in the tray; right-click to change everything.",
        "打开新贴图…": "New overlay…",
        "全部置顶": "Re-assert topmost (all)",
        "全部解除穿透": "Disable click-through (all)",
        # 菜单
        "打开…": "Open…", "打开图片/视频…": "Open image/video…",
        "最近打开": "Recent", "（无）": "(empty)",
        "复制文件路径": "Copy file path",
        "大小": "Size", "放大 +10%": "Bigger +10%", "缩小 -10%": "Smaller -10%",
        "保持宽高比（缩放时不变形）": "Keep aspect ratio",
        "隐藏其余只留这个": "Close others (keep this)",
        "位置（吸附到屏幕）": "Position (snap to screen)",
        "适配屏幕 90%": "Fit screen 90%",
        "不透明度": "Opacity",
        "更不透明 (+10%)": "More opaque (+10%)",
        "更透明 (-10%)": "More transparent (-10%)",
        "播放": "Playback", "播放 / 暂停": "Play / Pause",
        "循环播放": "Loop", "静音": "Mute",
        "音量…": "Volume…", "vol %d": "Vol %d",
        "（非视频，无播放选项）": "(not a video)",
        "置顶显示（占最高）": "Topmost (always on top)",
        "鼠标点击穿透（点击穿到下层）": "Click-through (mouse passes down)",
        "关闭这个贴图": "Close this overlay",
        "退出（全部关闭）": "Quit (close all)",
        "关键帧": "Keyframes",
        # 关键帧
        "开始关键帧动画": "Start keyframe animation",
        "停止动画": "Stop animation",
        "添加关键帧(当前位置)": "Add keyframe (current pos)",
        "清除全部关键帧": "Clear all keyframes",
        "关键帧列表": "Keyframe list",
        "没设关键帧": "No keyframes",
        "总时长 %.1f 秒": "Total %.1f s",
        "删第 %d 个": "Delete #%d",
        "当前位置设为关键帧 %d": "Position set as keyframe %d",
        "关键帧": "Keyframes", "动画：播放中": "Animation: playing",
        "动画：已停止": "Animation: stopped",
        "已加关键帧": "Keyframe added", "已清关键帧": "Keyframes cleared",
        # 文字贴图
        "新建文字贴图": "New text overlay",
        "编辑文字/样式…": "Edit text/style…",
        "插入符号": "Insert symbol",
        "复制文本": "Copy text",
        # 截图热键
        "临时截图(热键)": "Temp screenshot (hotkey)",
        # 设置框
        "全局热键": "Global hotkeys",
        "点击穿透切换": "Toggle click-through",
        "截图显示/隐藏": "Screenshot show/hide",
        "要求带修饰键 (Ctrl/Alt/Shift/Win)": "Requires modifier (Ctrl/Alt/Shift/Win)",
        "临时截图": "Temp screenshot",
        "放置位置": "Position", "宽度": "Width",
        "不透明度 %": "Opacity %",
        "截图时包含鼠标指针": "Include mouse cursor in screenshots",
        "界面语言": "Language", "中文": "Chinese", "English": "English",
        "无效热键（须带 Ctrl/Alt/Shift/Win）": "Invalid hotkey (needs Ctrl/Alt/Shift/Win)",
        # 运行提示
        "不支持的文件类型": "Unsupported file type",
        "无法识别的文件": "Unreadable file",
        "打开失败": "Open failed", "第 %d 个": "#%d",
        # 小面板 / 多图片批量设置
        "小面板": "Panel", "小面板开/关": "Panel toggle",
        "多图片批量设置…": "Batch (multi-image)…",
        "应用位置": "Apply position", "应用大小": "Apply size",
        "应用到选中": "Apply to selected", "关闭选中的贴图": "Close selected",
        "全选": "Select all", "清空选择": "Clear",
        "（没有贴图）": "(no overlays)", "当前贴图": "Overlays",
        "文字": "Text", "贴图": "Overlay", "关闭面板": "Close panel",
        "点击穿透": "Click-through", "中英切换": "中文/EN", "保持": "Keep",
        "已复制文本": "Text copied",
        "音量 %d": "Vol %d",
        "编辑文字/样式…（含符号面板）": "Edit text/style… (symbol palette)",
        "无法播放该文件": "Cannot play this file",
        "视频出错：%s": "Video error: %s",
        "未知": "unknown",
        "播放结束（右键可开循环）": "Ended (right-click for loop)",
        "无法播放该视频（缺解码器？试试 mp4）": "Cannot play (decoder missing? try mp4)",
        "视频播放出错": "Playback error",
        "播放中": "Playing", "已暂停": "Paused",
        "大小：%d%%": "Size: %d%%",
        "已适配屏幕": "Fitted to screen",
        "位置：": "Position: ",
        "已吸附：": "Snapped: ",
        "置顶：": "Topmost: ", "开": "on", "关": "off",
        "不透明度：%d%%": "Opacity: %d%%",
        "循环：": "Loop: ", "静音：": "Mute: ",
        "保持比例：": "Aspect: ",
        "无法播放": "Cannot play",
        "已复制路径": "Path copied",
        "已关闭其他贴图": "Other overlays closed",
        "选择图片或视频": "Open image or video",
        "已吸附": "Snapped", "位置": "Position",
        # v1.6 个性化/更新/官网
        "个性化": "Personalization", "主题": "Theme",
        "启动时恢复上次的贴图（默认关：每次启动自己选）":
            "Restore last overlays on start (off by default: pick each time)",
        "启动时检查更新": "Check for updates on start",
        "保存设置": "Save settings",
        "一键初始化": "Reset to defaults",
        "检查更新": "Check for updates",
        "打开官网": "Open website",
        "支持开发": "Support dev",
        "取色器": "Color picker",
        "框选截图": "Region screenshot",
        "取到颜色 %s（已复制）": "Picked %s (copied)",
        "取色失败": "Color pick failed",
        "取色热键": "Color picker hotkey",
        "框选截图热键": "Region screenshot hotkey",
        "变换": "Transform",
        "旋转 90°": "Rotate 90°",
        "左右镜像": "Flip horizontal",
        "上下镜像": "Flip vertical",
        "标注（红框/箭头/涂写）": "Annotate (box/arrow/scribble/mosaic)",
        "开始标注": "Start annotating",
        "完成标注": "Done annotating",
        "红框": "Box",
        "箭头": "Arrow",
        "涂写": "Scribble",
        "马赛克": "Mosaic",
        "画笔颜色": "Pen color",
        "笔画粗细": "Pen width",
        "撤销一笔": "Undo stroke",
        "清除全部标注": "Clear annotations",
        "拖拽框选区域，松开即截图（Esc 取消）":
            "Drag to select a region, release to capture (Esc cancels)",
        "发现新版本 %s": "New version %s available",
        "当前版本 %s，去官网下载最新版？": "Current %s. Open website to download?",
        "已是最新版本 %s。": "You are on the latest version %s.",
        "更新地址未配置（开源仓库就绪后填写）。": "Update URL not configured yet.",
        "检查更新失败（网络不通？）\n": "Update check failed (no network?)\n",
        "将关闭所有贴图，并把热键/主题/语言/截图设置恢复默认。\n确定继续？":
            "This closes all overlays and resets hotkeys/theme/language/screenshot settings.\nContinue?",
        "无法打开官网：%s": "Cannot open website: %s",
        "反馈：": "Feedback: ",
        # 批次4 补键
        "改": "Edit", "图片": "Image", "视频": "Video",
        "点击穿透热键": "Click-through hotkey",
        "临时截图热键": "Screenshot hotkey",
        "小面板热键": "Panel hotkey",
        "保存临时图片热键": "Save shot hotkey",
        "切换临时图片热键": "Cycle shot hotkey",
        "删除临时图片热键": "Delete shot hotkey",
        "删除全部图片热键": "Delete all shots hotkey",
        "未绑定（点“改”设置）": "Unbound (click Edit)",
        "热键冲突：%s 已被占用": "Hotkey conflict: %s already used",
        "保存临时图片…": "Save screenshot…",
        "下一张临时图片": "Next screenshot",
        "删除这张临时图片": "Delete this screenshot",
        "删除全部临时图片": "Delete all screenshots",
        "没有临时图片": "No screenshots",
        "已清全部临时图片": "All screenshots deleted",
        "已切换": "Switched", "已隐藏": "Hidden", "已删除": "Deleted",
        "截图已显示": "Screenshot shown",
        "选择保存目录": "Choose folder",
        "保存中…": "Saving…",
        "已保存": "Saved",
        "保存失败": "Save failed",
        "媒体文件": "Media", "所有文件 (*.*)": "All files (*.*)",
        "按新组合键（须带 Ctrl/Alt/Shift/Win）…\n只按 Esc 取消":
            "Press new combo (Ctrl/Alt/Shift/Win)…\nEsc to cancel",
        "截图失败": "Screenshot failed",
        "截图已显示，再按热键隐藏": "Screenshot shown. Press hotkey to hide",
        "已到关键帧": "At keyframe",
        "循环动画": "Loop animation",
        "箭头": "Arrows", "数学": "Math", "图形": "Shapes",
        "括号": "Brackets", "标记": "Marks", "货币": "Currency",
        "字号": "Font size", "粗体": "Bold", "底色": "Background",
        "文字颜色": "Text color", "背景颜色": "Background color",
    }


def D(s):
    """翻译：中文 KEY → English；EN 里没有就回中文。"""
    if LANG["code"] != "en" or not isinstance(s, str):
        return s
    try:
        return _en_table().get(s, s)
    except Exception:
        return s


def anchor_list():
    return ANCHORS_EN if LANG["code"] == "en" else ANCHORS


def anchor_short(i):
    """中文=全名；EN=短名（贴图 hover 文本）。"""
    if LANG["code"] != "en":
        return ANCHORS[i] if 0 <= i < len(ANCHORS) else ""
    short = ["free", "TL", "Top", "TR", "L", "C", "R", "BL", "Bottom", "BR"]
    return short[i] if 0 <= i < len(short) else ""


app = None
overlays = []
single_file = None       # 初始要打开的文件（命令行第一个参数）
tray = None
icon_path = None
_tip_box = [None]        # 当前提示框（新提示出现时关掉旧的）
_hotkey_timer = [None]
_hotkey_prev = {k: False for k in HK_KEYS}
_shot = [None]           # 当前活动临时截图窗（None=全部隐藏；槽位在 _shots）
_shots = []              # 临时截图槽位（多存，纯内存，最多 SHOT_SLOTS）
_mp = [None]             # 小面板（唯一，热键/托盘左键开关）
_panel = [None]          # 启动面板（托盘菜单/语言刷新要用）
_exiting = [False]       # 真退出闸（关窗口≠退出，只有退出动作才置位）


# ================= 工具函数 =================

def icon_file():
    global icon_path
    if icon_path:
        return icon_path
    cand = []
    if getattr(sys, "frozen", False):
        cand.append(os.path.join(sys._MEIPASS, "pin.ico"))
    cand.append(os.path.join(base_dir(), "pin.ico"))
    for p in cand:
        if os.path.exists(p):
            icon_path = p
            return p
    return None


def base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _dbg(msg):
    """SCREENPIN_DEBUG=1 时往 %TEMP%\\screenpin_debug.log 追一行（exe 内无控制台，靠它验后端）。"""
    if not os.environ.get("SCREENPIN_DEBUG"):
        return
    try:
        import time as _t
        p = os.path.join(os.environ.get("TEMP", base_dir()), "screenpin_debug.log")
        with open(p, "a", encoding="utf-8") as f:
            f.write("%.3f %s\n" % (_t.time(), str(msg)))
    except Exception:
        pass


def app_icon():
    p = icon_file()
    if p and os.path.exists(p):
        return QIcon(p)
    return QIcon()


def cfg_dir():
    env = os.environ.get("SCREENPIN_CFG_DIR")
    if env:
        return env
    return os.path.join(os.environ.get("LOCALAPPDATA", base_dir()), "ScreenPin")


def cfg_path():
    return os.path.join(cfg_dir(), "config.json")


def load_config():
    try:
        p = cfg_path()
        if os.path.isfile(p):
            # utf-8-sig：兼容记事本/PS 写出的 BOM，否则 json.load 吞异常回默认
            with open(p, "r", encoding="utf-8-sig") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def apply_global_cfg(cfg):
    """从配置恢复语言/热键/截图设置（解析失败回默认）。"""
    try:
        LANG["code"] = "en" if str(cfg.get("lang", "zh")).lower() == "en" else "zh"
    except Exception:
        LANG["code"] = "zh"
    try:
        for k in HK_KEYS:
            s = cfg.get("%s_hotkey" % k)
            if s is None:
                s = HK_DEF[k]
            HK[k] = (s or "").strip()
    except Exception:
        pass
    for k in HK:
        HKC[k] = parse_hk(HK.get(k, "")) or None   # 空串/违规 → None（未绑定）
    try:
        SHOT_CFG["anchor"] = max(1, min(9, int(cfg.get("shot_anchor", SHOT_DEF["anchor"]))))
        SHOT_CFG["pct"] = max(5, min(100, int(cfg.get("shot_pct", SHOT_DEF["pct"]))))
        SHOT_CFG["opacity"] = max(10, min(100, int(cfg.get("shot_opacity", SHOT_DEF["opacity"]))))
        SHOT_CFG["cursor"] = 1 if int(cfg.get("shot_cursor", SHOT_DEF["cursor"])) else 0
    except Exception:
        SHOT_CFG.update(SHOT_DEF)
    try:
        SETTINGS["theme"] = max(0, min(len(THEMES) - 1, int(cfg.get("theme", 0))))
    except Exception:
        SETTINGS["theme"] = 0
    try:
        SETTINGS["restore"] = 1 if int(cfg.get("restore", 0)) else 0   # 默认 0=启动不复读
    except Exception:
        SETTINGS["restore"] = 0
    try:
        SETTINGS["autoupdate"] = 1 if int(cfg.get("autoupdate", 1)) else 0
    except Exception:
        SETTINGS["autoupdate"] = 1


def save_config():
    """配置：素材=文件路径+锚点+关键帧；文字贴图=内容样式；不记屏幕坐标。
    （换分辨率/换显示器时窗口坐标会跑到屏幕外，所以坐标不持久化。）"""
    try:
        data = {"overlays": [], "lang": LANG.get("code", "zh"),
                "shot_anchor": SHOT_CFG["anchor"], "shot_pct": SHOT_CFG["pct"],
                "shot_opacity": SHOT_CFG["opacity"],
                "shot_cursor": int(SHOT_CFG.get("cursor", 1)),
                "theme": int(SETTINGS.get("theme", 0)),
                "restore": int(SETTINGS.get("restore", 0)),
                "autoupdate": int(SETTINGS.get("autoupdate", 1))}
        for k in HK_KEYS:                     # 7 键统一存（空串=未绑定，如实写回）
            data["%s_hotkey" % k] = (HK.get(k, HK_DEF.get(k, "")) or "").strip()
        for o in overlays:
            try:
                if getattr(o, "kind", None) == "text":
                    data["overlays"].append({
                        "type": "text", "anchor": o.anchor,
                        "text": o.text, "font_px": getattr(o, "_base_font", o.font_px),
                        "color": o.text_color.name(), "bold": bool(o.bold),
                        "bg": bool(o.bg_on), "bgcolor": o.bg_color.name(),
                    })
                    continue
                if not o.source_path:
                    continue
                item = {"file": o.source_path, "anchor": o.anchor,
                        "tf": int(getattr(o, "_tf", 0)) & 3,
                        "rot": int(getattr(o, "_rot", 0)) & 3}
                kc = getattr(o, "kfc", None)
                if kc is not None and getattr(kc, "kfs", None):
                    item["kf"] = list(kc.kfs)
                    item["kf_loop"] = bool(getattr(kc, "loop", True))
                data["overlays"].append(item)
            except Exception:
                continue
        os.makedirs(cfg_dir(), exist_ok=True)
        tmp = cfg_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, cfg_path())
    except Exception:
        pass


def file_kind(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in VIDEO_EXTS:
        return "video"
    if ext in GIF_EXTS:
        return "gif"
    if ext in IMAGE_EXTS:
        return "image"
    return None


def is_media_file(path):
    return file_kind(path) is not None


def list_files(paths):
    out = []
    for p in paths:
        p = (p or "").strip().strip('"')
        if not p:
            continue
        if os.path.isdir(p):
            try:
                for n in sorted(os.listdir(p)):
                    fp = os.path.join(p, n)
                    if os.path.isfile(fp) and is_media_file(fp):
                        out.append(fp)
            except Exception:
                pass
        elif os.path.isfile(p) and is_media_file(p):
            out.append(p)
    return out


def screen_rect_for(w):
    from PyQt5.QtGui import QGuiApplication
    try:
        fr = w.frameGeometry()
        s = QGuiApplication.screenAt(fr.center())
        if s is None:
            s = QGuiApplication.screenAt(w.pos())
        if s is None:
            s = QGuiApplication.primaryScreen()
        return s.availableGeometry()
    except Exception:
        return QGuiApplication.primaryScreen().availableGeometry()


def show_msg(anchor_w, text):
    """在素材旁短暂显示提示（无边框、置顶、自动消失；新提示替换旧提示）。"""
    text = D(text)
    try:
        old = _tip_box[0]
        _tip_box[0] = None
        if old is not None:
            try:
                old.close()
            except Exception:
                pass
        lab = QLabel(text)
        lab.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        pal = lab.palette()
        pal.setColor(lab.backgroundRole(), QColor(32, 32, 34, 235))
        pal.setColor(lab.foregroundRole(), QColor(235, 235, 235, 255))
        lab.setPalette(pal)
        lab.setAutoFillBackground(True)
        f = QFont()
        f.setPointSize(10)
        lab.setFont(f)
        lab.adjustSize()
        try:
            g = screen_rect_for(anchor_w)
            pos = anchor_w.pos() + QPoint(6, anchor_w.height() + 6)
            if pos.x() + lab.width() > g.right():
                pos.setX(g.right() - lab.width())
            if pos.y() + lab.height() > g.bottom():
                pos.setY(anchor_w.y() - lab.height() - 6)
            if pos.x() < g.left():
                pos.setX(g.left() + 4)
            if pos.y() < g.top():
                pos.setY(g.top() + 4)
            lab.move(pos)
        except Exception:
            pass
        lab.show()
        _tip_box[0] = lab

        def _kill(l, box=_tip_box):
            if box[0] is l:
                box[0] = None
            try:
                l.close()
            except Exception:
                pass

        QTimer.singleShot(1600, lambda: _kill(lab))
        return lab
    except Exception:
        return None


def hb(m, t):
    a = m.addAction(t)
    a.setEnabled(False)
    return a


def act(m, title, fn, checked=None):
    a = QAction(title, m)
    if checked is not None:
        a.setCheckable(True)
        a.setChecked(bool(checked))
    a.triggered.connect(fn)
    m.addAction(a)
    return a


def slider(val, vertical, parent=None):
    s = QSlider(Qt.Vertical if vertical else Qt.Horizontal, parent)
    s.setRange(0, 100)
    s.setValue(int(val))
    if not vertical:
        s.setFixedWidth(140)
    return s


# ================= 视频输出说明 =================
# 实测（PyQt5 5.15.11 + Qt WMF 后端）：QMediaPlayer.setVideoOutput(自定义
# QAbstractVideoSurface) 会进程级硬崩 0xC0000409，setVideoOutput(对象桥) 不被识别；
# QVideoWidget 正常。故视频走「QVideoWidget 子控件 + WA_TransparentForMouseEvents」，
# 透明度统一用 setWindowOpacity（右键菜单是独立 popup，不受影响）。


# ---------- 右键菜单分块（基础/文字贴图共用，菜单文案全部走 D() 翻译） ----------

def _menu_open(w, m):
    om = QMenu(D("打开…"), m)
    act(om, D("打开图片/视频…"), w.pick_file)
    rm = QMenu(D("最近打开"), om)
    if w.recent_files:
        for fp in w.recent_files[:10]:
            act(rm, os.path.basename(fp), lambda fp=fp: w.load(fp))
    else:
        hb(rm, D("（无）"))
    om.addMenu(rm)
    m.addMenu(om)


def _menu_size(w, m):
    sm = QMenu(D("大小"), m)
    for pct_v in SIZE_PRESETS:
        act(sm, "%d%%" % pct_v, lambda p=pct_v: w.set_pct(p),
            checked=(w.pct() == pct_v))
    act(sm, D("放大 +10%"), lambda: w.step_pct(10))
    act(sm, D("缩小 -10%"), lambda: w.step_pct(-10))
    sm.addAction(w.a_ratio)
    act(sm, D("隐藏其余只留这个"), w.solo)
    m.addMenu(sm)


def _menu_anchor(w, m):
    am = QMenu(D("位置（吸附到屏幕）"), m)
    names = anchor_list()
    for i, name in enumerate(names):
        if i == 0:
            act(am, name, lambda: w.set_anchor(0), checked=(w.anchor == 0))
            am.addSeparator()
        else:
            act(am, name, lambda i=i: w.set_anchor(i), checked=(w.anchor == i))
    act(am, D("适配屏幕 90%"), lambda: w.fit_screen(0.9))
    m.addMenu(am)


def _menu_opacity(w, m):
    om2 = QMenu(D("不透明度"), m)
    for v in OPAC_STEPS:
        act(om2, "%d%%" % v, lambda v=v: w.set_opacity(v),
            checked=(w.opacity_ == v))
    om2.addSeparator()
    act(om2, D("更不透明 (+10%)"), lambda: w.bump_opacity(10))
    act(om2, D("更透明 (-10%)"), lambda: w.bump_opacity(-10))
    m.addMenu(om2)


def _menu_play(w, m):
    mm = QMenu(D("播放"), m)
    if w.is_video:
        mm.addAction(w.a_play)
        mm.addAction(w.a_loop)
        mm.addAction(w.a_mute)
        vol_wrap = QWidget(None, Qt.Popup | Qt.FramelessWindowHint)
        vol_lay = QVBoxLayout(vol_wrap)
        vol_lay.setContentsMargins(6, 4, 6, 4)
        vol_lay.setSpacing(4)
        vol_lb = QLabel(D("音量 %d") % w.volume_)
        vol_lb.setStyleSheet("color:#dddddd; background:#202022; padding:2px 6px;")
        vol_sl = slider(w.volume_, False, vol_wrap)
        vol_sl.valueChanged.connect(w.set_volume)
        vol_sl.valueChanged.connect(lambda v, lb=vol_lb: lb.setText(D("音量 %d") % v))
        vol_lay.addWidget(vol_lb)
        vol_lay.addWidget(vol_sl)
        vol_wrap.setStyleSheet("background:#202022;")

        def open_vol():
            vol_wrap.move(QCursor.pos())
            vol_wrap.show()
            vol_wrap.raise_()

        a_vol = QAction(D("音量…"), mm)
        a_vol.triggered.connect(open_vol)
        mm.addAction(a_vol)
    else:
        hb(mm, D("（非视频，无播放选项）"))
    m.addMenu(mm)


def _menu_kf(w, m):
    """关键帧：播放/停止、打点、循环、列表(带删除)、清空。"""
    kf = getattr(w, "kfc", None)
    if kf is None:
        return
    sub = QMenu(D("关键帧"), m)
    if kf.playing:
        act(sub, D("停止动画"), kf.stop)
    else:
        act(sub, D("开始关键帧动画"), kf.start)

    def _add():
        n = kf.add()
        show_msg(w, D("已加关键帧") + " " + (D("第 %d 个") % n))
    act(sub, D("添加关键帧(当前位置)"), _add)
    if kf.kfs:
        def _clr():
            kf.clear()
            show_msg(w, D("已清关键帧"))
        act(sub, D("清除全部关键帧"), _clr)
        hb(sub, D("总时长 %.1f 秒") % kf.total())
        lst = QMenu(D("关键帧列表"), sub)
        for i, item in enumerate(list(kf.kfs)):
            t, x, y = item
            lab = "%s @%d,%d  %.1fs" % (D("第 %d 个") % (i + 1), x, y, t)
            act(lst, lab, lambda i=i: kf.remove(i))
        sub.addMenu(lst)

        def _tgl():
            kf.loop = not kf.loop
        act(sub, D("循环动画"), _tgl, checked=bool(kf.loop))
    else:
        hb(sub, D("没设关键帧"))
    m.addMenu(sub)


def _menu_tail(w, m):
    m.addSeparator()
    at = QAction(D("置顶显示（占最高）"), m)
    at.setCheckable(True)
    at.setChecked(bool(w.a_topmost.isChecked()))

    def _tm():
        w.a_topmost.setChecked(not w.a_topmost.isChecked())
        w.toggle_topmost()
    at.triggered.connect(_tm)
    m.addAction(at)
    ac = QAction(D("鼠标点击穿透（点击穿到下层）"), m)
    ac.setCheckable(True)
    ac.setChecked(bool(w.click_through))
    ac.triggered.connect(lambda: set_click_through(w, not w.click_through))
    m.addAction(ac)
    act(m, D("关闭这个贴图"), w.close)
    act(m, D("退出（全部关闭）"), quit_app)
    m.addSeparator()
    act(m, D("关于 " + APP_NAME), w.show_about)


# ================= 悬浮窗本体 =================

class OverlayWindow(QWidget):
    def __init__(self, path=None):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)

        self.kind = None
        self.source_path = None
        self.anchor = 0            # 0=自由，1..9=ANCHORS
        self.opacity_ = 100
        self.click_through = False
        self.volume_ = 70
        self.muted = False
        self.loop_ = True
        self.keep_ratio = True
        self.base = QSize(640, 480)
        self.scale = 1.0
        self._size_done = False    # 初始缩放钳制只做一次
        self.dragging = False
        self.resizing = False
        self.resize_corner = 1
        self.drag_off = QPoint(0, 0)
        self.start_geom = QRect()
        self._pressed = False
        self._press_pos = QPoint(0, 0)
        self._press_btn = 0
        self._drag_moved = False
        self._tf = 0            # bit0=左右镜像 bit1=上下镜像
        self._rot = 0           # 90° × N
        self._annot = False
        self._tool = "pen"
        self._pen_c = "#E53935"
        self._pen_w = 4
        self._strokes = []
        self._cur_stroke = None
        self.movie = None
        self._pix = None
        self.is_video = False
        self.player = None
        self._stopping = False
        self._image_name = ""
        self.video_name = "视频"
        self.recent_files = []
        self.kfc = KeyframeCtrl(self)     # 关键帧（位置动画），类在后面定义、调用时已加载

        self._build_menu_actions()

        # 视频链：player -> QVideoWidget 子控件（surface 方案在本机实测硬崩，弃用）
        self.video = QVideoWidget(self)
        self.video.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.video.setGeometry(self.rect())
        self.video.hide()
        self.vlabel = QLabel(self)
        self.vlabel.setStyleSheet("background-color:#CC1E1E20; color:#E8E8E8; "
                                  "padding:2px 8px; border:none;")
        self.vlabel.hide()
        self.avp = None                 # PyAV 引擎实例
        self.using_av = False           # True=自己画帧；False=QVideoWidget 画
        self.av_pix = None              # 当前视频帧 QImage
        self._av_timer = QTimer(self)
        self._av_timer.setInterval(33)
        self._av_timer.timeout.connect(self._av_tick)
        self.player = QMediaPlayer(self)
        try:
            self.player.setVideoOutput(self.video)
        except Exception:
            pass
        self.player.setVolume(self.volume_)
        self.player.mediaStatusChanged.connect(self._on_status)
        self.player.stateChanged.connect(self._on_state)
        try:
            self.player.metaDataChanged.connect(self._on_meta)
        except Exception:
            pass
        try:
            self.player.error.connect(self._on_media_error)
        except Exception:
            try:
                self.player.error[str].connect(self._on_media_error)
            except Exception:
                pass

        if path:
            QTimer.singleShot(0, lambda p=path: self.load(p))

    # ---------- 菜单动作（显式 setter，避免依赖构造器属性参数） ----------

    def _build_menu_actions(self):
        self.a_topmost = QAction("置顶显示（占最高）", self)
        self.a_topmost.setCheckable(True)
        self.a_topmost.setChecked(True)
        self.a_topmost.triggered.connect(self.toggle_topmost)

        self.a_clickthru = QAction("鼠标点击穿透（点击穿到下层）", self)
        self.a_clickthru.setCheckable(True)
        self.a_clickthru.setChecked(False)
        self.a_clickthru.triggered.connect(self.toggle_click_through)

        self.a_loop = QAction("循环播放", self)
        self.a_loop.setCheckable(True)
        self.a_loop.setChecked(True)
        self.a_loop.triggered.connect(self.toggle_loop)

        self.a_mute = QAction("静音", self)
        self.a_mute.setCheckable(True)
        self.a_mute.setChecked(False)
        self.a_mute.triggered.connect(self.toggle_mute)

        self.a_ratio = QAction("保持宽高比（缩放时不变形）", self)
        self.a_ratio.setCheckable(True)
        self.a_ratio.setChecked(True)
        self.a_ratio.triggered.connect(self.toggle_ratio)

        self.a_play = QAction("播放 / 暂停", self)
        self.a_play.triggered.connect(self.toggle_play)

    # ---------- 素材加载 ----------

    def load(self, path):
        path = os.path.abspath(path)
        kind = file_kind(path)
        if kind is None:
            show_msg(self, "不支持的文件类型")
            return False
        self._stop_media()
        self.kind = kind
        self.source_path = path
        name = os.path.basename(path)
        # 最近打开（去重、置顶、最多 10 条）
        try:
            if path in self.recent_files:
                self.recent_files.remove(path)
            self.recent_files.insert(0, path)
            del self.recent_files[10:]
        except Exception:
            pass
        try:
            if kind == "video":
                self.is_video = True
                disp = name if len(name) <= 24 else name[:22] + "…"
                self.video_name = disp
                self.vlabel.setText(disp)
                self.vlabel.show()
                self.vlabel.adjustSize()
                self.movie = None
                self._pix = None
                self.video.show()
                self.video.raise_()
                self.vlabel.raise_()
                self._play_video()
                return True
            self.is_video = False
            self.video.hide()
            self.vlabel.hide()
            if kind == "gif":
                self._pix = None
                self._image_name = name
                mv = QMovie(path, QByteArray(), self)  # 重载: (fileName, format, parent)
                if mv.frameCount() == 0:
                    mv.setCacheMode(QMovie.CacheAll)
                mv.updated.connect(lambda *a: self.update())
                mv.start()
                self.movie = mv
                sz = mv.currentPixmap().size()
                if sz.isEmpty() or sz.width() <= 0:
                    img = QImage(path)
                    sz = QSize(img.width(), img.height())
                if sz.isEmpty() or sz.width() <= 0:
                    self.movie = None
                    show_msg(self, "无法识别的文件")
                    return False
                self._set_base(sz)
            else:
                pm = QPixmap(path)
                if pm.isNull():
                    show_msg(self, "无法识别的文件")
                    return False
                self.movie = None
                self._pix = pm
                self._image_name = name
                self._set_base(pm.size())
            self.apply_anchor()
            return True
        except Exception:
            if os.environ.get("SCREENPIN_DEBUG"):
                import traceback as _tb
                _tb.print_exc()
            show_msg(self, "打开失败")
            return False

    def _play_video(self):
        """先试 PyAV（自带解码，本机唯一能走通的路）；不行再回落 Qt WMF。"""
        self._stopping = False
        self._teardown_av()
        if not HAVE_AV or AvPlayer is None:
            _dbg("HAVE_AV=False (av import failed): %s" % (_AV_ERR or "unknown"))
        if HAVE_AV and AvPlayer is not None:
            try:
                p = AvPlayer(self)
                w, h, dur = p.probe(self.source_path)
                p.loop = self.loop_
                p.failed.connect(self._av_failed)
                p.ended.connect(self._av_ended)
                p.start()
                p.set_volume(self.volume_)
                p.set_muted(self.muted)
                self.avp = p
                self.using_av = True
                self._size_done = True
                self._set_base(QSize(w, h))
                self.video.hide()
                self.vlabel.hide()
                self._av_timer.start()
                _dbg("backend=av path=%s size=%dx%d dur=%.1f" % (self.source_path, w, h, dur))
                return
            except Exception as e:
                self._teardown_av()
                _dbg("av probe/start fail: %r" % (e,))
                # 落到 Qt WMF 后备
        try:
            self.player.stop()
            self.player.setMedia(QMediaContent(QUrl.fromLocalFile(self.source_path)))
            self.player.play()
            _dbg("backend=qt path=%s" % self.source_path)
        except Exception as e:
            _dbg("qt play fail: %r" % (e,))
            show_msg(self, "无法播放该文件")

    # ---------- PyAV 后备通道 ----------

    def _teardown_av(self):
        self._av_timer.stop()
        p = self.avp
        self.avp = None
        self.using_av = False
        self.av_pix = None
        if p is not None:
            try:
                p.stop()
            except Exception:
                pass

    def _av_tick(self):
        """30fps 取当前时刻该显示的帧（暂停时同一对象不重绘）。"""
        if not self.using_av or self.avp is None:
            return
        try:
            im = self.avp.snapshot(self.avp.position())
        except Exception:
            return
        if im is None or im.isNull():
            return
        if im is self.av_pix:
            return
        self.av_pix = im
        self.update()

    def _av_failed(self, msg):
        show_msg(self, D("视频出错：%s") % (msg or D("未知")))

    def _av_ended(self):
        show_msg(self, "播放结束（右键可开循环）")

    def _on_meta(self, *a):
        """读播放器元数据里的分辨率（QSize），修正素材原始尺寸/宽高比。"""
        try:
            mp = self.player
            if mp is None or not mp.isMetaDataAvailable():
                return
            keys = mp.metaDataKeys()
            for k in keys:
                v = mp.metaData(k)
                if isinstance(v, QSize) and v.width() > 0 and v.height() > 0:
                    self.base = QSize(v)
                    self._size_done = True
                    self._apply_size()
                    return
        except Exception:
            pass

    def _stop_media(self):
        self._stopping = True
        self._teardown_av()
        try:
            if self.player is not None:
                self.player.stop()
                self.player.setMedia(QMediaContent())
        except Exception:
            pass
        if self.movie is not None:
            try:
                self.movie.stop()
            except Exception:
                pass
            self.movie = None

    def _on_status(self, st):
        if self.using_av:
            return   # Qt 播放器此刻无媒体，信号不该出现；防串台
        if st == QMediaPlayer.LoadedMedia:
            self.vlabel.hide()
        if st == QMediaPlayer.InvalidMedia:
            show_msg(self, "无法播放该视频（缺解码器？试试 mp4）")

    def _on_media_error(self, *a):
        show_msg(self, "视频播放出错")

    def _on_state(self, st):
        if st == QMediaPlayer.StoppedState:
            if self._stopping:
                return
            if self.is_video and self.loop_ and self.source_path:
                QTimer.singleShot(30, self._replay)
            return
        if st == QMediaPlayer.PlayingState and self.is_video:
            self.vlabel.hide()
            show_msg(self, "播放中")

    def _replay(self):
        if self.is_video and self.source_path and self.player and not self._stopping:
            try:
                if self.player.media().isNull():
                    self.player.setMedia(QMediaContent(QUrl.fromLocalFile(self.source_path)))
                self.player.play()
            except Exception:
                pass

    def _set_base(self, sz):
        if sz is None or sz.width() <= 0 or sz.height() <= 0:
            return
        if sz == self.base:
            return
        self.base = QSize(sz)
        if not self._size_done:
            self._size_done = True
            try:
                g = screen_rect_for(self)
                maxw = int(g.width() * 0.45)
                if maxw > 0 and self.base.width() > maxw:
                    self.scale = maxw / float(self.base.width())
            except Exception:
                pass
        self._apply_size()

    def _apply_size(self):
        """按 base × scale 计算窗口尺寸（素材原始像素尺寸不随缩放改变）。"""
        if self.base.width() <= 0 or self.base.height() <= 0:
            return
        w = max(MIN_W, int(round(self.base.width() * self.scale)))
        h = max(MIN_H, int(round(w * self.base.height() / float(self.base.width()))))
        cur = self.frameGeometry()
        if cur.width() != w or cur.height() != h:
            self.resize(w, h)
            self.apply_anchor()
        self.update()

    # ---------- 尺寸 ----------

    def pct(self):
        if self.base.width() <= 0:
            return 100
        return int(round(self.scale * 100))

    def set_pct(self, v, announce=True):
        v = max(5, min(800, int(v)))
        self.scale = v / 100.0
        self._apply_size()
        if announce:
            show_msg(self, D("大小：%d%%") % self.pct())

    def step_pct(self, delta):
        self.set_pct(self.pct() + delta)

    def fit_screen(self, frac=0.9):
        if self.base.width() <= 0 or self.base.height() <= 0:
            return
        r = screen_rect_for(self)
        w = r.width() * frac
        h = r.height() * frac
        self.scale = min(w / self.base.width(), h / self.base.height())
        self._apply_size()
        self.apply_anchor()
        show_msg(self, "已适配屏幕")

    # ---------- 位置 ----------

    def set_anchor(self, idx):
        if idx < 0 or idx >= len(ANCHORS):
            return
        self.anchor = idx
        self.apply_anchor()
        if idx > 0:
            show_msg(self, D("位置：") + anchor_list()[idx])

    def apply_anchor(self):
        if self.anchor <= 0:
            return
        r, c = ANCHOR_RC[self.anchor]
        g = screen_rect_for(self)
        w, h = self.width(), self.height()
        if c == 0:
            x = g.left() + MARGIN
        elif c == 2:
            x = g.right() - MARGIN - w
        else:
            x = g.left() + (g.width() - w) // 2
        if r == 0:
            y = g.top() + MARGIN
        elif r == 2:
            y = g.bottom() - MARGIN - h
        else:
            y = g.top() + (g.height() - h) // 2
        if self.pos() != QPoint(x, y):
            self.move(x, y)

    def snap_to_nearest(self):
        g = screen_rect_for(self)
        w, h = self.width(), self.height()
        x = self.x()
        y = self.y()
        rc = 1
        cc = 1
        dl = abs(x - (g.left() + MARGIN))
        dr = abs(x - (g.right() - MARGIN - w))
        dcx = abs(x - (g.left() + (g.width() - w) // 2))
        if dl <= dr and dl <= dcx:
            cc = 0
            x = g.left() + MARGIN
        elif dr <= dcx:
            cc = 2
            x = g.right() - MARGIN - w
        else:
            cc = 1
            x = g.left() + (g.width() - w) // 2
        dt = abs(y - (g.top() + MARGIN))
        db = abs(y - (g.bottom() - MARGIN - h))
        dcy = abs(y - (g.top() + (g.height() - h) // 2))
        if dt <= db and dt <= dcy:
            rc = 0
            y = g.top() + MARGIN
        elif db <= dcy:
            rc = 2
            y = g.bottom() - MARGIN - h
        else:
            rc = 1
            y = g.top() + (g.height() - h) // 2
        for i in range(1, len(ANCHORS)):
            if ANCHOR_RC[i] == (rc, cc):
                self.anchor = i
                break
        self.move(x, y)
        show_msg(self, D("已吸附：") + anchor_list()[self.anchor])

    def auto_snap(self, moved):
        """拖动结束时：若靠近边缘/角则吸附；若原本锚定但被拖远则转为自由。"""
        if not moved:
            return
        g = screen_rect_for(self)
        w, h = self.width(), self.height()
        x, y = self.x(), self.y()
        h_ok = (abs(x - (g.left() + MARGIN)) <= SNAP_DIST or
                abs(x - (g.right() - MARGIN - w)) <= SNAP_DIST or
                abs(x - (g.left() + (g.width() - w) // 2)) <= SNAP_DIST)
        v_ok = (abs(y - (g.top() + MARGIN)) <= SNAP_DIST or
                abs(y - (g.bottom() - MARGIN - h)) <= SNAP_DIST or
                abs(y - (g.top() + (g.height() - h) // 2)) <= SNAP_DIST)
        if h_ok and v_ok:
            self.snap_to_nearest()
        elif self.anchor > 0:
            self.anchor = 0  # 拖离吸附位 → 自由

    # ---------- 置顶 / 穿透 / 透明度 ----------

    def toggle_topmost(self):
        on = self.a_topmost.isChecked()
        try:
            self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        except Exception:
            pass
        self.show()
        if self.click_through:
            # setWindowFlag 会重建窗口句柄，穿透样式要重打
            QTimer.singleShot(0, lambda: set_click_through(self, True))
        if on:
            force_topmost(self)
        show_msg(self, D("置顶：") + D("开" if on else "关"))

    def toggle_click_through(self):
        set_click_through(self, not self.click_through)

    def set_opacity(self, v):
        v = int(v)
        v = max(10, min(100, v))
        self.opacity_ = v
        try:
            # 透明度统一在窗口级处理；右键菜单是独立 popup 不受父窗影响
            self.setWindowOpacity(self.current_opacity())
        except Exception:
            pass
        self.update()
        show_msg(self, D("不透明度：%d%%") % v)

    def bump_opacity(self, d):
        i = min(range(len(OPAC_STEPS)), key=lambda k: abs(OPAC_STEPS[k] - self.opacity_))
        i = max(0, min(len(OPAC_STEPS) - 1, i + (1 if d > 0 else -1)))
        self.set_opacity(OPAC_STEPS[i])

    def current_opacity(self):
        return max(5, min(100, int(self.opacity_))) / 100.0

    # ---------- 播放控制 ----------

    def toggle_loop(self):
        self.loop_ = self.a_loop.isChecked()
        if self.avp is not None:
            try:
                self.avp.loop = self.loop_
            except Exception:
                pass
        show_msg(self, D("循环：") + D("开" if self.loop_ else "关"))

    def toggle_mute(self):
        self.muted = self.a_mute.isChecked()
        if self.avp is not None:
            try:
                self.avp.set_muted(self.muted)
            except Exception:
                pass
        if self.player is not None:
            try:
                self.player.setMuted(self.muted)
            except Exception:
                pass
        show_msg(self, D("静音：") + D("开" if self.muted else "关"))

    def toggle_ratio(self):
        self.keep_ratio = self.a_ratio.isChecked()
        self._apply_size()
        show_msg(self, D("保持比例：") + D("开" if self.keep_ratio else "关"))

    def toggle_play(self):
        if not self.is_video:
            return
        if self.using_av and self.avp is not None:
            try:
                self.avp.toggle()
                show_msg(self, "播放中" if self.avp.is_playing() else "已暂停")
            except Exception:
                show_msg(self, "无法播放")
            return
        if self.player is None:
            return
        try:
            if self.player.state() == QMediaPlayer.PlayingState:
                self.player.pause()
                show_msg(self, "已暂停")
            else:
                self.player.play()
                show_msg(self, "播放中")
        except Exception:
            show_msg(self, "无法播放")

    def set_volume(self, v):
        v = int(v)
        self.volume_ = max(0, min(100, v))
        if self.avp is not None:
            try:
                self.avp.set_volume(self.volume_)
            except Exception:
                pass
        if self.player is not None:
            try:
                self.player.setVolume(self.volume_)
            except Exception:
                pass

    # ---------- 右键菜单 ----------

    def build_menu(self):
        m = QMenu(self)
        _menu_open(self, m)
        m.addSeparator()
        act(m, D("复制文件路径"), self.copy_path)
        m.addSeparator()
        _menu_size(self, m)
        _menu_anchor(self, m)
        _menu_opacity(self, m)
        _menu_play(self, m)
        _menu_kf(self, m)
        if (getattr(self, "kind", None) in ("image", "gif")) or \
                (getattr(self, "is_video", False) and getattr(self, "using_av", False)):
            _menu_tf(self, m)
        _menu_tail(self, m)
        return m

    def contextMenuEvent(self, ev):
        if self.click_through:
            return
        self.build_menu().exec_(QCursor.pos())
        ev.accept()

    # ---------- 杂项 ----------

    def copy_path(self):
        try:
            QApplication.clipboard().setText(self.source_path or "")
            show_msg(self, "已复制路径")
        except Exception:
            pass

    def solo(self):
        for o in list(overlays):
            if o is not self:
                close_overlay(o)
        show_msg(self, "已关闭其他贴图")

    def pick_file(self):
        start = os.path.dirname(self.source_path) if self.source_path else ""
        paths, _ = QFileDialog.getOpenFileNames(self, D("选择图片或视频"), start, media_filter())
        if not paths:
            return
        self.load(paths[0])          # 第一张替换本窗，其余各开新贴图（多图一次开）
        for p in paths[1:]:
            open_overlay(p)

    def show_about(self):
        try:
            from PyQt5.QtWidgets import QMessageBox
            if LANG["code"] == "en":
                txt = (APP_NAME + " " + VERSION + "\n\n"
                       "Right-click changes everything.\n"
                       "%s click-through · %s temp screenshot\n"
                       "Site: %s\nFeedback: %s\n"
                       "Icon: Google Material Design Icons \"pin\" (Apache-2.0).") % (
                    HK.get("pass", "Ctrl+Alt+P"), HK.get("shot", "Ctrl+Alt+S"),
                    SITE_URL, FEEDBACK_MAIL)
            else:
                txt = (APP_NAME + " " + VERSION + "\n\n"
                       "右键改一切。\n"
                       "%s 点击穿透 · %s 临时截图\n"
                       "官网：%s\n反馈：%s\n"
                       "图标：Google Material Design Icons「pin」(Apache-2.0)。") % (
                    HK.get("pass", "Ctrl+Alt+P"), HK.get("shot", "Ctrl+Alt+S"),
                    SITE_URL, FEEDBACK_MAIL)
            QMessageBox.information(self, D("关于 " + APP_NAME), txt)
        except Exception:
            pass

    # ---------- 拖放 ----------

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        try:
            for u in ev.mimeData().urls():
                p = u.toLocalFile()
                if p and is_media_file(p):
                    self.load(p)
                    break
        except Exception:
            pass
        ev.acceptProposedAction()

    # ---------- 鼠标 ----------

    def mousePressEvent(self, ev):
        if self.click_through:
            return
        pos = ev.pos()
        if getattr(self, "_annot", False) and ev.button() == Qt.LeftButton:
            self._pressed = True
            self._press_pos = pos
            self._press_btn = ev.button()
            self._drag_moved = False
            self.dragging = False
            self.resizing = False
            self._cur_stroke = {"t": getattr(self, "_tool", "pen"),
                                "c": getattr(self, "_pen_c", "#E53935"),
                                "w": int(getattr(self, "_pen_w", 4)),
                                "pts": [[pos.x() / float(max(1, self.width())),
                                         pos.y() / float(max(1, self.height()))]]}
            self.update()
            ev.accept()
            return
        r = self.rect()
        self._pressed = True
        self._press_pos = pos
        self._press_btn = ev.button()
        self._drag_moved = False
        if ev.button() == Qt.LeftButton and r.width() >= 12 and r.height() >= 12:
            br = QRect(r.right() - 12, r.bottom() - 12, 12, 12)
            bl = QRect(r.left(), r.bottom() - 12, 12, 12)
            if br.contains(pos) or bl.contains(pos):
                self.resizing = True
                self.start_geom = self.geometry()
                self._start_scale = self.scale   # 文字贴图：拖角按宽度比例缩放字号
                self.resize_corner = 1 if br.contains(pos) else -1
                return
        if ev.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_off = ev.globalPos() - self.pos()
        ev.accept()

    def mouseMoveEvent(self, ev):
        if self.click_through:
            return
        p = ev.pos()
        st = getattr(self, "_cur_stroke", None)
        if st is not None and (ev.buttons() & Qt.LeftButton):
            Wn, Hn = float(max(1, self.width())), float(max(1, self.height()))
            nx, ny = p.x() / Wn, p.y() / Hn
            if st["t"] == "pen":
                if not st["pts"] or abs(nx - st["pts"][-1][0]) * Wn + abs(ny - st["pts"][-1][1]) * Hn >= 3:
                    st["pts"].append([nx, ny])
            else:
                if len(st["pts"]) == 1:
                    st["pts"].append([nx, ny])
                else:
                    st["pts"][1] = [nx, ny]
            self.update()
            ev.accept()
            return
        if self.resizing and (ev.buttons() & Qt.LeftButton):
            g = self.start_geom
            dx = p.x() - self._press_pos.x()
            dy = p.y() - self._press_pos.y()
            if self.resize_corner > 0:
                w1 = g.width() + dx
                h1 = g.height() + dy
            else:
                w1 = g.width() - dx
                h1 = g.height() - dy
            w1 = max(MIN_W, w1)
            if getattr(self, "kind", None) == "text":
                # 文字贴图：宽度比例 → 字号比例，窗口按文字度量重算（不碰 base 640×480）
                w0 = max(1, g.width())
                st0 = getattr(self, "_start_scale", self.scale) or self.scale
                self.scale = max(0.05, min(8.0, st0 * (w1 / float(w0))))
                self.font_px = max(8, int(round(getattr(self, "_base_font", self.font_px) * self.scale)))
                self._resize_to_text()
                if self.anchor > 0:
                    self.apply_anchor()
                self._drag_moved = True
                self.update()
                ev.accept()
                return
            if self.base.width() > 0:
                if self.keep_ratio:
                    h1 = int(round(w1 * self.base.height() / float(self.base.width())))
                else:
                    h1 = max(MIN_H, h1)
                self.scale = w1 / float(self.base.width())
            else:
                h1 = max(MIN_H, h1)
            self.resize(max(MIN_W, w1), h1)
            if self.anchor > 0:
                self.apply_anchor()
            self._drag_moved = True
            self.update()
            ev.accept()
            return
        if self.dragging and (ev.buttons() & Qt.LeftButton):
            g = ev.globalPos() - self.drag_off
            if self.anchor > 0:
                dxr = abs(g.x() - self.x())
                dyr = abs(g.y() - self.y())
                if dxr < 4 and dyr < 4:
                    ev.accept()
                    return
                self.anchor = 0
            if g != self.pos():
                self._drag_moved = True
            self.move(g)
            ev.accept()
            return
        r = self.rect()
        if QRect(r.right() - 14, r.bottom() - 14, 14, 14).contains(p):
            self.setCursor(Qt.SizeFDiagCursor)
        elif QRect(r.left(), r.bottom() - 14, 14, 14).contains(p):
            self.setCursor(Qt.SizeBDiagCursor)
        else:
            self.setCursor(Qt.SizeAllCursor)
        ev.accept()

    def mouseReleaseEvent(self, ev):
        if getattr(self, "_annot", False) or getattr(self, "_cur_stroke", None) is not None:
            st = getattr(self, "_cur_stroke", None)
            self._cur_stroke = None
            if st is not None and len(st.get("pts", [])) >= 2:
                self._strokes.append(st)
            self._pressed = False
            self.dragging = False
            self.resizing = False
            self._drag_moved = True     # 抑制"单击切换播放"
            try:
                self.update()
            except Exception:
                pass
            ev.accept()
            return
        was_drag = self.dragging
        was_res = self.resizing
        quick = (self._pressed and not was_res and not self._drag_moved and
                 (ev.globalPos() - self._press_pos).manhattanLength() < 4 and
                 self._press_btn == Qt.LeftButton)
        self.dragging = False
        self.resizing = False
        self._pressed = False
        if was_drag and ev.button() == Qt.LeftButton:
            self.auto_snap(self._drag_moved)
        if was_res:
            show_msg(self, D("大小：%d%%") % self.pct())
        if quick and not self.click_through:
            self.toggle_play()
        ev.accept()

    def wheelEvent(self, ev):
        if self.click_through:
            return
        d = ev.angleDelta().y()
        if d == 0:
            return
        self.step_pct(10 if d > 0 else -10)
        ev.accept()

    def enterEvent(self, ev):
        self.update()
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self.update()
        super().leaveEvent(ev)

    def showEvent(self, ev):
        try:
            self.setWindowOpacity(self.current_opacity())
        except Exception:
            pass
        force_topmost(self)
        super().showEvent(ev)

    def resizeEvent(self, ev):
        try:
            if self.video is not None:
                self.video.setGeometry(self.rect())
        except Exception:
            pass
        super().resizeEvent(ev)

    def closeEvent(self, ev):
        # 关窗必须停掉解码线程/音频 sink，否则线程泄漏空转
        try:
            self._teardown_av()
            kf = getattr(self, "kfc", None)
            if kf is not None:
                kf.stop()
            if self.player is not None:
                self.player.stop()
                self.player.setMedia(QMediaContent())
            if self.movie is not None:
                self.movie.stop()
        except Exception:
            pass
        super().closeEvent(ev)

    # ---------- 绘制 ----------

    def paintEvent(self, ev):
        if self.is_video and not self.using_av:
            # Qt 后备：视频由 QVideoWidget 子控件绘制（它盖满窗口，下面不用画）
            return
        p = QPainter(self)
        r = self.rect()
        hover = r.contains(self.mapFromGlobal(QCursor.pos()))
        show_pix = None
        show_img = None
        if self.is_video:
            text = self.video_name or D("视频")
            if self.av_pix is not None and not self.av_pix.isNull():
                show_img = self.av_pix
        elif self.kind in ("image", "gif", "shot"):
            if self.kind == "shot":
                text = D("临时截图")
            else:
                text = self._image_name or D("图片")
            if self.movie is not None:
                pm = self.movie.currentPixmap()
                if not pm.isNull():
                    show_pix = pm
            elif self._pix is not None and not self._pix.isNull():
                show_pix = self._pix
        else:
            text = "屏幕贴图"
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        if show_img is not None:
            _paint_img(p, r, self, show_img)
        elif show_pix is not None:
            _paint_pix(p, r, self)
        else:
            p.fillRect(r, PLACE_BG)
        if getattr(self, "_strokes", None):
            _draw_strokes(p, self, self._strokes)
        if getattr(self, "_cur_stroke", None):
            _draw_strokes(p, self, [self._cur_stroke])
        label = text
        if self.kind == "shot":
            try:
                i = _shots.index(self)
                label = "%s  %d/%d" % (text, i + 1, len(_shots))
            except ValueError:
                pass
        if self.anchor > 0:
            label += " · " + anchor_short(self.anchor)
        if hover:
            p.fillRect(r, QColor(0, 0, 0, 90))  # 悬停暗条（半透明黑，非渐变）
            p.setPen(PLACE_FG)
            f = QFont()
            f.setPixelSize(max(12, min(20, r.height() // 8)))
            p.setFont(f)
            p.drawText(r, Qt.AlignCenter, label)
        p.end()

    # ---------- 置顶断言 ----------

    def force_topmost_native(self):
        try:
            if not int(self.windowFlags() & Qt.WindowStaysOnTopHint):
                return
            hwnd = int(self.winId())
            u32 = ctypes.windll.user32
            style = u32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
            if not (style & 0x00000008):           # WS_EX_TOPMOST
                # NOSIZE|NOMOVE|NOACTIVATE + HWND_TOPMOST(-1)
                u32.SetWindowPos(hwnd, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0008)
        except Exception:
            pass


def force_topmost(w):
    try:
        w.force_topmost_native()
    except Exception:
        pass


def apply_topmost_force_all():
    for o in list(overlays):
        force_topmost(o)


# ================= 点击穿透 =================

def set_click_through(w, on):
    try:
        on = bool(on)
        w.click_through = on
        w.a_clickthru.setChecked(on)
        u32 = ctypes.windll.user32
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        # 父窗 + 所有子控件一起设（否则 QVideoWidget 等子控件会拦下点击，穿透失效）
        targets = [w]
        try:
            targets.extend([c for c in w.findChildren(QWidget) if isinstance(c, QWidget)])
        except Exception:
            pass
        for t in targets:
            try:
                hwnd = int(t.winId())
            except Exception:
                continue
            style = u32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_LAYERED
            if on:
                style |= WS_EX_TRANSPARENT
            else:
                style &= ~WS_EX_TRANSPARENT
            u32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        try:
            # NOSIZE|NOMOVE|NOZORDER|NOACTIVATE|FRAMECHANGED = 0x1|0x2|0x4|0x8|0x20
            u32.SetWindowPos(int(w.winId()), None, 0, 0, 0, 0,
                             0x0001 | 0x0002 | 0x0004 | 0x0008 | 0x0020)
        except Exception:
            pass
        w.update()
        show_msg(w, D("点击穿透：") + D("开" if on else "关"))
    except Exception:
        pass


# ================= 热键（轮询 GetAsyncKeyState，全局生效且不吞键） ==========
# "可设定" 热键：HK={"pass","shot"} 串 → parse_hk → (ctrl,alt,shift,meta,vk)

_QT_VK_TABLE = [None]   # 延迟构建（Qt.Key → Windows VK）


def _build_qt_vk_table():
    from PyQt5.QtCore import Qt as _Q
    t = {}
    for i in range(26):
        v = getattr(_Q, "Key_%s" % chr(65 + i), None)      # Qt.Key_A..Z = 0x41..0x5A
        if v:
            t[int(v)] = 0x41 + i
    for i in range(10):
        v = getattr(_Q, "Key_%d" % i, None)
        if v:
            t[int(v)] = 0x30 + i
    for i in range(1, 25):
        v = getattr(_Q, "Key_F%d" % i, None)               # F1..F24
        if v:
            t[int(v)] = 0x70 + i - 1
    pairs = [
        ("Key_Home", 0x24), ("Key_End", 0x23), ("Key_PageUp", 0x21),
        ("Key_PageDown", 0x22), ("Key_Left", 0x25), ("Key_Up", 0x26),
        ("Key_Right", 0x27), ("Key_Down", 0x28), ("Key_Insert", 0x2D),
        ("Key_Delete", 0x2E), ("Key_Tab", 0x09), ("Key_Backspace", 0x08),
        ("Key_Return", 0x0D), ("Key_Enter", 0x0D), ("Key_Escape", 0x1B),
        ("Key_Space", 0x20), ("Key_Pause", 0x13), ("Key_Print", 0x2C),
        ("Key_ScrollLock", 0x91), ("Key_NumLock", 0x90), ("Key_CapsLock", 0x14),
        ("Key_Comma", 0xBC), ("Key_Period", 0xBE), ("Key_Slash", 0xBF),
        ("Key_Semicolon", 0xBA), ("Key_Apostrophe", 0xDE),
        ("Key_BracketLeft", 0xDB), ("Key_BracketRight", 0xDD),
        ("Key_Minus", 0xBD), ("Key_Equal", 0xBB), ("Key_QuoteLeft", 0xC0),
        ("Key_Backslash", 0xDC), ("Key_Asterisk", 0x6A), ("Key_QuoteDbl", 0xDE),
    ]
    for n, vk in pairs:
        v = getattr(_Q, n, None)
        if v:
            t[int(v)] = vk
    return t


def parse_hk(s):
    """'Ctrl+Alt+S' -> (ctrl,alt,shift,meta,vk)；无修饰键/解析失败 -> None。"""
    s = (s or "").strip()
    if not s:
        return None
    ls = s.lower()
    ctrl = ("ctrl" in ls) or ("control" in ls)
    alt = "alt" in ls
    shift = "shift" in ls
    meta = ("win" in ls) or ("meta" in ls) or ("cmd" in ls)
    if not (ctrl or alt or shift or meta):
        return None          # 全局热键必须带修饰键，避免吞掉普通输入
    if _QT_VK_TABLE[0] is None:
        _QT_VK_TABLE[0] = _build_qt_vk_table()
    base = s.rsplit("+", 1)[-1].strip() if "+" in s else s
    try:
        from PyQt5.QtGui import QKeySequence as _KS
        ks = _KS(s)
        if len(ks) > 0:
            k = int(ks[0]) & 0x01FFFFFF      # 去掉 Qt 修饰位留裸键码
            vk = _QT_VK_TABLE[0].get(k)
            if vk is None and (0x41 <= k <= 0x5A or 0x30 <= k <= 0x39):
                vk = k
            if vk is not None:
                return (ctrl, alt, shift, meta, vk)
    except Exception:
        pass
    b = base.upper()
    if len(b) == 1 and ("A" <= b <= "Z" or "0" <= b <= "9"):
        return (ctrl, alt, shift, meta, ord(b))
    if len(b) >= 2 and b[0] == "F" and b[1:].isdigit() and 1 <= int(b[1:]) <= 24:
        return (ctrl, alt, shift, meta, 0x70 + int(b[1:]) - 1)
    if base in _VK_PUNCT:
        return (ctrl, alt, shift, meta, _VK_PUNCT[base])
    named = {"HOME": 0x24, "END": 0x23, "PGUP": 0x21, "PGDN": 0x22, "LEFT": 0x25,
             "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28, "SPACE": 0x20, "TAB": 0x09,
             "INS": 0x2D, "DEL": 0x2E, "ESC": 0x1B}
    if b in named:
        return (ctrl, alt, shift, meta, named[b])
    return None


def _hk_state(spec):
    """spec=(ctrl,alt,shift,meta,vk)：指定修饰键全按下 + 主键按下才算。"""
    if not spec:
        return False
    ctrl, alt, shift, meta, vk = spec
    u32 = ctypes.windll.user32

    def dn(v):
        return bool(u32.GetAsyncKeyState(v) & 0x8000)

    if ctrl and not dn(0x11):     # VK_CONTROL
        return False
    if alt and not dn(0x12):       # VK_MENU
        return False
    if shift and not dn(0x10):     # VK_SHIFT
        return False
    if meta and not dn(0x5B):      # VK_LWIN
        return False
    return dn(vk)


def _hk_toggle_pass():
    for o in list(overlays):
        if not o.click_through:
            set_click_through(o, True)
            return
    if overlays:
        set_click_through(overlays[0], False)


def _hk_shot():
    fn = globals().get("toggle_shot")     # 后续批次定义，call 时取
    if callable(fn):
        fn()


def _hk_panel():
    fn = globals().get("toggle_mp")
    if callable(fn):
        fn()


def _hk_save():
    fn = globals().get("save_shot_async")
    if callable(fn):
        fn()


def _hk_switch():
    fn = globals().get("shot_next")
    if callable(fn):
        fn()


def _hk_del():
    fn = globals().get("shot_delete")
    if callable(fn):
        fn()


def _hk_delall():
    fn = globals().get("shot_delete_all")
    if callable(fn):
        fn()


def _hk_color():
    fn = globals().get("pick_color_under_cursor")
    if callable(fn):
        fn()


def _hk_region():
    fn = globals().get("start_region_shot")
    if callable(fn):
        fn()


_HK_FN = {"pass": _hk_toggle_pass, "shot": _hk_shot, "panel": _hk_panel,
          "save": _hk_save, "switch": _hk_switch, "del": _hk_del,
          "delall": _hk_delall, "color": _hk_color, "region": _hk_region}


def _hotkey_poll():
    try:
        for name in HK_KEYS:              # 7 键轮询；未绑定(None)直接跳过
            spec = HKC.get(name)
            if not spec:
                continue
            down = _hk_state(spec)
            if down and not _hotkey_prev.get(name):
                fn = _HK_FN.get(name)
                if fn:
                    fn()
            _hotkey_prev[name] = bool(down)
    except Exception:
        pass


def ensure_hotkey():
    global _hotkey_timer
    if _hotkey_timer[0] is not None:
        return
    try:
        ctypes.windll.user32.GetAsyncKeyState.restype = ctypes.c_short
    except Exception:
        pass
    t = QTimer(app)
    t.timeout.connect(_hotkey_poll)
    t.start(100)
    _hotkey_timer[0] = t


# ================= 多实例 IPC =================

def init_server():
    try:
        QLocalServer.removeServer(IPC_NAME)
    except Exception:
        pass
    srv = QLocalServer()
    try:
        srv.listen(IPC_NAME)
    except Exception:
        return None
    return srv


def _read_sock(sock):
    chunks = []
    try:
        while not sock.atEnd():
            b = sock.read(65536)
            if not b:
                break
            chunks.append(bytes(b))
    except Exception:
        pass
    return b"".join(chunks)


def _handle_conn(sock):
    if sock is None:
        return
    try:
        data = b""
        if sock.bytesAvailable() <= 0 and not sock.waitForReadyRead(3000):
            return
        data = _read_sock(sock)
        if not data and sock.waitForReadyRead(3000):
            data = _read_sock(sock)
    except Exception:
        return
    try:
        obj = json.loads(data.decode("utf-8", "replace"))
    except Exception:
        return
    if obj.get("cmd") == "open":
        for f in list_files(obj.get("files", [])):
            open_overlay(f)
        # 收到文件后保持运行，不退出
    elif obj.get("cmd") == "showpanel":
        # 第二实例没带文件 → 唤起小面板（后台托盘可见），不再弹窗
        _dbg("ipc showpanel")
        QTimer.singleShot(0, lambda: (toggle_mp() if callable(globals().get("toggle_mp")) else None))


def init_client():
    sock = QLocalSocket()
    sock.connectToServer(IPC_NAME, QLocalSocket.ReadWrite)  # 必须 ReadWrite：只读模式 write 会静默失败
    ok = sock.waitForConnected(1200)
    if not ok:
        try:
            sock.abort()
        except Exception:
            pass
        return None, False
    return sock, True


def send_files(sock, paths):
    return send_raw(sock, {"cmd": "open", "files": list(paths)})


def send_raw_cmd(sock, cmd):
    return send_raw(sock, {"cmd": cmd})


def send_raw(sock, obj):
    try:
        payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        sock.write(payload)
        sock.flush()
        sock.waitForBytesWritten(1500)
        return True
    except Exception:
        return False


# ================= 管理 =================

def open_overlay(path):
    o = OverlayWindow()
    overlays.append(o)
    o.resize(o.base.width(), o.base.height())
    try:
        g = screen_rect_for(o)
        idx = len(overlays)
        o.move(g.left() + 40 + (idx * 28) % 400,
               g.top() + 40 + (idx * 28) % 400)
    except Exception:
        pass
    o.show()
    o.load(path)
    ensure_hotkey()
    force_topmost(o)
    try:
        _mp_refresh()
    except Exception:
        pass
    return o


def close_overlay(o):
    """关掉一个贴图。关窗≠退出程序——后台（托盘+热键+小面板）一直活着。"""
    try:
        o.close()
    except Exception:
        pass
    if o in overlays:
        try:
            overlays.remove(o)
        except Exception:
            pass
    try:
        _mp_refresh()
    except Exception:
        pass


def quit_app():
    _exiting[0] = True
    save_config()
    if app is not None:
        app.quit()


# ================= 主题 / 初始化 / 更新 / 官网 =================

def theme(idx=None):
    """当前主题色板 dict。"""
    i = SETTINGS.get("theme", 0) if idx is None else int(idx)
    return THEMES[i][1]


def theme_name(idx=None):
    i = SETTINGS.get("theme", 0) if idx is None else int(idx)
    return THEMES[i][0]


def apply_theme(idx=None):
    """应用主题到整个 QApplication（中性灰成组配色，无渐变无发光）。"""
    if idx is not None:
        SETTINGS["theme"] = max(0, min(len(THEMES) - 1, int(idx)))
    c = theme()
    try:
        if app is None:
            return
        app.setStyleSheet(
            "QDialog, QWidget{background:%(bg)s; color:%(text)s;}"
            "QLabel{background:transparent; color:%(text)s;}"
            "QPushButton{background:%(btn)s; color:%(text)s; border:1px solid %(line)s;"
            " border-radius:4px; padding:5px 14px;}"
            "QPushButton:hover{background:%(btnh)s;}"
            "QPushButton:pressed{background:%(line)s;}"
            "QComboBox, QLineEdit, QSpinBox, QTextEdit{background:%(card)s;"
            " color:%(text)s; border:1px solid %(line)s; border-radius:4px; padding:3px 6px;}"
            "QComboBox QAbstractItemView{background:%(card)s; color:%(text)s;}"
            " QMenu{background:%(card)s; color:%(text)s; border:1px solid %(line)s;}"
            "QMenu::item:selected{background:%(btnh)s;}"
            "QMenu::item:disabled{color:%(dim)s;}"
            "QMenu::separator{background:%(line)s; height:1px;}"
            "QToolTip{background:%(card)s; color:%(text)s; border:1px solid %(line)s;}"
            "QCheckBox{background:transparent; color:%(text)s;}"
            "QCheckBox:disabled{color:%(dim)s;}"
            "QScrollBar:vertical{background:%(bg)s; width:10px;}"
            "QScrollBar::handle:vertical{background:%(line)s; border-radius:4px; min-height:24px;}"
            "QScrollBar:horizontal{background:%(bg)s; height:10px;}"
            "QScrollBar::handle:horizontal{background:%(line)s; border-radius:4px; min-width:24px;}"
            "QTabBar::tab{background:%(card)s; color:%(text)s; padding:6px 12px;"
            " border:1px solid %(line)s; border-bottom:none;}"
            "QTabBar::tab:selected{background:%(btnh)s;}"
            % c)
    except Exception:
        pass
    try:
        _mp_refresh()      # 小面板跟着换色（可见才重建）
    except Exception:
        pass


def reset_settings():
    """一键初始化：贴图全关、热键/主题/语言/截图设置回出厂、配置文件写空。"""
    for w in list(overlays):
        try:
            w.hide()
            w.deleteLater()
        except Exception:
            pass
    overlays.clear()
    shot_delete_all()
    HK.clear()
    HK.update(HK_DEF)
    for k in HK_KEYS:
        HKC[k] = parse_hk(HK.get(k, "")) or None
        _hotkey_prev[k] = False
    LANG["code"] = "zh"
    SHOT_CFG.update(SHOT_DEF)
    SETTINGS.update({"theme": 0, "restore": 0, "autoupdate": 1})
    apply_theme(0)
    try:
        for wdg in QApplication.topLevelWidgets():
            if isinstance(wdg, DropPanel):
                wdg.refresh_texts()
        if tray is not None:
            tray.setContextMenu(build_tray_menu())
            tray.setToolTip(D(APP_NAME) + " " + VERSION)
    except Exception:
        pass
    save_config()          # overlays 已清 → 配置写成空清单


def open_site():
    try:
        QDesktopServices.openUrl(QUrl(SITE_URL))
    except Exception:
        if overlays:
            show_msg(overlays[0], D("无法打开官网：%s") % SITE_URL)


def _parse_ver(s):
    out = []
    for p in str(s or "0").lstrip("vV").split("."):
        n = ""
        for ch in p:
            if ch.isdigit():
                n += ch
            else:
                break
        out.append(int(n or 0))
    while len(out) < 3:      # 补位到 3 段：1.5.0 == 1.5（否则会误判“有新版本”）
        out.append(0)
    return tuple(out[:3])


def check_update(manual=True):
    """查更新：UPDATE_API 没配就只在手动时提示；连不上不吵用户。"""
    if not UPDATE_API:
        if manual:
            QMessageBox.information(None, D("检查更新"),
                                    D("更新地址未配置（开源仓库就绪后填写）。") + "\n" + SITE_URL)
        return
    try:
        import urllib.request
        req = urllib.request.Request(UPDATE_API, headers={"User-Agent": "ScreenPin/" + VERSION})
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        latest = data.get("tag_name") or data.get("name") or ""
        if _parse_ver(latest) > _parse_ver(VERSION):
            mb = QMessageBox.information(None, D("发现新版本 %s" % latest),
                                         D("当前版本 %s，去官网下载最新版？" % VERSION),
                                         QMessageBox.Open | QMessageBox.Close)
            if mb == QMessageBox.Open:
                open_site()
        elif manual:
            QMessageBox.information(None, D("检查更新"),
                                    D("已是最新版本 %s。" % VERSION))
    except Exception:
        if manual:
            QMessageBox.warning(None, D("检查更新"),
                                D("检查更新失败（网络不通？）\n") + SITE_URL)


def _update_tick():
    try:
        if SETTINGS.get("autoupdate"):
            check_update(manual=False)
    except Exception:
        pass


def media_filter():
    pat = ("*.png *.jpg *.jpeg *.bmp *.webp *.gif *.tif *.tiff *.ico *.svg "
           "*.pbm *.pgm *.ppm *.xbm *.xpm *.mp4 *.mkv *.webm *.avi *.mov *.wmv *.m4v "
           "*.mpg *.mpeg *.ts *.flv *.3gp")
    return "%s (%s);;%s;;%s;;%s" % (D("媒体文件"), pat, D("图片"), D("视频"),
                                    D("所有文件 (*.*)"))


# ================= 拖放启动面板 =================

class DropPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def refresh_texts(self):
        """语言切换后整体刷新（main 里把控件挂到 panel.*_w 上）。"""
        pairs = (("hint_w", "把图片或视频拖到本窗口，\n或点下面的按钮选择。"),
                 ("btn_w", "选择图片/视频…"), ("set_w", "设置"), ("quit_w", "退出"))
        for attr, key in pairs:
            w = getattr(self, attr, None)
            if w is not None:
                w.setText(D(key))

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        try:
            # 多文件 / 整个文件夹一次全开（list_files 展开目录）
            paths = [u.toLocalFile() for u in ev.mimeData().urls()]
            for p in list_files(paths):
                open_overlay(p)
        except Exception:
            pass
        ev.acceptProposedAction()


def edit_text_overlay(w, parent=None):
    """文字编辑对话框：多行文本 + 符号面板(点击插入) + 字号/粗体/底色/取色。"""
    dlg = QDialog(parent or w)
    dlg.setWindowTitle(D("编辑文字/样式…"))
    lay = QVBoxLayout(dlg)
    ed = QTextEdit()
    ed.setPlainText(w.text)
    ed.setAcceptRichText(False)
    lay.addWidget(ed, 1)
    from PyQt5.QtWidgets import QTabWidget
    tabs = QTabWidget()
    for gname, chars in SYMBOL_GROUPS:
        box = QWidget()
        g = QGridLayout(box)
        g.setSpacing(2)
        for i, ch in enumerate(chars):
            b = QPushButton(ch)
            b.setFixedWidth(30)
            b.clicked.connect(lambda _c=False, c=ch, e=ed: e.insertPlainText(c))
            g.addWidget(b, i // 10, i % 10)
        tabs.addTab(box, D(gname))
    lay.addWidget(tabs)
    r1 = QHBoxLayout()
    r1.addWidget(QLabel(D("字号")))
    sp = QSpinBox()
    sp.setRange(8, 400)
    sp.setValue(int(getattr(w, "_base_font", w.font_px)))
    r1.addWidget(sp)
    chk_b = QCheckBox(D("粗体"))
    chk_b.setChecked(bool(w.bold))
    chk_bg = QCheckBox(D("底色"))
    chk_bg.setChecked(bool(w.bg_on))
    r1.addWidget(chk_b)
    r1.addWidget(chk_bg)
    lay.addLayout(r1)
    r2 = QHBoxLayout()
    r2.addWidget(QLabel(D("文字颜色")))
    cbtn = QPushButton()
    state = {"fg": QColor(w.text_color), "bg": QColor(w.bg_color)}

    def paint_btn(btn, key):
        btn.setStyleSheet("background:%s; height:24px; border:1px solid #888;" %
                          state[key].name())
    paint_btn(cbtn, "fg")

    def pick_fg():
        c = QColorDialog.getColor(state["fg"], dlg, D("文字颜色"))
        if c.isValid():
            state["fg"] = c
            paint_btn(cbtn, "fg")
    cbtn.clicked.connect(pick_fg)
    r2.addWidget(cbtn, 1)
    r2.addWidget(QLabel(D("背景颜色")))
    cbtn2 = QPushButton()
    paint_btn(cbtn2, "bg")

    def pick_bg():
        c = QColorDialog.getColor(state["bg"], dlg, D("背景颜色"))
        if c.isValid():
            state["bg"] = c
            paint_btn(cbtn2, "bg")
    cbtn2.clicked.connect(pick_bg)
    r2.addWidget(cbtn2, 1)
    lay.addLayout(r2)
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    lay.addWidget(bb)
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    if dlg.exec_() != QDialog.Accepted:
        return
    w.text = ed.toPlainText()
    w._base_font = int(sp.value())
    w.font_px = max(8, int(round(w._base_font * w.scale)))
    w.bold = bool(chk_b.isChecked())
    w.bg_on = bool(chk_bg.isChecked())
    w.text_color = QColor(state["fg"])
    w.bg_color = QColor(state["bg"])
    w._resize_to_text()


# ================= 关键帧（位置动画：给贴图打点，按时间轴平移） =============

class KeyframeCtrl(QObject):
    """位置关键帧。kfs=[[t,x,y],...]，start 后 30fps 插值 move 窗口。"""
    def __init__(self, w):
        super().__init__(w)
        self.w = w
        self.kfs = []
        self.loop = True
        self.playing = False
        self._t0 = 0.0
        self._dur = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._tick)

    def add(self, x=None, y=None):
        if x is None:
            x = self.w.x()
        if y is None:
            y = self.w.y()
        t = self.kfs[-1][0] + 2.0 if self.kfs else 0.0
        self.kfs.append([t, int(x), int(y)])
        self.w.anchor = 0
        return len(self.kfs)

    def remove(self, idx):
        if 0 <= idx < len(self.kfs):
            del self.kfs[idx]

    def clear(self):
        self.stop()
        self.kfs = []

    def total(self):
        return self.kfs[-1][0] if self.kfs else 0.0

    def start(self):
        if not self.kfs:
            show_msg(self.w, D("没设关键帧"))
            return
        if len(self.kfs) == 1:
            _t, x, y = self.kfs[0]
            self.w.move(int(x), int(y))
            show_msg(self.w, D("已到关键帧"))
            return
        self._dur = self.total()
        if self._dur <= 0:
            show_msg(self.w, D("没设关键帧"))
            return
        self.playing = True
        self._t0 = time.time()
        self._timer.start()
        show_msg(self.w, D("动画：播放中"))

    def stop(self):
        was = self.playing
        self._timer.stop()
        self.playing = False
        if was:
            show_msg(self.w, D("动画：已停止"))

    def _tick(self):
        if not self.playing or len(self.kfs) < 2 or self._dur <= 0:
            return
        el = time.time() - self._t0
        if el >= self._dur:
            if self.loop:
                self._t0 = time.time()
                el = 0.0
            else:
                _t, x, y = self.kfs[-1]
                self.w.move(int(x), int(y))
                self.stop()
                return
        k = self.kfs
        i = 0
        while i < len(k) - 1 and k[i + 1][0] < el:
            i += 1
        if i >= len(k) - 1:
            _t, x, y = k[-1]
        else:
            t0i, x0, y0 = k[i]
            t1i, x1, y1 = k[i + 1]
            span = t1i - t0i
            f = 0.0 if span <= 0 else max(0.0, min(1.0, (el - t0i) / span))
            x = int(round(x0 + (x1 - x0) * f))
            y = int(round(y0 + (y1 - y0) * f))
        self.w.move(int(x), int(y))
        self.w.update()


# ================= 文字/符号贴图 =================

class TextOverlay(OverlayWindow):
    """文字贴图：双击改内容与样式，可插入排版符号；随大小按钮缩放字号。"""
    def __init__(self):
        super().__init__()
        self.kind = "text"
        self.source_path = ""
        self.text = TXT_DEF["text"]
        self.font_px = int(TXT_DEF["font_px"])
        self.text_color = QColor(TXT_DEF["color"])
        self.bold = bool(TXT_DEF["bold"])
        self.bg_on = bool(TXT_DEF["bg"])
        self.bg_color = QColor(TXT_DEF["bgcolor"])
        self._tmp_pix = None
        self._tmp_movie = None
        self._base_font = int(TXT_DEF["font_px"])   # 100% 时的设计字号（持久化用它）
        self._resize_to_text()

    # —— 缩放 = 字号缩放（贴大小按钮/滚轮/菜单百分比的统一入口） ——

    def set_pct(self, v, announce=True):
        v = max(5, min(800, int(v)))
        self.scale = v / 100.0
        self.font_px = max(8, int(round(self._base_font * self.scale)))
        self._resize_to_text()
        if announce:
            show_msg(self, D("大小：%d%%") % self.pct())

    def resizeEvent(self, ev):
        # 用户拖角改窗口后：字号跟随（不回弹窗口，只同步字号并重绘）
        try:
            if self.kind == "text" and self._base_font:
                want = max(8, int(round(self._base_font * self.scale)))
                if want != self.font_px:
                    self.font_px = want
        except Exception:
            pass
        super().resizeEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        if self.kind == "text" and ev.button() == Qt.LeftButton and not self.click_through:
            self.edit_text()
            ev.accept()
            return
        super().mouseDoubleClickEvent(ev)

    def fit_screen(self, frac=0.9):
        """文字贴图：按窗口当前宽度等比缩放到屏幕 frac（字号随 scale 走，不碰 base）。"""
        try:
            cur = max(1, self.width())
            target = int(screen_rect_for(self).width() * frac)
            self.set_pct(max(5, min(800, int(round(self.pct() * target / float(cur))))))
            show_msg(self, D("已适配屏幕"))
        except Exception:
            pass

    def edit_text(self):
        edit_text_overlay(self)

    def copy_text(self):
        try:
            QApplication.clipboard().setText(self.text or "")
            show_msg(self, D("已复制文本"))
        except Exception:
            pass

    def build_menu(self):
        """文字贴图专用菜单：编辑/符号 + 大小(字号) + 位置 + 透明度 + 关键帧 + 通用尾部。"""
        m = QMenu(self)
        act(m, D("编辑文字/样式…（含符号面板）"), self.edit_text)
        act(m, D("复制文本"), self.copy_text)
        m.addSeparator()
        _menu_size(self, m)
        _menu_anchor(self, m)
        _menu_opacity(self, m)
        _menu_kf(self, m)
        _menu_tail(self, m)
        return m

    def _metrics(self):
        f = QFont()
        f.setPixelSize(max(8, int(self.font_px)))
        f.setBold(bool(self.bold))
        return f

    def _resize_to_text(self):
        try:
            fm = QFontMetricsF(self._metrics())
            src = self.text or " "
            rect = fm.boundingRect(QRect(0, 0, 3600, 4000),
                                   int(Qt.AlignLeft) | int(Qt.TextWordWrap), src)
            self.resize(max(MIN_W, int(rect.width()) + 44),
                        max(MIN_H, int(rect.height()) + 26))
            self.apply_anchor()
            self.update()
        except Exception:
            pass

    def paintEvent(self, ev):
        if self.kind != "text":
            super().paintEvent(ev)
            return
        p = QPainter(self)
        r = self.rect()
        if self.bg_on:
            c = QColor(self.bg_color)
            c.setAlpha(160)
            p.fillRect(r, c)
        p.setPen(QColor(self.text_color))
        p.setFont(self._metrics())
        p.drawText(r, int(Qt.AlignCenter) | int(Qt.TextWordWrap), self.text or "")
        p.end()


# ================= 临时截图（只存内存） =================

def capture_screen():
    """抓整屏（多屏按虚拟桌面拼接）。返回 QImage；不写盘。
    抓不到（offscreen 平台/0x0）返回 None，调用方按失败处理。"""
    try:
        from PyQt5.QtGui import QGuiApplication as G
        gs = G.screens()
        if not gs:
            return None
        if len(gs) == 1:
            im = gs[0].grabWindow(0).toImage()
        else:
            vg = G.primaryScreen().virtualGeometry()
            im = QImage(vg.width(), vg.height(), QImage.Format_ARGB32)
            im.fill(Qt.transparent)
            p = QPainter(im)
            for s in gs:
                rg = s.geometry()
                one = s.grabWindow(0).toImage()
                if not one.isNull():
                    p.drawImage(rg.x() - vg.x(), rg.y() - vg.y(), one)
            p.end()
        if im is None or im.isNull() or im.width() < 2 or im.height() < 2:
            return None
        # 抓鼠标指针（开关 SHOT_CFG["cursor"]；QCursor.pixmap()=Qt5.14+，抓当前真实指针）
        if int(SHOT_CFG.get("cursor", 1)):
            try:
                from PyQt5.QtGui import QCursor
                pos = QCursor.pos()
                if len(gs) == 1:
                    off = gs[0].geometry().topLeft()
                else:
                    off = vg.topLeft()
                ox, oy = pos.x() - off.x(), pos.y() - off.y()
                if 0 <= ox < im.width() and 0 <= oy < im.height():
                    cur = QCursor().pixmap()
                    if cur is not None and not cur.isNull():
                        p2 = QPainter(im)
                        p2.setRenderHint(QPainter.SmoothPixmapTransform)
                        p2.drawPixmap(ox, oy, cur)
                        p2.end()
            except Exception:
                pass    # 指针抓失败不影响截图本身
        return im
    except Exception:
        return None


class ShotOverlay(OverlayWindow):
    """临时截图贴图：帧在内存（_pix），source_path 恒空 → 不进配置、不落盘。"""
    def __init__(self, img):
        super().__init__()
        self.kind = "shot"
        self.source_path = ""
        self._pix = QPixmap.fromImage(img)
        self._image_name = D("临时截图")
        self._size_done = True
        try:
            import time as _t
            self._stamp = _t.strftime("%Y%m%d_%H%M%S")
        except Exception:
            self._stamp = "shot"
        if not self._pix.isNull():
            self.base = QSize(self._pix.size())
            self.resize(self.base.width(), self.base.height())

    def build_menu(self):
        m = QMenu(self)
        act(m, D("保存临时图片…"), lambda: save_shot_async(self))
        act(m, D("下一张临时图片"), shot_next)
        act(m, D("删除这张临时图片"), lambda: shot_delete(self))
        act(m, D("删除全部临时图片"), shot_delete_all)
        _annot_menu(self, m)
        _menu_tf(self, m)
        m.addSeparator()
        _menu_open(self, m)
        m.addSeparator()
        _menu_size(self, m)
        _menu_anchor(self, m)
        _menu_opacity(self, m)
        _menu_kf(self, m)
        _menu_tail(self, m)
        return m


def set_shot_visible(w):
    """显示 w（活动窗），其余槽位窗全部 hide。维护 _shot[0]。"""
    _shot[0] = w
    for s in list(_shots):
        try:
            if s is w:
                s.show()
            else:
                s.hide()
        except Exception:
            pass


def _apply_shot_style(w):
    """按设置摆位置/宽度%/透明度并置顶。"""
    try:
        scr = screen_rect_for(w)
        tw = int(scr.width() * SHOT_CFG.get("pct", 33) / 100.0)
        if w.base.width() > 0 and tw > 0:
            w.scale = max(0.05, tw / float(w.base.width()))
            w._apply_size()
    except Exception:
        pass
    w.set_anchor(int(SHOT_CFG.get("anchor", 3)))
    w.set_opacity(int(SHOT_CFG.get("opacity", 100)))
    ensure_hotkey()
    force_topmost(w)
    try:
        _mp_refresh()
    except Exception:
        pass


def _append_slot(w):
    _shots.append(w)
    while len(_shots) > SHOT_SLOTS:        # 槽满：释放最早一张（真正释放内存）
        old = _shots.pop(0)
        try:
            old.hide()
            old.deleteLater()
        except Exception:
            pass


# ================= v1.9：取色 / 框选截图 / 旋转镜像 / 标注 =================

_tip_float = [None]


def _float_tip(text, ms=2000):
    """屏幕中央短提示（无锚点操作用；text 须已过 D()）。"""
    try:
        old = _tip_float[0]
        _tip_float[0] = None
        if old is not None:
            try:
                old.close()
            except Exception:
                pass
        lab = QLabel(text)
        lab.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        pal = lab.palette()
        pal.setColor(lab.backgroundRole(), QColor(32, 32, 34, 240))
        pal.setColor(lab.foregroundRole(), QColor(235, 235, 235, 255))
        lab.setPalette(pal)
        lab.setAutoFillBackground(True)
        f = QFont()
        f.setPointSize(11)
        lab.setFont(f)
        lab.adjustSize()
        try:
            scr = QApplication.primaryScreen().availableGeometry()
            lab.move(scr.center().x() - lab.width() // 2, scr.center().y() - lab.height() // 2)
        except Exception:
            pass
        lab.show()
        _tip_float[0] = lab

        def _kill(box=_tip_float, l=lab):
            if box[0] is l:
                box[0] = None
            try:
                l.close()
            except Exception:
                pass
        QTimer.singleShot(ms, _kill)
    except Exception:
        pass


def pick_color_under_cursor():
    """取鼠标指针下像素颜色 → 复制 #RRGGBB 到剪贴板 + 浮条提示（无贴图也能用）。"""
    try:
        from PyQt5.QtGui import QCursor, QGuiApplication as G
        pos = QCursor.pos()
        for sc in G.screens():
            g = sc.geometry()
            if not g.contains(pos):
                continue
            im = sc.grabWindow(0).toImage()
            if im is None or im.isNull():
                break
            p = pos - g.topLeft()
            if 0 <= p.x() < im.width() and 0 <= p.y() < im.height():
                c = im.pixelColor(p)
                hx = "#%02X%02X%02X" % (c.red(), c.green(), c.blue())
                QApplication.clipboard().setText(hx)
                _float_tip(D("取到颜色 %s（已复制）") % hx)
                return
        _float_tip(D("取色失败"))
    except Exception:
        _float_tip(D("取色失败"))


_region_box = [None]   # 当前框选会话


def start_region_shot():
    """全屏先截一张 → 铺快照遮罩 → 鼠标拖框 → 本地裁剪入临时截图槽。Esc/右键取消。"""
    if _region_box[0] is not None:
        try:
            _region_box[0].close()
        except Exception:
            pass
        _region_box[0] = None
    try:
        r = RegionShotBox()
        _region_box[0] = r
        r.show()
        r.raise_()
        r.activateWindow()
    except Exception:
        _region_box[0] = None
        _float_tip(D("截图失败"))


class RegionShotBox(QWidget):
    """框选截图：整屏置顶快照 + 变暗遮罩 + 拖出高亮选区 + 尺寸提示 + 十字光标。"""

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setCursor(Qt.CrossCursor)
        self._im = capture_screen()          # 先截屏（不含本遮罩自己）
        self._start = None
        self._cur = None
        try:
            from PyQt5.QtGui import QGuiApplication as G
            self.setGeometry(G.primaryScreen().virtualGeometry())
        except Exception:
            self.setGeometry(0, 0, 1920, 1200)

    def paintEvent(self, ev):
        p = QPainter(self)
        if self._im is not None and not self._im.isNull():
            p.drawImage(self.rect(), self._im)
        else:
            p.fillRect(self.rect(), QColor(0, 0, 0, 255))
        p.fillRect(self.rect(), QColor(0, 0, 0, 90))   # 整体变暗（半透明黑）
        if self._start is not None and self._cur is not None:
            r = QRect(self._start, self._cur).normalized()
            if self._im is not None and not self._im.isNull():
                p.drawImage(r, self._im, QRect(r.x(), r.y(), r.width(), r.height()))  # 选区显示原亮
            p.setPen(QPen(QColor(47, 85, 150), 2))
            p.drawRect(r.adjusted(0, 0, -1, -1))
            p.setPen(QColor(255, 255, 255))
            tip = "%dx%d" % (r.width(), r.height())
            ty = r.top() - 8 if r.top() >= 24 else r.bottom() + 18
            p.drawText(r.left() + 1, ty, tip)
        p.setPen(QColor(235, 235, 235))
        p.drawText(self.rect().adjusted(0, 0, 0, -12), Qt.AlignHCenter | Qt.AlignBottom,
                   D("拖拽框选区域，松开即截图（Esc 取消）"))
        p.end()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._start = ev.pos()
            self._cur = ev.pos()
            self.update()
        elif ev.button() == Qt.RightButton:
            self.close()

    def mouseMoveEvent(self, ev):
        if self._start is not None:
            self._cur = ev.pos()
            self.update()

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton and self._start is not None:
            r = QRect(self._start, ev.pos()).normalized()
            self._start = None
            self._cur = None
            self.close()
            if r.width() < 4 or r.height() < 4 or self._im is None or self._im.isNull():
                _float_tip(D("截图失败"))
                ev.accept()
                return
            im = self._im.copy(r)
            if im is None or im.isNull():
                _float_tip(D("截图失败"))
                ev.accept()
                return
            w = ShotOverlay(im)
            _append_slot(w)
            set_shot_visible(w)
            _apply_shot_style(w)
            show_msg(w, D("截图已显示") + " (%d/%d)" % (_shots.index(w) + 1, len(_shots)))
            try:
                _mp_refresh()
            except Exception:
                pass
        ev.accept()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self.close()
        ev.accept()

    def closeEvent(self, ev):
        if _region_box[0] is self:
            _region_box[0] = None
        ev.accept()


# ---- 旋转 / 镜像：单一实现，paintEvent 与测试共用 ----

def _draw_tf(p, r, pix=None, img=None, tf=0, rot=0):
    """镜像(tf bit0=左右 bit1=上下) + 旋转(rot 个 90°)：预变换整数坐标，DrawAt 铺满 r。
    不用 QPainter 矩阵（offscreen 下矩阵+负宽高负坐标易失真），QImage.mirrored/transformed
    是纯整数几何，四种组合实测方向全对。pix/img 可只给一个，pix 分支需要 pixmap。"""
    from PyQt5.QtGui import QTransform
    src = img if img is not None else (pix.toImage() if pix is not None else None)
    if src is None or src.isNull():
        return
    if not tf and not rot:
        if img is not None:
            p.drawImage(r, img)
        else:
            p.drawPixmap(r, pix, QRect(0, 0, pix.width(), pix.height()))
        return
    out = src
    if tf:
        out = out.mirrored(bool(tf & 1), bool(tf & 2))
    if rot:
        out = out.transformed(QTransform().rotate(rot * 90))
    p.drawImage(r, out)


def _paint_pix(p, r, w):
    _draw_tf(p, r, pix=w._pix, tf=getattr(w, "_tf", 0), rot=getattr(w, "_rot", 0))


def _paint_img(p, r, w, show_img):
    _draw_tf(p, r, img=show_img, tf=getattr(w, "_tf", 0), rot=getattr(w, "_rot", 0))


def _menu_tf(w, m):
    tsm = QMenu(D("变换"), m)
    act(tsm, D("左右镜像"), lambda: w.tf_h())
    act(tsm, D("上下镜像"), lambda: w.tf_v())
    act(tsm, D("旋转 90°"), lambda: w.tf_rot())
    m.addMenu(tsm)


# ---- 标注（红框 / 箭头 / 涂写 / 马赛克；坐标存 0..1 归一化，缩放移动不跑偏） ----

_ANNOT_TOOLS = (("box", "红框"), ("arrow", "箭头"), ("pen", "涂写"), ("mos", "马赛克"))


def _annot_toggle(w):
    if getattr(w, "_annot", False):
        if getattr(w, "_cur_stroke", None) is not None:
            w._strokes.append(w._cur_stroke)
            w._cur_stroke = None
        w._annot = False
        _float_tip(D("完成标注"))
    else:
        w._annot = True
        _float_tip(D("开始标注"))
    try:
        w.update()
    except Exception:
        pass


def _annot_tool(w, key):
    w._tool = key
    w._annot = True                    # 选工具即进入标注
    try:
        w.update()
    except Exception:
        pass


def _annot_color(w, hx):
    w._pen_c = hx


def _annot_width(w, v):
    w._pen_w = int(v)


def _annot_undo(w):
    if getattr(w, "_strokes", None):
        w._strokes.pop()
        try:
            w.update()
        except Exception:
            pass


def _annot_clear(w):
    if getattr(w, "_strokes", None):
        del w._strokes[:]
        try:
            w.update()
        except Exception:
            pass


def _annot_menu(w, m):
    if w.kind != "shot":
        return
    am = QMenu(D("标注（红框/箭头/涂写）"), m)
    state_t = D("完成标注") if getattr(w, "_annot", False) else D("开始标注")
    act(am, state_t, lambda: _annot_toggle(w))
    am.addSeparator()
    for key, lab in _ANNOT_TOOLS:
        act(am, D(lab), lambda k=key: _annot_tool(w, k),
            checked=(getattr(w, "_tool", "pen") == key))
    am.addSeparator()
    cm = QMenu(D("画笔颜色"), am)
    for hx in TXT_SWATCH:
        act(cm, hx, lambda c=hx: _annot_color(w, c),
            checked=(getattr(w, "_pen_c", "#E53935") == hx))
    am.addMenu(cm)
    wm = QMenu(D("笔画粗细"), am)
    for ww in (2, 4, 8):
        act(wm, "%d px" % ww, lambda v=ww: _annot_width(w, v),
            checked=(getattr(w, "_pen_w", 4) == ww))
    am.addMenu(wm)
    am.addSeparator()
    act(am, D("撤销一笔"), lambda: _annot_undo(w))
    act(am, D("清除全部标注"), lambda: _annot_clear(w))
    m.addMenu(am)


def _arrow_head(c, a, b, size):
    """朝 b 方向的箭头两撇；c=QPainter。"""
    import math
    from PyQt5.QtCore import QPointF
    ang = math.atan2(b.y() - a.y(), b.x() - a.x())
    for da in (math.pi * 0.83, -math.pi * 0.83):
        x = b.x() + size * math.cos(ang + da)
        y = b.y() + size * math.sin(ang + da)
        c.drawLine(b, QPointF(x, y))


def _draw_strokes(p, w, strokes):
    """画标注（点位 0..1 归一化 → 换算窗口像素）。w 只要 width/height/_pix。"""
    from PyQt5.QtGui import QPen, QPolygonF
    from PyQt5.QtCore import QPointF as FP, QRectF
    W, H = float(w.width()), float(w.height())
    if W <= 0 or H <= 0:
        return
    smooth = True
    for st in strokes:
        pts = st.get("pts") or []
        if len(pts) < 2:
            continue
        col = QColor(st.get("c", "#E53935"))
        wid = int(st.get("w", 4))
        t = st.get("t", "pen")
        px = [FP(nx * W, ny * H) for nx, ny in pts]
        if t == "pen":
            p.setPen(QPen(col, wid, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            p.drawPolyline(QPolygonF(px))
        elif t in ("box", "arrow"):
            p.setPen(QPen(col, wid, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            x0, y0 = px[0].x(), px[0].y()
            x1, y1 = px[-1].x(), px[-1].y()
            if t == "box":
                p.drawRect(QRectF(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0)))
            else:
                a, b = px[0], px[-1]
                p.drawLine(a, b)
                _arrow_head(p, a, b, max(8.0, wid * 4.0))
        elif t == "mos":
            # 马赛克：按归一化矩形回采 _pix，缩 1/20 再放回 → 打码
            x0, y0 = min(px[0].x(), px[-1].x()), min(px[0].y(), px[-1].y())
            x1, y1 = max(px[0].x(), px[-1].x()), max(px[0].y(), px[-1].y())
            rect = QRectF(x0, y0, x1 - x0, y1 - y0)
            if rect.width() < 3 or rect.height() < 3:
                continue
            pix = getattr(w, "_pix", None)
            if pix is None or pix.isNull():
                continue
            fx, fy = pix.width() / W, pix.height() / H
            pr = QRect(int(rect.x() * fx), int(rect.y() * fy),
                       max(1, int(rect.width() * fx)), max(1, int(rect.height() * fy)))
            pr = pr.intersected(QRect(0, 0, pix.width(), pix.height()))
            if pr.isEmpty():
                continue
            crop = pix.copy(pr)
            small = crop.scaled(max(1, pr.width() // 20), max(1, pr.height() // 20),
                                Qt.IgnoreAspectRatio, Qt.FastTransformation)
            big = small.scaled(pr.width(), pr.height(), Qt.IgnoreAspectRatio, Qt.FastTransformation)
            p.setRenderHint(QPainter.SmoothPixmapTransform, False)
            p.drawPixmap(rect.toRect(), big, QRect(0, 0, big.width(), big.height()))
            smooth = False
    if not smooth:
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)


def flatten_shot_img(w):
    """把标注合成进截图原图（窗口坐标按比例映射回原分辨率）。无标注返回原图。"""
    pix = getattr(w, "_pix", None)
    if pix is None or pix.isNull():
        return None
    strokes = list(getattr(w, "_strokes", []) or [])
    if not strokes or w.width() <= 0 or w.height() <= 0:
        return pix.toImage()
    out = pix.copy()
    p = QPainter(out)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    p.scale(pix.width() / float(w.width()), pix.height() / float(w.height()))
    _draw_strokes(p, w, strokes)
    p.end()
    return out.toImage()


def flatten_shot(w, path):
    try:
        im = flatten_shot_img(w)
        if im is None:
            return w._pix.save(path, "PNG")
        return im.save(path, "PNG")
    except Exception:
        try:
            return w._pix.save(path, "PNG")
        except Exception:
            return False


# ---- 方法挂到 OverlayWindow（定义时类体已结束，运行期菜单才取，安全） ----

def _tf_h(self):
    self._tf = getattr(self, "_tf", 0) ^ 1
    self.update()


def _tf_v(self):
    self._tf = getattr(self, "_tf", 0) ^ 2
    self.update()


def _tf_rot(self):
    self._rot = (getattr(self, "_rot", 0) + 1) & 3
    try:
        self.resize(self.height(), self.width())   # 90°/270° 窗口宽高互换，内容才不裁变形
        if getattr(self, "anchor", 0) > 0:
            self.apply_anchor()
    except Exception:
        pass
    self.update()


OverlayWindow.tf_h = _tf_h
OverlayWindow.tf_v = _tf_v
OverlayWindow.tf_rot = _tf_rot


def _capture_or_warn():
    img = capture_screen()
    if img is None or img.isNull():
        if overlays:
            show_msg(overlays[0], D("截图失败"))
        return None
    return img


def toggle_shot():
    """热键（默认 Ctrl+Alt+S）：没显示→再截一张入槽并显示；有显示→隐藏（留槽，内存不放）。"""
    w = _shot[0]
    if w is not None and w.isVisible():
        try:
            _shot[0] = None
            w.hide()
        except Exception:
            _shot[0] = None
        try:
            _mp_refresh()
        except Exception:
            pass
        return
    img = _capture_or_warn()
    if img is None:
        return
    w = ShotOverlay(img)
    _append_slot(w)
    set_shot_visible(w)
    show_msg(w, D("截图已显示") + " (%d/%d)" % (_shots.index(w) + 1, len(_shots)))
    _apply_shot_style(w)


def shot_next():
    """切换下一张临时图片（循环轮播）。没存的就新截一张。"""
    if len(_shots) < 2:
        img = _capture_or_warn()
        if img is None:
            return
        if _shot[0] is None or not _shot[0].isVisible():
            w = ShotOverlay(img)
            _append_slot(w)
            set_shot_visible(w)
            _apply_shot_style(w)
            show_msg(w, D("截图已显示") + " (%d/%d)" % (_shots.index(w) + 1, len(_shots)))
        return
    try:
        cur = _shots.index(_shot[0]) if _shot[0] in _shots else -1
    except ValueError:
        cur = -1
    nxt = _shots[(cur + 1) % len(_shots)]
    set_shot_visible(nxt)
    _apply_shot_style(nxt)
    show_msg(nxt, "%d/%d" % (_shots.index(nxt) + 1, len(_shots)))


def shot_delete(w=None):
    """删除指定那张（默认=当前活动）。内存立即释放。"""
    if w is None:
        w = _shot[0]
    if w is None:
        if overlays:
            show_msg(overlays[0], D("没有临时图片"))
        return
    try:
        _shots.remove(w)
    except ValueError:
        pass
    if _shot[0] is w:
        _shot[0] = None
    try:
        w.hide()
        w.deleteLater()
    except Exception:
        pass
    if _shots:
        set_shot_visible(_shots[-1])
        show_msg(_shots[-1], "%d/%d" % (len(_shots), len(_shots)))
    try:
        _mp_refresh()
    except Exception:
        pass


def shot_delete_all():
    """一键删除全部临时图片（内存全部释放）。"""
    if not _shots and _shot[0] is None:
        if overlays:
            show_msg(overlays[0], D("没有临时图片"))
        return
    for w in list(_shots):
        try:
            w.hide()
            w.deleteLater()
        except Exception:
            pass
    _shots.clear()
    _shot[0] = None
    try:
        _mp_refresh()
    except Exception:
        pass
    if overlays:
        show_msg(overlays[0], D("已清全部临时图片"))


def save_shot_async(w=None):
    """右键/热键「保存临时图片」：选目录 → 同步存 PNG（QSaveFile，几百 ms 内完成）。
    存盘后内存槽照常（可继续切换/删除）；文件名带时间戳防重名。"""
    try:
        if w is None:
            w = _shot[0]
        if w is None or getattr(w, "_pix", None) is None or w._pix.isNull():
            if overlays:
                show_msg(overlays[0], D("没有临时图片"))
            return
        d = QFileDialog.getExistingDirectory(w, D("选择保存目录"),
                                            getattr(save_shot_async, "lastdir", "") or "")
        if not d:
            return
        save_shot_async.lastdir = d
        try:
            import time as _t
            name = "临时截图_%s_%d.png" % (_t.strftime("%Y%m%d_%H%M%S"), _t.time_ns() % 1000)
        except Exception:
            name = "临时截图.png"
        path = os.path.join(d, name)
        try:
            ok = flatten_shot(w, path)
        except Exception:
            ok = False
        show_msg(w, (D("已保存") + " " + name) if ok else D("保存失败"))
    except Exception:
        if os.environ.get("SCREENPIN_DEBUG"):
            import traceback as _tb
            _tb.print_exc()


def new_text_overlay(anchor_w=None):
    w = TextOverlay()
    overlays.append(w)
    try:
        g = screen_rect_for(w)
        w.move(g.left() + 60 + (len(overlays) * 24) % 300,
               g.top() + 60 + (len(overlays) * 24) % 300)
    except Exception:
        pass
    w.show()
    ensure_hotkey()
    force_topmost(w)
    try:
        _mp_refresh()
    except Exception:
        pass
    return w


# ================= 设置（热键/截图/语言） =================

def pick_hk(parent, cur):
    """按键捕获对话框：按新组合（须带修饰键）→ 返回 'Ctrl+Alt+X'；取消/违规 None。"""
    dlg = QDialog(parent)
    dlg.setWindowTitle(D("全局热键"))
    lay = QVBoxLayout(dlg)
    lab = QLabel(cur or "")
    lab.setAlignment(Qt.AlignCenter)
    f = QFont()
    f.setPixelSize(18)
    lab.setFont(f)
    lay.addWidget(lab)
    hint2 = QLabel(D("按新组合键（须带 Ctrl/Alt/Shift/Win）…\n只按 Esc 可取消"))
    hint2.setWordWrap(True)
    lay.addWidget(hint2)
    state = {"spec": None}

    def poll():
        u32 = ctypes.windll.user32
        mods = 0
        if u32.GetAsyncKeyState(0x11) & 0x8000:
            mods |= 1
        if u32.GetAsyncKeyState(0x12) & 0x8000:
            mods |= 2
        if u32.GetAsyncKeyState(0x10) & 0x8000:
            mods |= 4
        if u32.GetAsyncKeyState(0x5B) & 0x8000:
            mods |= 8
        vk = 0
        for k in list(range(0x30, 0x5B)) + list(range(0x70, 0x88)) + [0x20, 0x09]:
            if u32.GetAsyncKeyState(k) & 0x8000:
                vk = k
                break
        if vk and mods:
            seq = []
            if mods & 1:
                seq.append("Ctrl")
            if mods & 2:
                seq.append("Alt")
            if mods & 4:
                seq.append("Shift")
            if mods & 8:
                seq.append("Win")
            if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
                base = chr(vk)
            elif 0x70 <= vk <= 0x87:
                base = "F%d" % (vk - 0x6F)
            elif vk == 0x20:
                base = "Space"
            elif vk == 0x09:
                base = "Tab"
            else:
                base = "0x%02X" % vk
            s = "+".join(seq + [base])
            if parse_hk(s):
                state["spec"] = s
                lab.setText(s)
                tm.stop()
    tm = QTimer(dlg)
    tm.setInterval(50)
    tm.timeout.connect(poll)
    tm.start()
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    lay.addWidget(bb)
    if dlg.exec_() == QDialog.Accepted and state["spec"]:
        return state["spec"]
    return None


# ================= 小面板（托盘箭头那种一格格任务的小窗） =================

def _mp_place(p):
    p.show()
    p.adjustSize()
    try:
        from PyQt5.QtGui import QGuiApplication as _G
        scr = _G.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        g = scr.availableGeometry()
        p.move(g.right() - p.width() - 14, g.bottom() - p.height() - 14)
    except Exception:
        pass
    p.raise_()
    return p


def toggle_mp():
    w = _mp[0]
    if w is not None:
        try:
            if w.isVisible():
                w.hide()
                w.deleteLater()
                _mp[0] = None
                return
        except Exception:
            _mp[0] = None
            return
        _mp[0] = None
    _mp_place(build_mini_panel())


def _mp_refresh():
    """清单变化后原地重建（可见时才动）。"""
    w = _mp[0]
    if w is None:
        return
    try:
        if not w.isVisible():
            return
        w.hide()
        w.deleteLater()
    except Exception:
        pass
    _mp[0] = None
    _mp_place(build_mini_panel())


def build_mini_panel():
    panel = _panel[0]
    w = QWidget(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
    w.setObjectName("miniPanel")
    w.setStyleSheet(
        "QWidget#miniPanel{background:%(bg)s; color:%(text)s; border:1px solid %(line)s;}"
        "QLabel{color:%(dim)s; background:transparent;}"
        "QPushButton{color:%(text)s; background:%(btn)s; border:1px solid %(line)s;"
        " padding:4px 8px; text-align:left; border-radius:3px;}"
        "QPushButton:hover{background:%(btnh)s;}" % theme())
    lay = QVBoxLayout(w)
    lay.setContentsMargins(10, 8, 10, 10)
    lay.setSpacing(6)
    title = QLabel(APP_NAME + " · " + D("小面板") + "   " + HK.get("panel", ""))
    title.setStyleSheet("font-weight:bold; color:#BFBFBF; background:transparent;")
    lay.addWidget(title)
    tasks = [
        (D("打开图片/视频…"), lambda: _pick_and_open(panel)),
        (D("新建文字贴图"), lambda: (new_text_overlay(panel), _mp_refresh())),
        (D("临时截图"), toggle_shot),
        (D("框选截图"), start_region_shot),
        (D("取色器"), pick_color_under_cursor),
        (D("点击穿透"), lambda: (_hk_toggle_pass(), _mp_refresh())),
        (D("全部置顶"), apply_topmost_force_all),
        (D("中英切换"), lambda: set_language("zh" if LANG["code"] == "en" else "en")),
        (D("多图片批量设置…"), lambda: open_multi_settings(w)),
        (D("设置"), lambda: open_settings(w)),
        (D("打开官网"), open_site),
        (D("关于"), lambda: _about(w)),
        (D("退出"), quit_app),
        (D("关闭面板"), toggle_mp),
    ]
    grid = QGridLayout()
    grid.setSpacing(4)
    for i, (lab, fn) in enumerate(tasks):
        b = QPushButton(lab)
        b.clicked.connect(fn)
        grid.addWidget(b, i // 2, i % 2)
    lay.addLayout(grid)
    sep = QLabel(D("当前贴图") + " (%d)" % len(overlays))
    sep.setStyleSheet("color:#9A9A9A; background:transparent; margin-top:4px;")
    lay.addWidget(sep)
    if overlays:
        body = QWidget()
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(0, 0, 0, 0)
        body_l.setSpacing(3)
        for o in list(overlays):
            row = QHBoxLayout()
            nm = QPushButton(overlay_display_name(o))
            nm.clicked.connect(lambda _c=False, o=o: (o.raise_(), force_topmost(o)))
            x = QPushButton("×")
            x.setFixedWidth(26)

            def mk_close(o):
                def _c():
                    close_overlay(o)
                    _mp_refresh()
                return _c
            x.clicked.connect(mk_close(o))
            row.addWidget(nm, 1)
            row.addWidget(x)
            body_l.addLayout(row)
        scr = QScrollArea()
        scr.setWidget(body)
        scr.setWidgetResizable(True)
        scr.setFixedHeight(min(190, 34 + 37 * len(overlays)))
        scr.setStyleSheet("QScrollArea{border:none; background:transparent;}")
        lay.addWidget(scr)
    else:
        lay.addWidget(QLabel(D("（没有贴图）")))
    w.setFixedSize(w.sizeHint())
    return w


def overlay_display_name(o):
    try:
        k = getattr(o, "kind", None)
        if k == "text":
            t = (getattr(o, "text", "") or "").replace("\n", " ")
            return D("文字") + " · " + (t[:14] + ("…" if len(t) > 14 else ""))
        if k == "shot":
            return D("临时截图")
        p = getattr(o, "source_path", "") or ""
        if p:
            return os.path.basename(p)
        return k or D("贴图")
    except Exception:
        return D("贴图")


def apply_batch(sel, pos=None, opa=None, size=None):
    """多图片批量套用：pos=锚点1..9 / opa=不透明度 / size=大小%（None=不改）。"""
    for o in sel:
        try:
            if pos:
                o.set_anchor(int(pos))
            if opa:
                o.set_opacity(int(opa))
            if size:
                o.set_pct(int(size), announce=False)
        except Exception:
            continue


def build_multi_settings(parent=None):
    dlg = QDialog(parent)
    dlg.setWindowTitle(D("多图片批量设置…"))
    lay = QVBoxLayout(dlg)
    ovs = list(overlays)
    if not ovs:
        lay.addWidget(QLabel(D("（没有贴图）")))
    lw = QListWidget()
    for o in ovs:
        it = QListWidgetItem(overlay_display_name(o))
        it.setCheckState(Qt.Unchecked)
        lw.addItem(it)
    lay.addWidget(lw)
    r0 = QHBoxLayout()
    r0.addWidget(QPushButton(D("全选")))
    r0.addWidget(QPushButton(D("清空选择")))
    lay.addLayout(r0)
    r1 = QHBoxLayout()
    c_pos = QCheckBox(D("应用位置"))
    combo_p = QComboBox()
    for n in anchor_list()[1:]:
        combo_p.addItem(n)
    r1.addWidget(c_pos)
    r1.addWidget(combo_p, 1)
    lay.addLayout(r1)
    r2 = QHBoxLayout()
    c_opa = QCheckBox(D("应用不透明度"))
    sp_o = QSpinBox()
    sp_o.setRange(10, 100)
    sp_o.setSuffix(" %")
    sp_o.setValue(70)
    r2.addWidget(c_opa)
    r2.addWidget(sp_o)
    lay.addLayout(r2)
    r3 = QHBoxLayout()
    c_sz = QCheckBox(D("应用大小"))
    sp_s = QSpinBox()
    sp_s.setRange(5, 800)
    sp_s.setSuffix(" %")
    sp_s.setValue(100)
    r3.addWidget(c_sz)
    r3.addWidget(sp_s)
    lay.addLayout(r3)
    bb = QDialogButtonBox()
    btn_apply = bb.addButton(D("应用到选中"), QDialogButtonBox.ActionRole)
    btn_close_sel = bb.addButton(D("关闭选中的贴图"), QDialogButtonBox.DestructiveRole)
    bb.addButton(QDialogButtonBox.Close)
    lay.addWidget(bb)

    def selected():
        out = []
        for i in range(lw.count()):
            if lw.item(i).checkState() == Qt.Checked and i < len(ovs):
                out.append(ovs[i])
        return out

    r0.itemAt(0).widget().clicked.connect(
        lambda: [lw.item(i).setCheckState(Qt.Checked) for i in range(lw.count())])
    r0.itemAt(1).widget().clicked.connect(
        lambda: [lw.item(i).setCheckState(Qt.Unchecked) for i in range(lw.count())])

    def do_apply():
        apply_batch(selected(),
                     pos=(combo_p.currentIndex() + 1) if c_pos.isChecked() else None,
                     opa=int(sp_o.value()) if c_opa.isChecked() else None,
                     size=int(sp_s.value()) if c_sz.isChecked() else None)

    def do_close_sel():
        for o in selected():
            close_overlay(o)
    btn_apply.clicked.connect(do_apply)
    btn_close_sel.clicked.connect(do_close_sel)
    bb.rejected.connect(dlg.reject)
    return dlg


def open_multi_settings(parent=None):
    try:
        build_multi_settings(parent).exec_()
    except Exception:
        if os.environ.get("SCREENPIN_DEBUG"):
            import traceback as _tb
            _tb.print_exc()


def _tray_activated(reason):
    """托盘左键 = 开/关小面板（右键照旧出菜单）。"""
    try:
        if int(reason) == int(QSystemTrayIcon.Trigger):
            toggle_mp()
    except Exception:
        pass


def build_tray_menu():
    panel = _panel[0]
    tm = QMenu()
    act(tm, D("打开新贴图…"), lambda: _pick_and_open(panel))
    act(tm, D("新建文字贴图"), lambda: new_text_overlay(panel))
    act(tm, D("小面板开/关") + "  " + HK.get("panel", ""), toggle_mp)
    act(tm, D("多图片批量设置…"), lambda: open_multi_settings(panel))
    act(tm, D("打开官网"), open_site)
    act(tm, D("检查更新"), lambda: check_update(manual=True))
    act(tm, D("临时截图(热键)") + "  " + HK.get("shot", ""), toggle_shot)
    act(tm, D("保存临时图片…"), lambda: save_shot_async())
    act(tm, D("下一张临时图片"), shot_next)
    act(tm, D("删除全部临时图片"), shot_delete_all)
    act(tm, D("取色器"), pick_color_under_cursor)
    act(tm, D("框选截图"), start_region_shot)
    act(tm, D("设置"), lambda: open_settings(panel))
    tm.addSeparator()
    act(tm, D("全部置顶"), apply_topmost_force_all)
    act(tm, D("全部解除穿透"),
        lambda: [set_click_through(o, False) for o in list(overlays)])
    tm.addSeparator()
    act(tm, D("退出"), quit_app)
    return tm


def open_settings(parent=None):
    try:
        par = parent
        if par is None:
            par = QApplication.activeWindow()
        dlg = QDialog(par)
        dlg.setWindowTitle(D("设置"))
        lay = QVBoxLayout(dlg)
        # 语言
        r0 = QHBoxLayout()
        r0.addWidget(QLabel(D("界面语言")))
        combo_l = QComboBox()
        combo_l.addItem(D("中文"), "zh")
        combo_l.addItem("English", "en")
        combo_l.setCurrentIndex(1 if LANG["code"] == "en" else 0)
        r0.addWidget(combo_l)
        lay.addLayout(r0)
        # 热键
        lay.addWidget(QLabel("<b>" + D("全局热键") + "</b>"))
        rows = {}
        _hk_rows = (("pass", D("点击穿透热键")), ("shot", D("临时截图热键")),
                    ("panel", D("小面板热键")), ("save", D("保存临时图片热键")),
                    ("switch", D("切换临时图片热键")),
                    ("del", D("删除临时图片热键")), ("delall", D("删除全部图片热键")),
                    ("color", D("取色热键")), ("region", D("框选截图热键")))
        for key, lab in _hk_rows:
            r = QHBoxLayout()
            r.addWidget(QLabel(lab))
            e = QLineEdit(HK.get(key, ""))
            if not (HK.get(key) or "").strip():
                e.setPlaceholderText(D("未绑定（点“改”设置）"))
            b = QPushButton(D("改"))
            r.addWidget(e, 1)
            r.addWidget(b)
            lay.addLayout(r)
            rows[key] = (e, b)

        def bind_hk(key, btn):
            def _c():
                s = pick_hk(dlg, HK.get(key, ""))
                if s:
                    rows[key][0].setText(s)
            btn.clicked.connect(_c)
        for k in rows:
            bind_hk(k, rows[k][1])
        lay.addWidget(QLabel(D("要求带修饰键 (Ctrl/Alt/Shift/Win)")))
        # 临时截图
        lay.addWidget(QLabel("<b>" + D("临时截图") + "</b>"))
        r1 = QHBoxLayout()
        r1.addWidget(QLabel(D("放置位置")))
        combo_a = QComboBox()
        for n in anchor_list()[1:]:
            combo_a.addItem(n)
        combo_a.setCurrentIndex(max(0, min(8, SHOT_CFG["anchor"] - 1)))
        r1.addWidget(combo_a)
        lay.addLayout(r1)
        r2 = QHBoxLayout()
        r2.addWidget(QLabel(D("宽度")))
        sp_w = QSpinBox()
        sp_w.setRange(5, 100)
        sp_w.setSuffix(" %")
        sp_w.setValue(int(SHOT_CFG["pct"]))
        r2.addWidget(sp_w)
        lay.addLayout(r2)
        r3 = QHBoxLayout()
        r3.addWidget(QLabel(D("不透明度 %")))
        sp_o = QSpinBox()
        sp_o.setRange(10, 100)
        sp_o.setSuffix(" %")
        sp_o.setValue(int(SHOT_CFG["opacity"]))
        r3.addWidget(sp_o)
        lay.addLayout(r3)
        chk_cursor = QCheckBox(D("截图时包含鼠标指针"))
        chk_cursor.setChecked(bool(int(SHOT_CFG.get("cursor", 1))))
        lay.addWidget(chk_cursor)
        # 主题 / 启动行为 / 更新
        lay.addWidget(QLabel("<b>" + D("个性化") + "</b>"))
        r4 = QHBoxLayout()
        r4.addWidget(QLabel(D("主题")))
        combo_t = QComboBox()
        for nm, _c in THEMES:
            combo_t.addItem(nm)
        combo_t.setCurrentIndex(max(0, min(len(THEMES) - 1, int(SETTINGS.get("theme", 0)))))
        r4.addWidget(combo_t, 1)
        lay.addLayout(r4)
        chk_restore = QCheckBox(D("启动时恢复上次的贴图（默认关：每次启动自己选）"))
        chk_restore.setChecked(bool(SETTINGS.get("restore")))
        lay.addWidget(chk_restore)
        chk_auto = QCheckBox(D("启动时检查更新"))
        chk_auto.setChecked(bool(SETTINGS.get("autoupdate")))
        lay.addWidget(chk_auto)
        r5 = QHBoxLayout()
        b_site = QPushButton(D("打开官网"))
        b_site.clicked.connect(open_site)
        b_upd = QPushButton(D("检查更新"))
        b_upd.clicked.connect(lambda: check_update(manual=True))
        b_rst = QPushButton(D("一键初始化"))
        b_rst.clicked.connect(lambda: _do_reset(dlg))
        b_afd = QPushButton(D("支持开发"))
        b_afd.setToolTip("afdian.com/a/AKM771")
        b_afd.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(AFDIAN_URL)))
        r5.addWidget(b_site)
        r5.addWidget(b_afd)
        r5.addWidget(b_upd)
        r5.addWidget(b_rst)
        lay.addLayout(r5)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        lay.addWidget(bb)
        bb.rejected.connect(dlg.reject)

        def accept():
            seen = {}
            for k in HK_KEYS:
                s = rows[k][0].text().strip()
                if s and not parse_hk(s):
                    QMessageBox.warning(dlg, APP_NAME,
                                        D("无效热键（须带 Ctrl/Alt/Shift/Win）"))
                    return
                if s and s in seen and seen[s] != k:
                    QMessageBox.warning(dlg, APP_NAME,
                                        D("热键冲突：%s 已被占用") % s)
                    return
                if s:
                    seen[s] = k
            for k in HK_KEYS:
                HK[k] = rows[k][0].text().strip()
                HKC[k] = parse_hk(HK[k]) or None      # 空串 → None（未绑定不轮询）
            for k in HK_KEYS:
                _hotkey_prev[k] = False
            SHOT_CFG["anchor"] = combo_a.currentIndex() + 1
            SHOT_CFG["pct"] = int(sp_w.value())
            SHOT_CFG["opacity"] = int(sp_o.value())
            SHOT_CFG["cursor"] = 1 if chk_cursor.isChecked() else 0
            newlang = combo_l.currentData() or "zh"
            newtheme = int(combo_t.currentIndex())
            oldtheme = int(SETTINGS.get("theme", 0))
            SETTINGS["restore"] = 1 if chk_restore.isChecked() else 0
            SETTINGS["autoupdate"] = 1 if chk_auto.isChecked() else 0
            SETTINGS["theme"] = newtheme
            dlg.accept()
            if newtheme != oldtheme:
                apply_theme(newtheme)
            if newlang != LANG["code"]:
                set_language(newlang)
            else:
                save_config()
        bb.accepted.connect(accept)
        dlg.exec_()
    except Exception:
        if os.environ.get("SCREENPIN_DEBUG"):
            import traceback as _tb
            _tb.print_exc()


def _do_reset(dlg):
    """设置框里的一键初始化：确认后回出厂并关掉设置框。"""
    try:
        mb = QMessageBox.question(dlg, D("一键初始化"),
                                  D("将关闭所有贴图，并把热键/主题/语言/截图设置恢复默认。\n确定继续？"),
                                  QMessageBox.Yes | QMessageBox.No)
        if mb != QMessageBox.Yes:
            return
        reset_settings()
        dlg.reject()
        # 回到干净状态：启动面板还在（后台常驻），直接再选素材即可
    except Exception:
        if os.environ.get("SCREENPIN_DEBUG"):
            import traceback as _tb
            _tb.print_exc()


def set_language(code):
    """中英切换：语言表全局生效，启动面板/托盘菜单即时刷新，素材窗口重绘。"""
    LANG["code"] = "en" if str(code).lower() == "en" else "zh"
    try:
        for wdg in QApplication.topLevelWidgets():
            try:
                if isinstance(wdg, DropPanel):
                    wdg.refresh_texts()
            except Exception:
                pass
        if tray is not None:
            tray.setContextMenu(build_tray_menu())
    except Exception:
        pass
    for o in list(overlays):
        try:
            o.update()
        except Exception:
            pass
    try:
        _mp_refresh()      # 小面板文案也切语言
    except Exception:
        pass
    save_config()


# ================= 主入口 =================

def main():
    global app, single_file, tray
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # 纯 os 层解析参数（可在 QApplication 之前做）
    args = [a for a in sys.argv[1:] if a]
    files = list_files(args)
    if files:
        single_file = files[0]

    # 启动期先读配置：语言（对话框即时生效）、热键、截图设置
    try:
        _cfg0 = load_config()
    except Exception:
        _cfg0 = {}
    try:
        _STARTUP_LANG["code"] = "en" if str(_cfg0.get("lang", "zh")).lower() == "en" else "zh"
    except Exception:
        _STARTUP_LANG["code"] = "zh"
    LANG["code"] = _STARTUP_LANG["code"]
    apply_global_cfg(_cfg0)
    _dbg("startup lang=%s theme=%d restore=%d autoupdate=%d" % (
        LANG["code"], SETTINGS.get("theme", 0),
        SETTINGS.get("restore", 0), SETTINGS.get("autoupdate", 1)))

    app = QApplication(sys.argv)
    # 热键（7 项，新 4 项默认空=未绑定）
    for _k in HK_KEYS:
        HKC[_k] = parse_hk(HK.get(_k, "")) or None
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)   # 后台常驻：关窗不退出（退出只有托盘/菜单/热键）
    app.setWindowIcon(app_icon())
    try:
        apply_theme()                      # 启动即套用配置里的主题
    except Exception:
        pass
    app.aboutToQuit.connect(save_config)

    # 单实例：已有实例在跑时，把文件交给它再退出
    sock, ok = init_client()
    if ok:
        if files:
            send_files(sock, files)
        else:
            # 不弹窗打扰：给已在跑的实例发“唤起小面板”
            send_raw_cmd(sock, "showpanel")
        try:
            sock.disconnectFromServer()
        except Exception:
            pass
        return 0

    server = init_server()
    if server is not None:
        try:
            server.newConnection.connect(
                lambda: _handle_conn(server.nextPendingConnection()))
        except Exception:
            pass

    # 初始素材：命令行参数优先。上次的贴图**默认不复读**（restore=1 才恢复）
    items = [{"file": f, "anchor": 0} for f in files]
    if not items and SETTINGS.get("restore"):
        for it in _cfg0.get("overlays", []):
            if str(it.get("type", "")) == "text":
                items.append({"type": "text", "anchor": it.get("anchor", 0),
                              "text": it.get("text", ""),
                              "font_px": it.get("font_px", TXT_DEF["font_px"]),
                              "color": it.get("color", TXT_DEF["color"]),
                              "bold": it.get("bold", TXT_DEF["bold"]),
                              "bg": it.get("bg", TXT_DEF["bg"]),
                              "bgcolor": it.get("bgcolor", TXT_DEF.get("bgcolor", "#202022"))})
                continue
            p = it.get("file")
            if p and os.path.isfile(p) and is_media_file(p):
                try:
                    anc = int(it.get("anchor", 0))
                except Exception:
                    anc = 0
                items.append({"file": p, "anchor": anc,
                              "kf": it.get("kf"),
                              "kf_loop": it.get("kf_loop", True)})

    # 启动面板（选文件 + 托盘 + 关于）
    panel = DropPanel(None)
    panel.setWindowTitle(D(APP_NAME))
    panel.setWindowIcon(app_icon())
    lay = QVBoxLayout(panel)
    hint = QLabel(D("把图片或视频拖到本窗口，\n或点下面的按钮选择。"))
    hint.setWordWrap(True)
    lay.addWidget(hint)
    btn = QPushButton(D("选择图片/视频…"))
    btn.clicked.connect(lambda: _pick_and_open(panel))
    lay.addWidget(btn)
    hb_ = QHBoxLayout()
    about_btn = QPushButton(D("设置"))
    about_btn.clicked.connect(lambda: open_settings(panel))
    quit_btn = QPushButton(D("退出"))
    quit_btn.clicked.connect(quit_app)
    hb_.addWidget(about_btn)
    hb_.addWidget(quit_btn)
    lay.addLayout(hb_)
    panel.hint_w, panel.btn_w = hint, btn
    panel.set_w, panel.quit_w = about_btn, quit_btn
    panel.resize(300, 150)
    panel.show()

    # 托盘（菜单由 build_tray_menu 单一来源构建，语言切换时整体重建）
    try:
        _panel[0] = panel
        tray = QSystemTrayIcon(app_icon(), app)
        tray.setContextMenu(build_tray_menu())
        try:
            tray.activated.connect(_tray_activated)   # 左键=开/关小面板，双击=小面板
        except Exception:
            pass
        tray.setToolTip(D(APP_NAME) + " " + VERSION + "  ·  " + HK.get("shot", "Ctrl+Alt+S") + " 截图")
        tray.show()
    except Exception:
        tray = None

    ensure_hotkey()
    if SETTINGS.get("autoupdate"):
        QTimer.singleShot(5000, _update_tick)   # 启动 5s 后静默查一次更新（有更新才提示）
    _dbg("items=%d restore=%d" % (len(items), SETTINGS.get("restore", 0)))

    if items:
        QTimer.singleShot(150, lambda: _open_all(items))

    QTimer.singleShot(4000, _topmost_tick)
    return app.exec_()


def _topmost_tick():
    apply_topmost_force_all()
    QTimer.singleShot(4000, _topmost_tick)


def _open_all(items):
    for it in items:
        if str(it.get("type", "")) == "text":
            w = new_text_overlay()
            try:
                w.text = str(it.get("text", TXT_DEF["text"]))
                w._base_font = int(it.get("font_px", TXT_DEF["font_px"]))
                w.font_px = max(8, int(round(w._base_font * w.scale)))
                w.text_color = QColor(it.get("color", TXT_DEF["color"]))
                w.bold = bool(it.get("bold", TXT_DEF["bold"]))
                w.bg_on = bool(it.get("bg", TXT_DEF["bg"]))
                w.bg_color = QColor(it.get("bgcolor", TXT_DEF.get("bgcolor", "#202022")))
                w._resize_to_text()
            except Exception:
                pass
            try:
                anc = int(it.get("anchor", 0))
            except Exception:
                anc = 0
            if anc:
                w.set_anchor(anc)
            continue
        o = open_overlay(it["file"])
        try:
            anc = int(it.get("anchor", 0))
        except Exception:
            anc = 0
        if anc:
            o.set_anchor(anc)
        try:
            o._tf = int(it.get("tf", 0)) & 3
            o._rot = int(it.get("rot", 0)) & 3
            o.update()
        except Exception:
            pass
        # 关键帧恢复（锚点/关键帧一起恢复才有用）
        try:
            kfs = it.get("kf")
            if kfs and getattr(o, "kfc", None) is not None:
                o.kfc.kfs = [[float(t), int(x), int(y)] for t, x, y in kfs]
                o.kfc.loop = bool(it.get("kf_loop", True))
        except Exception:
            pass


def _pick_and_open(anchor_w):
    start = ""
    try:
        if single_file:
            start = os.path.dirname(single_file)
    except Exception:
        start = ""
    try:
        paths, _ = QFileDialog.getOpenFileNames(anchor_w, D("选择图片或视频"), start, media_filter())
    except Exception:
        paths, _ = QFileDialog.getOpenFileNames(None, D("选择图片或视频"), start, media_filter())
    for p in paths:
        open_overlay(p)


def _about(anchor_w):
    try:
        if LANG["code"] == "en":
            txt = (APP_NAME + " " + VERSION + "\n\n"
                   "Right-click changes everything; %s toggles click-through.\n"
                   "Icon: Google Material Design Icons \"pin\" (Apache-2.0).\n\n"
                   "Support development: afdian.com/a/AKM771\n"
                   "Website: %s") % (
                HK.get("pass", "Ctrl+Alt+P"), SITE_URL)
        else:
            txt = (APP_NAME + " " + VERSION + "\n\n"
                   "右键改一切；%s 点击穿透；%s 临时截图。\n"
                   "图标：Google Material Design Icons「pin」(Apache-2.0)。\n\n"
                   "支持开发（爱发电）：afdian.com/a/AKM771\n"
                   "官网：%s") % (
                HK.get("pass", "Ctrl+Alt+P"), HK.get("shot", "Ctrl+Alt+S"), SITE_URL)
        QMessageBox.information(anchor_w, D("关于 " + APP_NAME), txt)
    except Exception:
        pass


if __name__ == "__main__":
    sys.exit(main())
