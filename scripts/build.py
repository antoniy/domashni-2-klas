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
        self.c = canvas.Canvas(str(path), pagesize=A4, invariant=1)
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
    exprs = t["expressions"]
    row_h = 15 * mm
    # A flat list wraps into `columns`; a list of lists keeps the teacher's
    # rows, each row spread over the full width.
    if isinstance(exprs[0], list):
        rows = [(row, len(row)) for row in exprs]
    else:
        cols = t.get("columns", 4)
        rows = [(exprs[i:i + cols], cols) for i in range(0, len(exprs), cols)]
    for row, cols in rows:
        col_w = (W - 2 * M) / cols
        s.ensure(row_h)
        for col, expr in enumerate(row):
            x = M + col * col_w
            s.c.setFont("Body", 16)
            s.c.setFillColor(BLACK)
            s.c.drawString(x, s.y, expr)
            s.c.setStrokeColor(BLACK)
            s.c.rect(x + pdfmetrics.stringWidth(expr, "Body", 16) + 2 * mm,
                     s.y - 3 * mm, 12 * mm, 9 * mm)
        s.y -= row_h
    s.y -= 4 * mm


def task_short_answer(s, t):
    """Word followed by a short writing line, words side by side in columns."""
    cols = t.get("columns", 2)
    col_w = (W - 2 * M) / cols
    words = t["words"]
    for i in range(0, len(words), cols):
        s.ensure(LINE_GAP)
        for col, word in enumerate(words[i:i + cols]):
            x = M + col * col_w
            s.c.setFont("Body-Bold", 12)
            s.c.setFillColor(BLACK)
            s.c.drawString(x, s.y + 2, word)
            s.c.setStrokeColor(RULE)
            s.c.line(x + pdfmetrics.stringWidth(word, "Body-Bold", 12) + 3 * mm, s.y,
                     x + col_w - 6 * mm, s.y)
        s.y -= LINE_GAP + 0.5 * mm


def task_equations(s, t):
    """Equation with an unknown, then short lines below it for the solution steps."""
    cols = t.get("columns", 2)
    lines = t.get("lines", 2)
    col_w = (W - 2 * M) / cols
    eqs = t["equations"]
    for i in range(0, len(eqs), cols):
        s.ensure(6 * mm + lines * LINE_GAP)
        top = s.y
        for col, eq in enumerate(eqs[i:i + cols]):
            x = M + col * col_w
            s.c.setFont("Body", 16)
            s.c.setFillColor(BLACK)
            s.c.drawString(x, top, eq)
            s.c.setStrokeColor(RULE)
            for n in range(1, lines + 1):
                y = top - 2 * mm - n * LINE_GAP
                s.c.line(x, y, x + col_w - 10 * mm, y)
        s.y = top - 2 * mm - lines * LINE_GAP - 8 * mm
    s.y += 4 * mm


def task_copy_text(s, t):
    """A text to copy (optional centred title), writing lines, then labelled sections."""
    if "title" in t:
        s.ensure(8 * mm)
        s.c.setFont("Body-Bold", 13)
        s.c.setFillColor(BLACK)
        s.c.drawCentredString(W / 2, s.y, t["title"])
        s.y -= 7 * mm
    for para in t["passage"]:
        s.paragraph(para, after=1 * mm)
    s.y -= 6 * mm
    # One line at a time, so the copying space may run onto the next page.
    for _ in range(t.get("lines", 10)):
        s.ensure(LINE_GAP)
        s.rule()
        s.y -= LINE_GAP
    s.y -= 2 * mm
    for label, count in t.get("sections", []):
        s.labelled_lines(label, count)


def task_word_problems(s, t):
    sections = t.get("sections", DEFAULT_SECTIONS)
    # No `problems`: the task text itself is the one problem.
    if "problems" not in t:
        for label, count in sections:
            s.labelled_lines(label, count)
        return
    letters = "абвгдежзий"
    for letter, text in zip(letters, t["problems"]):
        s.paragraph(f"<b>{letter})</b> {text}", after=5 * mm)
        for label, count in sections:
            s.labelled_lines(label, count)
        s.y -= 5 * mm


def task_column(s, t):
    """Written (column) arithmetic: numbers digit by digit in a grid, one operator.

    Each problem is "a + b + c" or "a - b" with spaces only between numbers and
    the operator. Rows: small cells for carries/borrows, one row per number with
    the operator in the left cell, a thick line, then empty answer cells.
    """
    cell = 6.5 * mm
    carry_h = 5 * mm
    gap = 4 * mm        # between grids side by side
    row_gap = 10 * mm   # between rows of grids
    problems = [p.split() for p in t["problems"]]
    # Widest number in the task, plus one digit for a possible carry out of
    # the top column, plus the operator cell; all grids share this width.
    digits = max(len(tok) for p in problems for tok in p[::2]) + 1
    width = (digits + 1) * cell
    cols = t.get("columns", max(1, int((W - 2 * M + gap) // (width + gap))))
    col_w = (W - 2 * M) / cols
    c = s.c

    def cells(x, y, h, color):
        c.setStrokeColor(color)
        for i in range(digits):
            c.rect(x + (i + 1) * cell, y - h, cell, h)

    for i in range(0, len(problems), cols):
        row = problems[i:i + cols]
        rows = max(len(p) // 2 + 1 for p in row)
        s.ensure(7 * mm + carry_h + (rows + 1) * cell)
        top = s.y
        for col, p in enumerate(row):
            n = i + col + 1
            x = M + col * col_w
            c.setFont("Body-Bold", 11)
            c.setFillColor(LABEL)
            c.drawString(x, top, f"{n})")
            y = top - 3 * mm
            cells(x, y, carry_h, RULE)
            y -= carry_h
            op = p[1]
            c.setFillColor(BLACK)
            for r, number in enumerate(p[::2]):
                cells(x, y, cell, RULE)
                c.setFont("Body", 16)
                for d, ch in enumerate(reversed(number)):
                    cx = x + (digits - d + 0.5) * cell
                    c.drawCentredString(cx, y - cell + 2 * mm, ch)
                if r:
                    c.drawCentredString(x + 0.5 * cell, y - cell + 2 * mm,
                                        "–" if op in "-–−" else op)
                y -= cell
            c.setStrokeColor(BLACK)
            c.setLineWidth(2)
            c.line(x, y, x + width, y)
            c.setLineWidth(1)
            cells(x, y, cell, BLACK)
        s.y = top - 3 * mm - carry_h - (rows + 1) * cell - row_gap
    s.y += row_gap - 4 * mm


TASKS = {
    "sentences": task_sentences,
    "calc": task_calc,
    "word_problems": task_word_problems,
    "column": task_column,
    "short_answer": task_short_answer,
    "equations": task_equations,
    "copy_text": task_copy_text,
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
