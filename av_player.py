# -*- coding: utf-8 -*-
"""PyAV 视频回退引擎 —— 系统解码器缺失时的兜底后端（可选依赖 av）。

架构：解码线程(demux→decode→rgb24/PCM) + wallclock 主时钟 + QAudioOutput pull 从动。
上层 AvPlayer.load() 失败即回落 Qt WMF；本机(msmpegvdec 被删)全靠本引擎。
API 实测于 av 18.1.0 / PyQt5 5.15.11(Qt5 无 push write，仅 pull)。
"""
import threading
import time
from collections import deque

from PyQt5.QtCore import QIODevice, QObject, QSize, pyqtSignal
from PyQt5.QtGui import QImage
from PyQt5.QtMultimedia import QAudioDeviceInfo, QAudioFormat, QAudioOutput

try:
    import av as _av
    HAVE_AV = True
except Exception:
    _av = None
    HAVE_AV = False


class _AudioPull(QIODevice):
    """Qt pull 回调（音频线程调用），从引擎 PCM 队列取字节。"""
    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.total = 0

    def readData(self, n):
        b, c = self.engine._read_pcm(int(n))
        self.total += c
        return b

    def writeData(self, data):
        return len(data) if data else 0


class AvPlayer(QObject):
    frame_ready = pyqtSignal()   # 已有新可显示帧
    ended = pyqtSignal()         # 非循环播到结尾
    failed = pyqtSignal(str)     # 运行期致命错误

    def __init__(self, parent=None):
        super().__init__(parent)
        if not HAVE_AV:
            raise RuntimeError("av 不可用")
        self._lk = threading.Lock()     # 保护 _frames / _pcm / _pcmbuf
        self._frames = []               # [(pts_sec, QImage)] 已解码待显示
        self._pcm = deque()             # [bytes] PCM 交错 s16
        self._pcmbuf = b""              # 部分消费的尾块
        self._stop = threading.Event()
        self._thr = None
        self._cont = None               # av 容器（线程独占）
        self._vstream = None
        self._astream = None
        self._dur = 0.0
        self._size = QSize(0, 0)
        self._sink = None               # QAudioOutput
        self._pull = None
        self._bps = 0                   # 字节率
        self._has_audio = False
        self._playing = False
        self._t0 = 0.0                  # wallclock 基准
        self._frozen = 0.0              # 暂停时的位置
        self.loop = True
        self._ended_flag = False
        self._vol = 0.7                 # 0~1
        self._muted = False
        self._eof_spins = 0             # 连续 EOF 计数（防 seek 失败死循环）
        self.underruns = 0              # PCM 欠载补零次数（音频质量指标）

    # ---------- 探测（同步，GUI 线程） ----------

    def probe(self, path):
        """打开容器读元数据。失败抛异常；成功返回 (w, h, dur_sec)。"""
        cont = _av.open(path)
        try:
            if not cont.streams.video:
                raise RuntimeError("无视频轨")
            vs = cont.streams.video[0]
            cc = vs.codec_context
            w, h = int(cc.width), int(cc.height)
            if w <= 0 or h <= 0:
                raise RuntimeError("无尺寸")
            dur = float(cont.duration) / 1000000.0 if cont.duration else 0.0
            st = None
            if cont.streams.audio:
                st = cont.streams.audio[0]
            self._cont = cont
            self._vstream = vs
            self._astream = st
            self._dur = dur
            self._size = QSize(w, h)
            return w, h, dur
        except Exception:
            try:
                cont.close()
            except Exception:
                pass
            raise

    # ---------- 播放控制 ----------

    def start(self):
        """起解码线程 + 音频 sink（若有音轨），时钟从 0 起。"""
        self._t0 = time.perf_counter()
        self._frozen = 0.0
        self._playing = True
        self._ended_flag = False
        self._stop.clear()
        if self._astream is not None:
            self._setup_audio()
        self._thr = threading.Thread(target=self._loop, daemon=True,
                                     name="avplayer-decode")
        self._thr.start()

    def _setup_audio(self):
        """音频链：文件音轨 → AudioResampler(s16/声道/采样率) → pull sink。"""
        try:
            dev = QAudioDeviceInfo.defaultOutputDevice()
            if dev.isNull():
                self._has_audio = False
                return
            fmt = QAudioFormat()
            fmt.setSampleRate(44100)
            fmt.setChannelCount(2)
            fmt.setSampleSize(16)
            fmt.setCodec("audio/pcm")
            fmt.setByteOrder(QAudioFormat.LittleEndian)
            fmt.setSampleType(QAudioFormat.SignedInt)
            if not dev.isFormatSupported(fmt):
                fmt = dev.nearestFormat(fmt)
            if fmt.sampleSize() != 16 or fmt.codec() not in ("audio/pcm", ""):
                self._has_audio = False
                return
            layout = "mono" if fmt.channelCount() == 1 else "stereo"
            self._resamp = _av.AudioResampler(format="s16", layout=layout,
                                              rate=int(fmt.sampleRate()))
            self._bps = int(fmt.sampleRate()) * int(fmt.channelCount()) * 2
            self._sink = QAudioOutput(dev, fmt)
            self._pull = _AudioPull(self, self._sink)
            self._pull.open(QIODevice.ReadOnly)
            self._sink.start(self._pull)
            self._has_audio = True
            self._apply_vol()
        except Exception:
            self._has_audio = False
            self._sink = None
            self._pull = None

    def position(self):
        if self._playing:
            return max(0.0, time.perf_counter() - self._t0)
        return self._frozen

    def duration(self):
        return self._dur

    def size(self):
        return QSize(self._size)

    def is_playing(self):
        return self._playing

    def pause(self):
        if not self._playing:
            return
        self._frozen = self.position()
        self._playing = False
        try:
            if self._sink is not None:
                self._sink.suspend()
        except Exception:
            pass

    def resume(self):
        if self._playing:
            return
        self._t0 = time.perf_counter() - self._frozen
        self._playing = True
        self._ended_flag = False
        try:
            if self._sink is not None:
                self._sink.resume()
        except Exception:
            pass

    def toggle(self):
        if self._playing:
            self.pause()
        else:
            self.resume()

    def set_volume(self, pct):
        self._vol = max(0.0, min(1.0, pct / 100.0))
        self._apply_vol()

    def set_muted(self, on):
        self._muted = bool(on)
        self._apply_vol()

    def _apply_vol(self):
        try:
            if self._sink is not None:
                self._sink.setVolume(0.0 if self._muted else self._vol)
        except Exception:
            pass

    def snapshot(self, pos):
        """返回 pts<=pos 的最新帧（并丢掉过期帧）。无帧返回 None。"""
        with self._lk:
            if not self._frames:
                return None
            # 丢掉明显过期的帧（落后 1.5s 以上）
            cut = 0
            for i, (pts, _im) in enumerate(self._frames):
                if pts < pos - 1.5:
                    cut = i + 1
                else:
                    break
            if cut:
                del self._frames[:cut]
            pick = None
            for pts, im in self._frames:
                if pts <= pos + 0.02:
                    pick = im
                else:
                    break
            return pick

    def stop(self):
        self._playing = False
        self._stop.set()
        try:
            if self._sink is not None:
                self._sink.stop()
        except Exception:
            pass
        t = self._thr
        if t is not None and t.is_alive():
            t.join(timeout=1.5)
        self._thr = None
        try:
            if self._cont is not None:
                self._cont.close()
        except Exception:
            pass
        self._cont = None
        with self._lk:
            self._frames.clear()
            self._pcm.clear()
            self._pcmbuf = b""

    # ---------- PCM 出口（Qt 音频线程调用） ----------

    def _read_pcm(self, n):
        if n <= 0:
            return b"", 0
        with self._lk:
            buf = self._pcmbuf
            while len(buf) < n and self._pcm:
                buf += self._pcm.popleft()
            if len(buf) >= n:
                out = buf[:n]
                self._pcmbuf = buf[n:]
            else:
                # 欠载补零：听感=咔哒/炸麦，计数供冒烟断言（必须≈0）
                self.underruns += 1
                pad = n - len(buf)
                # 按 4 字节(2ch×16bit)帧边界对齐补零，错位叠加会放大毛刺
                pad -= pad % 4
                out = buf + b"\x00" * pad
                if len(out) < n:
                    out += b"\x00" * (n - len(out))
                self._pcmbuf = b""
        return out, n

    # ---------- 解码线程 ----------

    def _loop(self):
        cont = self._cont
        vs = self._vstream
        ast = self._astream
        v_idx = vs.index
        a_idx = ast.index if ast is not None else -1
        try:
            gen = None  # demux 生成器（绝不能 list()：会把整部影片的包吃进内存）
            while not self._stop.is_set():
                # 暂停=冻结解码（否则 PCM/帧无界增长：背压都挂在 _playing 上，
                # 暂停时线程会全速超前解码 → 长暂停内存泄漏）
                if not self._playing:
                    if self._stop.wait(0.1):
                        break
                    continue
                # 背压：PCM 超前 2 秒 → 等音频消费；帧堆 >90 → 等画面消费
                if self._has_audio and self._bps:
                    pos = self.position()
                    with self._lk:
                        queued = sum(len(x) for x in self._pcm) + len(self._pcmbuf)
                    if queued > (pos + 2.0) * self._bps:
                        if self._stop.wait(0.05):
                            break
                        continue
                if gen is None:
                    gen = cont.demux()
                # 画面背压：帧堆过厚时暂时跳过视频包（绝不睡眠——睡眠会连带
                # 断掉音频供给，声卡一欠载补零就是周期性爆音），音频包照常处理
                with self._lk:
                    video_backlog = len(self._frames)
                skip_video = video_backlog > 90
                try:
                    pkt = next(gen)
                except StopIteration:
                    gen = None
                    self._on_eof()
                    if self._eof_spins > 3:
                        try:
                            self.failed.emit("循环解码异常（文件可能损坏）")
                        except Exception:
                            pass
                        break
                    if not self.loop or self._stop.is_set():
                        break
                    continue
                except Exception:
                    gen = None
                    self._on_eof()
                    if self._eof_spins > 3 or not self.loop or self._stop.is_set():
                        break
                    continue
                if self._stop.is_set():
                    return
                try:
                    if pkt.stream.index == v_idx:
                        if skip_video:
                            self._eof_spins = 0   # 画面满了先不出帧，音频继续
                        else:
                            for fr in vs.decode(pkt):
                                im = self._frame_to_qimage(fr)
                                if im is None:
                                    continue
                                pts = 0.0
                                try:
                                    if fr.pts is not None and fr.time_base:
                                        pts = float(fr.pts * fr.time_base)
                                except Exception:
                                    pts = 0.0
                                with self._lk:
                                    self._frames.append((pts, im))
                                    if len(self._frames) > 120:
                                        del self._frames[:40]
                                self._eof_spins = 0
                                self.frame_ready.emit()
                    elif pkt.stream.index == a_idx and self._astream is not None:
                        # 只在有 sink 时供音频（纯视频/无设备则跳过省 CPU）
                        if self._sink is not None:
                            for af in ast.decode(pkt):
                                outs = self._resamp.resample(af)
                                seq = outs if isinstance(outs, (list, tuple)) else [outs]
                                for o in seq:
                                    if o is None:
                                        continue
                                    try:
                                        # 只取有效样本字节：bytes(plane) 含对齐填充，
                                        # 每块尾巴混进 ~1.45ms 零段 = 周期性断续(糊/炸麦)
                                        nb = int(getattr(o, "samples", 0) or 0)
                                        fmt = o.format
                                        bpc = int(getattr(fmt, "bytes", 2) or 2)
                                        ch = int(getattr(fmt, "channels", 0) or 0)
                                        if ch <= 0:
                                            ch = int(getattr(o.layout, "nb_channels", 0) or 0)
                                        if ch <= 0:
                                            cs = getattr(o.layout, "channels", None)
                                            ch = len(cs) if cs else 2
                                        need = nb * bpc * ch if nb > 0 else 0
                                        raw = bytes(o.planes[0])
                                        if need and len(raw) > need:
                                            raw = raw[:need]
                                        data = raw
                                    except Exception:
                                        continue
                                    if data:
                                        with self._lk:
                                            self._pcm.append(data)
                except Exception:
                    continue
        except Exception as e:
            if not self._stop.is_set():
                try:
                    self.failed.emit(str(e))
                except Exception:
                    pass
        finally:
            try:
                if self._cont is not None:
                    self._cont.close()
            except Exception:
                pass

    def _on_eof(self):
        self._eof_spins += 1
        if self.loop:
            # 循环：回 0 + 清队列 + 时钟归零（音画一起回起点）
            try:
                self._cont.seek(0, stream=self._vstream)
            except Exception:
                pass
            with self._lk:
                self._frames.clear()
                self._pcm.clear()
                self._pcmbuf = b""
            self._t0 = time.perf_counter()
            self._frozen = 0.0
        else:
            self._frozen = self._dur
            self._playing = False
            try:
                if self._sink is not None:
                    self._sink.suspend()
            except Exception:
                pass
            if not self._ended_flag:
                self._ended_flag = True
                try:
                    self.ended.emit()
                except Exception:
                    pass

    @staticmethod
    def _frame_to_qimage(fr):
        try:
            arr = fr.to_ndarray(format="rgb24")
            h, w = arr.shape[0], arr.shape[1]
            img = QImage(arr.data, w, h, int(arr.strides[0]),
                         QImage.Format_RGB888)
            return img.copy()   # 必须 copy：arr 随帧释放
        except Exception:
            return None
