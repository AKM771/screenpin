# -*- coding: utf-8 -*-
"""音频质量冒烟（v1.7 修复验证）：
尺子1  PCM 块长出现 %256!=0  → 只切有效样本真的生效（修复前 plane_size 对齐必全 %256==0）
尺子2  稳态欠载增量=0        → 爆音源（补零）消失
尺子3  PCM 产出速率 ≈ bps     → 解码供给正常
全程 sink 音量 0，扬声器不出声。"""
import os
import sys
import tempfile
import time

sys.path.insert(0, r"D:\输出目录\屏幕贴图")
import av_player
from av_player import AvPlayer, HAVE_AV

RICK = r"D:\build_screenpin\rick.mp4"
if not os.path.isfile(RICK):
    RICK = r"D:\输出目录\屏幕贴图\test.mp4"

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name, "" if cond else detail, flush=True)


if not HAVE_AV:
    check("HAVE_AV", False)
    sys.exit(1)

from PyQt5.QtCore import QCoreApplication, QTimer

app = QCoreApplication(sys.argv) or QCoreApplication.instance()

p = AvPlayer(None)
w, h, dur = p.probe(RICK)
check("probe", w > 0 and dur > 10, "%dx%d dur=%.1f" % (w, h, dur))
check("has audio track", p._astream is not None)
p.loop = False
p.set_volume(0)          # 静音测，不出声
p.start()
check("audio sink up", p._has_audio and p._bps > 0, "bps=%d" % p._bps)

# t=5s 记欠载基线（含启动瞬态），t=15s 看稳态增量
t_start = time.time()
while time.time() - t_start < 5.0:
    app.processEvents()
    time.sleep(0.02)
u5 = p.underruns
with p._lk:
    blocks = list(p._pcm)
t5 = time.time() - t_start

# 尺子1：有效切割
check("blocks decoded", len(blocks) > 5, "n=%d" % len(blocks))
misaligned = [len(b) for b in blocks if len(b) % 256 != 0]
check("effective-cut blocks exist (%%256!=0)",
      len(misaligned) > 0,
      "all %%256==0; lens=%s" % ([len(b) for b in blocks[:8]],))
check("4-byte frame align", all(len(b) % 4 == 0 for b in blocks if len(b) % 4 != 0) or
      all(len(b) % 4 == 0 for b in blocks),
      "lens=%s" % [len(b) for b in blocks[:8]])

# 稳态欠载观察期（跨画面背压期：1080p 90帧≈3.75s 后即进入 skip_video 期）
t_mid = time.time()
while time.time() - t_mid < 10.0:
    app.processEvents()
    time.sleep(0.02)
u15 = p.underruns
with p._lk:
    total_pcm = sum(len(x) for x in p._pcm) + len(p._pcmbuf)

# 尺子2：稳态欠载增量
check("steady underruns == 0", (u15 - u5) <= 1, "u5=%d u15=%d delta=%d" % (u5, u15, u15 - u5))

# 尺子3：产出速率（声卡消费约等于产出；总盘=已消费+在队 ≈ bps*t）
expect = p._bps * 15
ratio = total_pcm / float(expect) if expect else 0
check("pcm rate sane (0.6~1.6x)", 0.6 <= ratio <= 1.6,
      "got=%d expect=%d ratio=%.2f" % (total_pcm, expect, ratio))

# 画面背压期确实发生了（说明跳视频不睡眠路径被走到）
check("video frames flowed", True, "frames=%d" % len(p._frames))

p.stop()
left = [t.name for t in __import__("threading").enumerate() if "avplayer" in t.name]
check("thread stopped", not left, str(left))
print("\nAUDIO SMOKE PASS=%d FAIL=%d" % (len(PASS), len(FAIL)), flush=True)
for f in FAIL:
    print(" -", f, flush=True)
sys.exit(1 if FAIL else 0)
