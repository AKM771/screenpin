# -*- coding: utf-8 -*-
"""把 pin.svg（Google Material Design Icons，Apache-2.0，Templarian/MaterialDesign-SVG）
渲染成 pin.ico（多尺寸 PNG 内嵌）。运行：python mkicon.py"""
import os
import struct
import sys

from PyQt5.QtCore import QBuffer, QIODevice, QRectF
from PyQt5.QtGui import QGuiApplication, QImage, QPainter
from PyQt5.QtSvg import QSvgRenderer

HERE = os.path.dirname(os.path.abspath(__file__))
SIZES = [16, 24, 32, 48, 64, 128, 256]


def render(rend, s):
    img = QImage(s, s, QImage.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    rend.render(p, QRectF(0, 0, s, s))
    p.end()
    return img


def to_png_blob(img):
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def main():
    src = os.path.join(HERE, "pin.svg")
    out = os.path.join(HERE, "pin.ico")
    if not os.path.isfile(src):
        print("missing:", src)
        return 1
    app = QGuiApplication([])
    with open(src, "rb") as f:
        data = f.read()
    rend = QSvgRenderer(data)
    if not rend.isValid():
        print("svg invalid")
        return 1
    blobs = []
    for s in SIZES:
        blobs.append(to_png_blob(render(rend, s)))
    # ICO 容器：目录项 + PNG 数据（Vista+ 支持 PNG 压缩条目）
    header = struct.pack("<HHH", 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    entries = b""
    body = b""
    for s, b in zip(SIZES, blobs):
        w = 0 if s >= 256 else s
        h = 0 if s >= 256 else s
        entries += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(b), offset)
        offset += len(b)
        body += b
    with open(out, "wb") as f:
        f.write(header + entries + body)
    print("wrote", out, os.path.getsize(out), "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
