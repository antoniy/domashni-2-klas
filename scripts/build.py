"""Render one homework TOML file into a printable A4 PDF.

Usage: python scripts/build.py homework/2026-11-21.toml
Writes pdf/<same name>.pdf.
"""
import sys
import tomllib
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

# Cyrillic-capable system fonts, first match wins (macOS, then common Linux).
FONT_CANDIDATES = [
    ("/System/Library/Fonts/Supplemental/Arial.ttf",
     "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]

W, H = A4
M = 18 * mm
LINE_GAP = 9.5 * mm     # spacing between writing lines
# The printer is black and white: keep everything dark enough to print.
LABEL = HexColor("#333333")
RULE = HexColor("#666666")
BLACK = HexColor("#000000")

DEFAULT_SECTIONS = [["Кратък запис:", 3], ["Решение:", 2], ["Отговор:", 1]]


def register_fonts():
    for regular, bold in FONT_CANDIDATES:
        if Path(regular).exists() and Path(bold).exists():
            pdfmetrics.registerFont(TTFont("Body", regular))
            pdfmetrics.registerFont(TTFont("Body-Bold", bold))
            return
    sys.exit("No Cyrillic font found; add one to FONT_CANDIDATES")


class Sheet:
    def __init__(self, path):
        self.c = canvas.Canvas(str(path), pagesize=A4)
        self.c.setTitle(f"Домашна работа {Path(path).stem}")
        self.y = 0
        self.title = None

    # --- page flow ---------------------------------------------------------

    def new_page(self, title, continued=False):
        if self.y:
            self.c.showPage()
        self.title = title
        self.y = H - M
        self._name_date()
        self._subject(title + (" (продължение)" if continued else ""))

    def ensure(self, height):
        """Start a continuation page when the next block would cross the bottom margin."""
        if self.y - height < M:
            self.new_page(self.title, continued=True)

    def save(self):
        self.c.showPage()
        self.c.save()

    # --- drawing primitives ------------------------------------------------

    def _name_date(self):
        c, y = self.c, self.y
        c.setFont("Body", 11)
        c.setFillColor(LABEL)
        c.setStrokeColor(RULE)
        c.drawString(M, y, "Име:")
        c.line(M + 12 * mm, y - 1, W / 2 + 10 * mm, y - 1)
        c.drawString(W / 2 + 20 * mm, y, "Дата:")
        c.line(W / 2 + 32 * mm, y - 1, W - M, y - 1)
        self.y -= 14 * mm

    def _subject(self, title):
        c = self.c
        c.setFillColor(BLACK)
        c.setStrokeColor(BLACK)
        c.setFont("Body-Bold", 20)
        c.drawString(M, self.y, title)
        c.setLineWidth(1.2)
        c.line(M, self.y - 3 * mm, W - M, self.y - 3 * mm)
        c.setLineWidth(1)
        self.y -= 12 * mm

    def paragraph(self, text, bold=False, size=13, leading=18, after=3 * mm):
        style = ParagraphStyle("p", fontName="Body-Bold" if bold else "Body",
                               fontSize=size, leading=leading, textColor=BLACK)
        p = Paragraph(text, style)
        _, h = p.wrap(W - 2 * M, H)
        self.ensure(h)
        p.drawOn(self.c, M, self.y - h + size)
        self.y -= h + after

    def rule(self, x0=M):
        self.c.setStrokeColor(RULE)
        self.c.line(x0, self.y, W - M, self.y)

    def labelled_lines(self, label, count, bold=False, size=11):
        """A label followed by a writing line, then count-1 full-width lines."""
        font = "Body-Bold" if bold else "Body"
        self.ensure(count * LINE_GAP)
        self.c.setFont(font, size)
        self.c.setFillColor(BLACK if bold else LABEL)
        self.c.drawString(M, self.y + 2, label)
        self.rule(M + pdfmetrics.stringWidth(label, font, size) + 3 * mm)
        self.y -= LINE_GAP
        for _ in range(count - 1):
            self.rule()
            self.y -= LINE_GAP


# --- task renderers: one per task "type" in the TOML ----------------------

def task_sentences(s, t):
    for word in t["words"]:
        s.labelled_lines(word, t.get("lines", 2), bold=True, size=12)
        s.y -= 0.5 * mm


def task_calc(s, t):
    cols = t.get("columns", 4)
    col_w = (W - 2 * M) / cols
    row_h = 15 * mm
    for i in range(0, len(t["expressions"]), cols):
        s.ensure(row_h)
        for col, expr in enumerate(t["expressions"][i:i + cols]):
            x = M + col * col_w
            s.c.setFont("Body", 16)
            s.c.setFillColor(BLACK)
            s.c.drawString(x, s.y, expr)
            s.c.setStrokeColor(BLACK)
            s.c.rect(x + pdfmetrics.stringWidth(expr, "Body", 16) + 2 * mm,
                     s.y - 3 * mm, 12 * mm, 9 * mm)
        s.y -= row_h
    s.y -= 4 * mm


def task_word_problems(s, t):
    sections = t.get("sections", DEFAULT_SECTIONS)
    letters = "абвгдежзий"
    for letter, text in zip(letters, t["problems"]):
        s.paragraph(f"<b>{letter})</b> {text}", after=5 * mm)
        for label, count in sections:
            s.labelled_lines(label, count)
        s.y -= 5 * mm


TASKS = {
    "sentences": task_sentences,
    "calc": task_calc,
    "word_problems": task_word_problems,
}


def build(src):
    data = tomllib.loads(Path(src).read_text(encoding="utf-8"))
    out = Path(__file__).resolve().parent.parent / "pdf" / (Path(src).stem + ".pdf")
    out.parent.mkdir(exist_ok=True)
    register_fonts()
    s = Sheet(out)
    for subject in data["subject"]:
        s.new_page(subject["title"])
        for n, task in enumerate(subject["task"], 1):
            if task["type"] not in TASKS:
                sys.exit(f"Unknown task type {task['type']!r}; known: {', '.join(TASKS)}")
            s.paragraph(f"{n}. {task['text']}", bold=True, leading=17, after=6 * mm)
            TASKS[task["type"]](s, task)
            s.y -= 4 * mm
    s.save()
    print(out)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    build(sys.argv[1])
