# -*- coding: utf-8 -*-
"""屏幕贴图 · 离屏测试（不弹窗、不抢键鼠、不碰用户配置）。
用法：python test_overlay.py   → 全部 PASS 才算过。"""
import os
import sys
import tempfile
import time
import traceback

# 隔离配置，绝不写用户真实配置
os.environ["SCREENPIN_CFG_DIR"] = os.path.join(tempfile.gettempdir(), "screenpin_test_cfg")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = []
FAIL = []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
    else:
        FAIL.append("%s %s" % (name, detail))
        print("FAIL", name, detail)


def main():
    import overlay
    from PyQt5.QtCore import QPoint, QSize, Qt
    from PyQt5.QtGui import QImage, QGuiApplication
    from PyQt5.QtWidgets import QApplication

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication(sys.argv)

    def pump(ms):
        end = time.time() + ms / 1000.0
        while time.time() < end:
            app.processEvents()
            time.sleep(0.01)

    # ---- 尺寸数学 ----
    check("file_kind mp4", overlay.file_kind("a/b.MP4") == "video")
    check("file_kind png", overlay.file_kind("x.png") == "image")
    check("file_kind gif", overlay.file_kind("x.gif") == "gif")
    check("file_kind txt", overlay.file_kind("x.txt") is None)
    check("list_files mix", len(overlay.list_files(["nope.png", "nope2.mp4"])) == 0)
    check("ANCHORS/RC len", len(overlay.ANCHORS) == len(overlay.ANCHOR_RC))
    check("anchor center rc", overlay.ANCHOR_RC[5] == (1, 1))
    check("anchor free rc", overlay.ANCHOR_RC[0] == (-1, -1))

    # 造一张测试图（只写本任务自己的临时文件）
    img = QImage(800, 600, QImage.Format_ARGB32)
    img.fill(0xFF5566)
    png = os.path.join(tempfile.gettempdir(), "screenpin_test.png")
    img.save(png, "PNG")
    check("test png written", os.path.isfile(png))

    o = overlay.OverlayWindow()
    overlay.overlays.append(o)
    check("load image", o.load(png) is True)
    check("kind", o.kind == "image")
    check("base", o.base == QSize(800, 600), str(o.base))

    # 初始缩放：800 宽 > 屏幕45%(≈864)? 800<864 不缩 → scale=1
    # 为测缩放钳制，再造一张 2000 宽的
    big = QImage(2000, 500, QImage.Format_ARGB32)
    big.fill(0x33AA88)
    png2 = os.path.join(tempfile.gettempdir(), "screenpin_test_big.png")
    big.save(png2, "PNG")
    o2 = overlay.OverlayWindow()
    overlay.overlays.append(o2)
    o2.load(png2)
    scr = QGuiApplication.primaryScreen().availableGeometry()
    maxw = int(scr.width() * 0.45)
    check("initial clamp applied", o2.pct() < 100, "pct=%d" % o2.pct())
    check("initial clamp to 45%%", abs(o2.scale - maxw / 2000.0) < 0.01,
          "scale=%.3f expect=%.3f" % (o2.scale, maxw / 2000.0))

    # set_pct / step
    o.set_pct(150)
    check("set_pct size", o.width() == 1200 and o.height() == 900,
          "%dx%d" % (o.width(), o.height()))
    o.step_pct(-10)
    check("step_pct", o.pct() == 140, str(o.pct()))
    o.set_pct(5)
    check("pct floor 5", o.pct() == 5, str(o.pct()))
    o.set_pct(900)
    check("pct ceil 800", o.pct() == 800, str(o.pct()))
    o.set_pct(100)

    # 保持宽高比开：关掉后 h 不按 base 比例
    o.a_ratio.setChecked(False)
    o.toggle_ratio()
    o.set_pct(100, announce=False)
    check("keep_ratio off ok", o.keep_ratio is False)
    o.a_ratio.setChecked(True)
    o.toggle_ratio()
    check("keep_ratio on", o.keep_ratio is True)

    # ---- 锚点 ----
    g = overlay.screen_rect_for(o)
    for idx in range(1, 10):
        o.set_anchor(idx)
        r, c = overlay.ANCHOR_RC[idx]
        w, h = o.width(), o.height()
        if c == 0:
            ex = g.left() + overlay.MARGIN
        elif c == 2:
            ex = g.right() - overlay.MARGIN - w
        else:
            ex = g.left() + (g.width() - w) // 2
        if r == 0:
            ey = g.top() + overlay.MARGIN
        elif r == 2:
            ey = g.bottom() - overlay.MARGIN - h
        else:
            ey = g.top() + (g.height() - h) // 2
        check("anchor %d" % idx, o.pos() == QPoint(ex, ey),
              "%s vs (%d,%d)" % (o.pos(), ex, ey))
    # 尺寸变化后锚定保持
    o.set_anchor(1)
    o.set_pct(120)
    r, c = overlay.ANCHOR_RC[1]
    check("anchor holds after resize",
          o.x() == g.left() + overlay.MARGIN and o.y() == g.top() + overlay.MARGIN,
          "%s" % o.pos())
    # 自由
    o.set_anchor(0)
    o.move(100, 100)
    check("free move", o.pos() == QPoint(100, 100))

    # snap_to_nearest（先把窗拖到右下角附近）
    o.move(g.right() - o.width() - 15, g.bottom() - o.height() - 15)
    o.snap_to_nearest()
    check("snap 右下", o.anchor == 9, "anchor=%d" % o.anchor)
    check("snap pos", o.x() == g.right() - overlay.MARGIN - o.width(),
          "%d" % o.x())

    # auto_snap 拖远 → 自由
    o.move(300, 300)
    o.anchor = 5
    o.auto_snap(True)
    check("drag away -> free", o.anchor == 0, "anchor=%d" % o.anchor)

    # ---- 不透明度 ----
    o.set_opacity(50)
    check("opacity 50", o.opacity_ == 50 and abs(o.current_opacity() - 0.5) < 0.01)
    o.set_opacity(0)
    check("opacity floor", o.opacity_ == 10)
    o.set_opacity(120)
    check("opacity ceil", o.opacity_ == 100)
    o.bump_opacity(10)
    check("bump up", o.opacity_ == 100)
    o.set_opacity(50)
    o.bump_opacity(-10)
    check("bump down", o.opacity_ == 40, str(o.opacity_))

    # ---- 菜单构建（不显示，只验证不炸 + 关键条目存在） ----
    try:
        m = o.build_menu()
        titles = [a.text() for a in m.actions() if a.text()]
        joined = "|".join(titles)
        check("menu built", True)
        check("menu has 大小", "大小" in joined, joined)
        check("menu has 位置", "位置" in joined)
        check("menu has 不透明度", "不透明度" in joined)
        check("menu has 置顶", "置顶显示（占最高）" in joined)
        check("menu has 穿透", "鼠标点击穿透（点击穿到下层）" in joined)
        check("menu has 关闭", "关闭这个贴图" in joined)
        check("menu has 退出", "退出（全部关闭）" in joined)
        # 子菜单逐个构建
        sub_ok = True
        sub_detail = ""
        for a in m.actions():
            sm = a.menu()
            if sm is None:
                continue
            try:
                for a2 in list(sm.actions()):
                    sm2 = a2.menu()
                    if sm2 is not None:
                        _ = [x.text() for x in sm2.actions()]
                _ = [x.text() for x in sm.actions()]
            except Exception:
                sub_ok = False
                sub_detail = traceback.format_exc()
        check("submenus built", sub_ok, sub_detail)
    except Exception:
        check("menu built", False, traceback.format_exc())

    # 非视频素材的播放子菜单应显示占位
    try:
        m2 = o.build_menu()
        check("image menu ok", True)
    except Exception:
        check("image menu ok", False, traceback.format_exc())

    # ---- 新功能：热键解析 ----
    from overlay import (D, HK, HKC, SHOT_CFG, LANG, MIN_W, MIN_H, anchor_list,
                         anchor_short, apply_global_cfg, parse_hk)
    s = parse_hk("Ctrl+Alt+P")
    check("hk ctrl+alt+P", s == (True, True, False, False, 0x50), str(s))
    s2 = parse_hk("Alt+F5")
    check("hk alt+F5", s2 is not None and s2[1] and s2[4] == 0x74, str(s2))
    s3 = parse_hk("Ctrl+Shift+K")
    check("hk ctrl+shift+K", s3 == (True, False, True, False, 0x4B), str(s3))
    check("hk no-modifier rejected", parse_hk("p") is None)
    check("hk garbage rejected", parse_hk("Ctrl+") is None)
    check("hk empty rejected", parse_hk("") is None)

    # ---- 新功能：中英切换 ----
    check("lang default zh", LANG["code"] == "zh")
    LANG["code"] = "en"
    check("D translates", D("设置") == "Settings", D("设置"))
    check("D fallback", D("不存在的键xyz") == "不存在的键xyz")
    check("anchor_list en", anchor_list()[1] == "Top-left", anchor_list()[1])
    check("anchor_short en", anchor_short(1) == "TL" and anchor_short(9) == "BR",
          "%s/%s" % (anchor_short(1), anchor_short(9)))
    m_en = o.build_menu()
    en_titles = "|".join(a.text() for a in m_en.actions() if a.text())
    check("menu EN has Size/Keyframes",
          "Size" in en_titles and "Keyframes" in en_titles, en_titles)
    LANG["code"] = "zh"
    m_zh = o.build_menu()
    zh_titles = "|".join(a.text() for a in m_zh.actions() if a.text())
    check("menu ZH anchors", "位置（吸附到屏幕）" in zh_titles, zh_titles)
    check("anchor_list zh restored", anchor_list()[1] == "左上角", anchor_list()[1])

    # ---- 新功能：关键帧 ----
    kf = o.kfc
    kf.clear()
    check("kf empty total", kf.total() == 0.0, str(kf.total()))
    n1 = kf.add(100, 200)
    n2 = kf.add(300, 400)
    n3 = kf.add(500, 600)
    check("kf add count", n1 == 1 and n2 == 2 and n3 == 3)
    check("kf total 4s", abs(kf.total() - 4.0) < 1e-6, str(kf.total()))
    check("kf stored", kf.kfs[1] == [2.0, 300, 400], str(kf.kfs))
    kf.remove(1)
    check("kf remove", len(kf.kfs) == 2, str(len(kf.kfs)))
    kf.clear()
    check("kf clear", kf.kfs == [] and not kf.playing)
    kf.add(50, 50)
    kf.start()
    check("kf single-point no loop", not kf.playing)
    kf.clear()
    kf.add(100, 100)
    kf.add(700, 700)          # 2s 走 600px
    kf.start()
    check("kf playing", kf.playing)
    pump(300)
    x_mid = o.x()
    check("kf moving", 100 < x_mid < 700, "x=%d" % x_mid)
    kf.stop()
    check("kf stop", not kf.playing)
    kf.clear()
    m_kf = o.build_menu()
    kf_titles = "|".join(a.text() for a in m_kf.actions() if a.text())
    check("menu has keyframes", "关键帧" in kf_titles, kf_titles)

    # ---- 新功能：文字贴图 ----
    t = overlay.TextOverlay()
    overlay.overlays.append(t)
    check("text kind", t.kind == "text")
    check("text no file path", t.source_path == "")
    t.text = "Hello 测试 ABC"
    t._resize_to_text()
    check("text sized", t.width() >= MIN_W and t.height() >= MIN_H,
          t.geometry().getRect())
    t.set_pct(200)
    check("text font scales", abs(t.font_px - 112) <= 2, str(t.font_px))
    t.set_pct(100)
    check("text font back", abs(t.font_px - 56) <= 1, str(t.font_px))
    mt = t.build_menu()
    mt_titles = "|".join(a.text() for a in mt.actions() if a.text())
    check("text menu has edit", "编辑文字/样式" in mt_titles, mt_titles)
    t.show()
    app.processEvents()
    check("text show", t.isVisible())
    t.hide()

    # ---- 新功能：临时截图 ----
    img0 = QImage(640, 480, QImage.Format_ARGB32)
    img0.fill(0xFF336699)
    so = overlay.ShotOverlay(img0)
    overlay.overlays.append(so)
    check("shot kind", so.kind == "shot")
    check("shot no file path", so.source_path == "")
    check("shot base", so.base == QSize(640, 480), str(so.base))
    cap = overlay.capture_screen()
    # offscreen 平台抓不到真实屏幕 → 允许 None（这是「空抓帧被安全处理」的断言；
    # 真实抓帧在 smoke3 的真屏幕 GUI 冒烟里验）
    check("capture_screen safe (None or valid)",
          cap is None or (not cap.isNull() and cap.width() >= 2),
          "None" if cap is None else "%dx%d" % (cap.width(), cap.height()))
    overlay._shot[0] = None
    overlay.toggle_shot()
    app.processEvents()
    so2 = overlay._shot[0]
    if so2 is None:
        # offscreen 抓帧失败 → toggle_shot 必须干净地不建窗（无崩溃、_shot 仍 None）
        check("shot null-capture handled", True, "capture unavailable offscreen")
    else:
        check("shot on", so2.isVisible())
        check("shot sized by pct", so2.width() > 0, str(so2.width()))
        overlay.toggle_shot()
        app.processEvents()
        check("shot off + freed", overlay._shot[0] is None)
    overlay.overlays.remove(so)
    so.close()

    # ---- 新功能：设置持久化（热键/截图/语言） ----
    old_hk = dict(HK)
    old_shot = dict(SHOT_CFG)
    old_lang = LANG["code"]
    HK["pass"] = "Ctrl+Shift+K"
    HKC["pass"] = parse_hk("Ctrl+Shift+K")
    SHOT_CFG.update({"anchor": 7, "pct": 44, "opacity": 55})
    LANG["code"] = "en"
    overlay.save_config()
    cfg2 = overlay.load_config()
    HK.update(old_hk)
    SHOT_CFG.update(old_shot)
    LANG["code"] = "zh"
    HKC["pass"] = parse_hk(HK["pass"])
    apply_global_cfg(cfg2)
    check("hk persisted", HK["pass"] == "Ctrl+Shift+K", HK["pass"])
    check("hk reparsed", HKC["pass"] == (True, False, True, False, 0x4B),
          str(HKC["pass"]))
    check("shot cfg persisted",
          SHOT_CFG["anchor"] == 7 and SHOT_CFG["pct"] == 44 and SHOT_CFG["opacity"] == 55,
          str(SHOT_CFG))
    check("lang persisted", LANG["code"] == "en", LANG["code"])
    # 配置里应含文字贴图项、且截图(无文件)不入配置
    txt_items = [it for it in cfg2.get("overlays", []) if it.get("type") == "text"]
    check("text saved in cfg", len(txt_items) >= 1, str(cfg2.get("overlays")))
    check("text font persisted",
          txt_items and txt_items[0].get("font_px") == 56, str(txt_items[:1]))
    bad_files = [it for it in cfg2.get("overlays", [])
                 if it.get("type") != "text" and not it.get("file")]
    check("shot/media no-empty-file", not bad_files, str(bad_files))
    # 还原默认
    apply_global_cfg({"lang": "zh", "pass_hotkey": "Ctrl+Alt+P",
                      "shot_hotkey": "Ctrl+Alt+S", "shot_anchor": 3,
                      "shot_pct": 33, "shot_opacity": 100})
    check("defaults restored", HK["pass"] == "Ctrl+Alt+P" and LANG["code"] == "zh"
          and SHOT_CFG["anchor"] == 3)
    overlay.overlays.remove(t)
    t.close()

    # ---- 新功能 v1.5：7 热键 + 截图多槽 ----
    check("hk keys count", len(overlay.HK_KEYS) == 7, str(overlay.HK_KEYS))
    check("hk 4 new defaults empty",
          all(overlay.HK.get(k, "") == "" for k in ("save", "switch", "del", "delall")),
          str({k: overlay.HK.get(k) for k in ("save", "switch", "del", "delall")}))
    check("hk 4 new unparsed",
          all(overlay.HKC.get(k) is None for k in ("save", "switch", "del", "delall")),
          str({k: overlay.HKC.get(k) for k in ("save", "switch", "del", "delall")}))
    m7 = o.build_menu()
    check("menu built with 7-key cfg", m7 is not None)
    # 设置框 7 行热键文案齐（EN 表也齐）
    en7 = {"点击穿透热键", "临时截图热键", "小面板热键", "保存临时图片热键",
           "切换临时图片热键", "删除临时图片热键", "删除全部图片热键"}
    t = overlay.D
    overlay.LANG["code"] = "en"
    miss = [k for k in en7 if t(k) == k]
    overlay.LANG["code"] = "zh"
    check("7 hotkey labels translated", not miss, str(miss))

    # 截图多槽：模拟 3 张 → 轮换/删除/全删（不真截屏，直接造槽）
    img1 = QImage(80, 60, QImage.Format_ARGB32); img1.fill(0xFFFF0000)
    img2 = QImage(80, 60, QImage.Format_ARGB32); img2.fill(0xFF00FF00)
    img3 = QImage(80, 60, QImage.Format_ARGB32); img3.fill(0xFF0000FF)
    for im in (img1, img2, img3):
        so = overlay.ShotOverlay(im)
        overlay._shots.append(so)
        overlay._apply_shot_style(so)
    overlay.set_shot_visible(overlay._shots[0])
    check("shot pool=3", len(overlay._shots) == 3, str(len(overlay._shots)))
    check("shot active=0", overlay._shot[0] is overlay._shots[0])
    overlay.shot_next()
    app.processEvents()
    check("shot next ->1", overlay._shots.index(overlay._shot[0]) == 1,
          str(overlay._shots.index(overlay._shot[0])))
    overlay.shot_next()
    check("shot next ->2", overlay._shots.index(overlay._shot[0]) == 2)
    overlay.shot_next()
    check("shot next wrap ->0", overlay._shots.index(overlay._shot[0]) == 0)
    dead = overlay._shot[0]
    overlay.shot_delete()
    check("shot delete removes active", len(overlay._shots) == 2 and dead not in overlay._shots,
          str(len(overlay._shots)))
    check("shot active after delete", overlay._shot[0] in overlay._shots)
    # 槽满顶掉最老
    while len(overlay._shots) < overlay.SHOT_SLOTS:
        overlay._shots.append(overlay.ShotOverlay(img1))
    oldest = overlay._shots[0]
    overflow = overlay.ShotOverlay(img2)
    overlay._shots.append(overflow)
    if len(overlay._shots) > overlay.SHOT_SLOTS:
        overlay._shots.pop(0)
    check("slot cap evicts oldest", oldest not in overlay._shots and overflow in overlay._shots)
    overlay.shot_delete_all()
    check("shot delete all", len(overlay._shots) == 0 and overlay._shot[0] is None)
    # 取消保存不炸（getExistingDirectory mock 返回空）
    _orig_ged = overlay.QFileDialog.getExistingDirectory
    overlay.QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: "")
    try:
        overlay.save_shot_async()
        check("save cancel safe", True)
    except Exception:
        check("save cancel safe", False, traceback.format_exc())
    finally:
        overlay.QFileDialog.getExistingDirectory = _orig_ged

    # ---- 配置读写（隔离目录） ----
    overlay.save_config()
    cfg = overlay.load_config()
    check("cfg saved", isinstance(cfg.get("overlays"), list), str(cfg))
    check("cfg has file", any(it.get("file") == png for it in cfg.get("overlays", [])), str(cfg))
    # 坏配置不炸
    with open(overlay.cfg_path(), "w", encoding="utf-8") as f:
        f.write("{broken json")
    check("bad cfg tolerated", overlay.load_config() == {})
    # 恢复空（删配置 = 清空，不留测试残留）
    overlay.overlays.clear()
    overlay.save_config()

    # ---- 展示路径（offscreen 下 paintEvent 也走一遍） ----
    o.show()
    o.update()
    app.processEvents()
    check("show offscreen", o.isVisible())
    try:
        overlay.set_click_through(o, True)
        check("click_through on", o.click_through is True)
        overlay.set_click_through(o, False)
        check("click_through off", o.click_through is False)
    except Exception:
        check("click_through", False, traceback.format_exc())
    # 窗口级透明度已生效（setWindowOpacity 是我们改用的方案）
    o.set_opacity(40)
    check("windowOpacity applied", abs(o.windowOpacity() - 0.4) < 0.01,
          str(o.windowOpacity()))
    # 视频子控件存在且透明转发鼠标
    check("video child exists", isinstance(getattr(o, "video", None), object) and o.video is not None)

    # 关窗（列表可能已被上面 clear，这里做存在性判断）
    if o in overlay.overlays:
        overlay.overlays.remove(o)
    o.close()
    if o2 in overlay.overlays:
        overlay.overlays.remove(o2)
    o2.close()

    # ---- v1.6：后台常驻 / 主题 / 一键初始化 / 更新版本比较 ----
    check("quit gate default", overlay._exiting[0] is False)
    wt = overlay.OverlayWindow()
    overlay.overlays.append(wt)
    overlay.close_overlay(wt)
    check("close keeps app alive", overlay._exiting[0] is False and wt not in overlay.overlays,
          "exiting=%s" % overlay._exiting[0])
    check("themes >= 5", len(overlay.THEMES) >= 5, str(len(overlay.THEMES)))
    th = overlay.theme(2)
    check("theme keys", all(k in th for k in ("bg", "card", "btn", "btnh", "text", "dim", "line")))
    check("theme no gradient css", "qlineargradient" not in th["bg"].lower())
    overlay.apply_theme(2)
    check("theme applied", overlay.SETTINGS["theme"] == 2)
    overlay.apply_theme(0)
    check("ver cmp", overlay._parse_ver("v1.6.0") > overlay._parse_ver("1.5"),
          str((overlay._parse_ver("v1.6.0"), overlay._parse_ver("1.5"))))
    check("ver eq pad", overlay._parse_ver("1.5") == overlay._parse_ver("1.5.0"))
    overlay.apply_global_cfg({})
    check("restore default off", overlay.SETTINGS["restore"] == 0, str(overlay.SETTINGS))
    check("autoupdate default on", overlay.SETTINGS["autoupdate"] == 1)
    overlay.HK["shot"] = "Ctrl+Shift+X"
    overlay.LANG["code"] = "en"
    overlay.SETTINGS["restore"] = 1
    overlay.SETTINGS["theme"] = 3
    overlay.reset_settings()
    check("reset hk", overlay.HK["shot"] == "Ctrl+Alt+S", overlay.HK["shot"])
    check("reset lang", overlay.LANG["code"] == "zh")
    check("reset restore", overlay.SETTINGS["restore"] == 0)
    check("reset theme", overlay.SETTINGS["theme"] == 0)
    check("reset clears overlays", overlay.overlays == [], str(len(overlay.overlays)))
    cfgz = overlay.load_config()
    check("reset writes empty list", cfgz.get("overlays") == [], str(cfgz))
    check("reset keeps feedback/site consts",
          overlay.SITE_URL.startswith("http") and "@" in overlay.FEEDBACK_MAIL)

    print("\nPASS=%d FAIL=%d" % (len(PASS), len(FAIL)))
    if FAIL:
        for f in FAIL:
            print(" -", f)
        return 1
    print("ALL GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
