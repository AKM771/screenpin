# 屏幕贴图 ScreenPin

把图片、视频、GIF、文字钉在 Windows 屏幕上：随意改大小、吸附九宫格位置、半透明、永远置顶，右键改一切。解码自带 FFmpeg，不依赖系统解码器。

[下载](https://github.com/AKM771/screenpin/releases) · 官网 https://akm771.github.io/screenpin/ · 反馈：jjonju361999@qq.com

## 有什么

- 图片 / 视频（mp4、mkv、webm…）/ GIF / 文字贴图，拖放即贴
- 大小：拖角、滚轮 10% 一档、菜单 50%~300% 固定档
- 位置：左上角/上方/右上角/左边/居中/右边/左下角/下方/右下角，拖到边自动吸
- 半透明 10%~100%，置顶每 4 秒自动抢回
- 关键帧动画（打点平移）、临时截图（纯内存 16 槽，热键切换/删除/保存）
- 7 个热键全部可自定义、中英双语、小面板、后台常驻
- 主题五套 + 一键初始化；启动不复读上次贴图

## 构建

```
pip install PyQt5 av pyinstaller
cmd /c build_exe.bat        # 产物 dist\screenpin.exe（含 FFmpeg 解码库）
```

- `overlay.py` 主程序 · `av_player.py` 视频后端 · `installer.cs` 安装程序（csc 编译）
- 测试：`python test_overlay.py`（134 项离屏断言）· `smoke_audio.py`（音频 10 项）

## 环境

Windows 10/11 · Python 3.11 · PyQt5 5.15 · PyAV 18（自带 FFmpeg，可 `pip uninstall av` 卸掉）

## 许可

GPL-3.0（见 LICENSE）。图标素材 [Material Design Icons](https://github.com/Templarian/MaterialDesign-SVG)（Apache-2.0）。依赖 PyQt5（GPL-3/商业双许可）、PyAV（BSD-3）、PyInstaller（GPL-3+bootloader 例外）——逐个点开前自行核对各项目当前 LICENSE。
