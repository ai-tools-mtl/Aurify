# -*- coding: utf-8 -*-
"""专利黑白线框图直绘库（PIL 实现）——patent-figure-design 的「代码直绘通路」。

适用：drawio 渲染环境不可用时，流程图/架构图的等效绘制；成品与 drawio 图同形态、
同纪律、同验收门（SKILL.md「代码直绘通路」一节）。源自内部分享的 patent-wireframe
技能（2026-11 吸收进本技能，字体口径对齐 cnipa-monochrome：宋体优先）。

风格规范（专利附图标准）：
- 纯黑白：白底、黑实线（默认宽 3px）、宋体字；禁止任何彩色/灰色/阴影/图标/圆角
- 直角矩形框；连线为曼哈顿折线（水平+垂直），末端实心三角箭头（方向由末段自动定向）
- 虚线仅用于"反馈/回传/可选路径"等非主流程语义
- 框内文字：左对齐（左边距 12px）、按框宽自动折行、垂直居中；折行后行数放不下自动缩字号
  （下限 15px，缩字号是兜底不是设计手段，框高要按内容画够）
- 禁止绕过 box()/text_block() 用 d.text 手工往框里塞文本——排版引擎是防文字溢出的结构保证

用法：
    from wireframe_lib import begin, box, container, line, label, save
    img, d = begin(1300, 930)
    box(d, 300, 290, 900, 400, ["S1 数据接入", "接入模块201"], 22)
    container(d, 300, 40, 900, 250, "多源输入数据", 26)
    line(d, [(600, 250), (600, 290)])                       # 实线箭头
    line(d, [(300, 590), (40, 590), (40, 495), (300, 495)], dashed=True)  # 虚线反馈
    label(d, (55, 470), "处理参数反馈", 17, "lm")
    save(img, "out.png")
"""
import math
import os

from PIL import Image, ImageDraw, ImageFont

# ---- 字体：与 cnipa-monochrome 同口径，宋体优先；找不到时在候选中补本机路径 ----
FONT_CANDIDATES = [
    "C:/Windows/Fonts/simsun.ttc",                    # Windows 宋体（与 SVG 通路同族）
    "C:/Windows/Fonts/simhei.ttf",                    # Windows 黑体（兜底）
    "/System/Library/Fonts/Supplemental/Songti.ttc",  # macOS 宋体
    "/usr/share/fonts/truetype/arphic/uming.ttc",     # Linux AR PL UMing（明体）
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",   # Linux 文泉驿（兜底）
]
FONT_PATH = next((p for p in FONT_CANDIDATES if os.path.exists(p)), None)
if FONT_PATH is None:
    raise RuntimeError("未找到中文字体，请在 FONT_CANDIDATES 中补充本机字体路径")

LW = 3          # 线宽
PAD = 12        # 框内文字左右边距
VGAP = 4        # 文字块顶部预留

_font_cache = {}
def F(size):
    if size not in _font_cache:
        _font_cache[size] = ImageFont.truetype(FONT_PATH, size)
    return _font_cache[size]


# ---- 折行与排版引擎 ----
def _can_break_before(ch):
    """该字符前可断行：ASCII 连续串（字母/数字/常见符号）视为整体，中文任意可断"""
    return not (ch.isascii() and (ch.isalnum() or ch in ".-_()/"))


def wrap_text(d, text, font, max_w):
    """按像素宽度折行；优先在空格/箭头/分隔符处断，中文逐字断。保留显式 \\n。"""
    seps = " →·；;，,："
    lines = []
    for para in text.split("\n"):
        cur = ""
        for ch in para:
            trial = cur + ch
            if not cur or d.textlength(trial, font=font) <= max_w:
                cur = trial
                continue
            cut = -1
            for k in range(len(cur) - 1, 0, -1):
                if cur[k] in seps or _can_break_before(cur[k]):
                    cut = k
                    break
            if cut > 0:
                lines.append(cur[:cut])
                cur = cur[cut:] + ch
            else:
                lines.append(cur)
                cur = ch
        lines.append(cur)
    return [l for l in lines if l]


def layout_lines(d, lines, max_w, start_size, min_size=15, max_rows=None):
    """在 start_size 下折行；行数超过 max_rows 则缩字号重试（只在此处允许缩字号）。"""
    size = start_size
    wrapped = []
    while size >= min_size:
        f = F(size)
        wrapped = []
        for t in lines:
            wrapped.extend(wrap_text(d, t, f, max_w))
        if max_rows is None or len(wrapped) <= max_rows:
            return f, wrapped
        size -= 2
    return F(min_size), wrapped


def text_block(d, x1, y1, x2, y2, lines, size=26, gap=8, align="left", vcenter=True):
    """框内文字块：默认左对齐 + 自动折行 + 垂直居中；align="center" 可选。"""
    max_w = (x2 - x1) - PAD * 2
    max_rows = max(1, int(((y2 - y1) - VGAP * 2 + gap) / (size + gap)))
    f, wrapped = layout_lines(d, lines, max_w, size, max_rows=max_rows)
    heights, total = [], 0
    for t in wrapped:
        bb = d.textbbox((0, 0), t, font=f)
        heights.append(bb[3] - bb[1])
        total += bb[3] - bb[1]
    total += gap * (len(wrapped) - 1)
    y = (y1 + y2) / 2 - total / 2 if vcenter else y1 + VGAP
    for t, h in zip(wrapped, heights):
        if align == "left":
            d.text((x1 + PAD, y + h / 2), t, font=f, fill="black", anchor="lm")
        else:
            d.text(((x1 + x2) / 2, y + h / 2), t, font=f, fill="black", anchor="mm")
        y += h + gap


# ---- 图元 ----
def box(d, x1, y1, x2, y2, lines, size=26, gap=6):
    """普通方框：黑实线白底，框内文字左对齐自动折行"""
    d.rectangle([x1, y1, x2, y2], outline="black", width=LW, fill="white")
    text_block(d, x1, y1, x2, y2, lines, size=size, gap=gap, align="left")


def container(d, x1, y1, x2, y2, title, title_size=26):
    """容器框：标题居中于顶部内侧，内部再放子框"""
    d.rectangle([x1, y1, x2, y2], outline="black", width=LW, fill="white")
    d.text(((x1 + x2) / 2, y1 + 34), title, font=F(title_size), fill="black", anchor="mm")


def _poly_len(pts):
    return sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
               for i in range(len(pts) - 1))


def _point_at(pts, dist):
    for i in range(len(pts) - 1):
        seg = math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
        if dist <= seg:
            t = dist / seg if seg else 0
            return (pts[i][0] + t * (pts[i + 1][0] - pts[i][0]),
                    pts[i][1] + t * (pts[i + 1][1] - pts[i][1]))
        dist -= seg
    return pts[-1]


def line(d, pts, dashed=False, arrow=True, on=14, off=9):
    """曼哈顿折线。dashed=True 虚线（用于反馈/可选路径）；arrow=True 末端实心三角箭头，
    方向由末段行进方向自动定向。总线干路传 arrow=False，箭头只落支路末梢。"""
    if len(pts) < 2:
        return
    if dashed:
        total = _poly_len(pts)
        dist = 0.0
        while dist < total - on:
            a = _point_at(pts, dist)
            b = _point_at(pts, min(dist + on, total))
            d.line([a, b], fill="black", width=LW)
            dist += on + off
        d.line([_point_at(pts, max(total - on, 0)), pts[-1]], fill="black", width=LW)
    else:
        d.line(pts, fill="black", width=LW)
    if arrow:
        prev = _point_at(pts, max(_poly_len(pts) - 30, 0))
        tip = pts[-1]
        dx, dy = tip[0] - prev[0], tip[1] - prev[1]
        L = math.hypot(dx, dy) or 1
        ux, uy = dx / L, dy / L
        px, py = -uy, ux
        s = 16
        d.polygon([tip,
                   (tip[0] - s * ux + s * 0.5 * px, tip[1] - s * uy + s * 0.5 * py),
                   (tip[0] - s * ux - s * 0.5 * px, tip[1] - s * uy - s * 0.5 * py)],
                  fill="black")


def label(d, xy, text, size=20, anchor="mm"):
    """折线旁的独立标注文字（不属于任何框），置于空白处不压线不压框"""
    d.text(xy, text, font=F(size), fill="black", anchor=anchor)


# ---- 画布 ----
def begin(w, h):
    """创建白底画布，返回 (img, d)；所有图元函数传入同一个 d"""
    img = Image.new("RGB", (w, h), "white")
    return img, ImageDraw.Draw(img)


def save(img, path):
    img.save(path)
    return path
