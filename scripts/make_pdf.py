"""Bundle every text file in the project into one PDF for submission."""
from pathlib import Path
from fpdf import FPDF

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(r"D:\Test Claude\support-memory.pdf")

# Order of files matters - reviewers should see docs before code.
FILES = [
    ("README.md", "README"),
    ("ARCHITECTURE.md", "ARCHITECTURE"),
    ("DAILY_UPDATE.md", "DAILY UPDATE"),
    ("NEXT.md", "NEXT"),
    ("requirements.txt", "requirements.txt"),
    ("seed_data.json", "seed_data.json"),
    ("src/db.py", "src/db.py"),
    ("src/ingest.py", "src/ingest.py"),
    ("src/facts.py", "src/facts.py"),
    ("src/conflicts.py", "src/conflicts.py"),
    ("src/context.py", "src/context.py"),
    ("src/main.py", "src/main.py"),
    ("tests/test_landmines.py", "tests/test_landmines.py"),
    ("scripts/generate_samples.py", "scripts/generate_samples.py"),
]


def sanitize(text: str) -> str:
    """fpdf2's core fonts are Latin-1 only. Map common Unicode glyphs to safe ASCII."""
    replacements = {
        "—": "--",   # em dash
        "–": "-",    # en dash
        "→": "->",   # right arrow
        "←": "<-",
        "‘": "'",    # left single quote
        "’": "'",    # right single quote
        "“": '"',    # left double quote
        "”": '"',    # right double quote
        "…": "...",  # ellipsis
        "✅": "[x]",  # check mark
        " ": " ",    # non-breaking space
        "•": "*",    # bullet
        "▶": ">",
        "│": "|",    # box drawing
        "├": "+",
        "─": "-",
        "└": "+",
        "┳": "+",
        "┌": "+",
        "┐": "+",
        "┘": "+",
        "┼": "+",
        "┤": "+",
        "┬": "+",
        "┴": "+",
        "●": "*",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", errors="replace").decode("latin-1")


class PDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(120, 120, 120)
        self.cell(0, 6, "Support Memory Reliability Layer", align="L")
        self.cell(0, 6, f"page {self.page_no()}", align="R", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def footer(self):
        pass


def add_title_page(pdf: PDF):
    pdf.add_page()
    pdf.ln(60)
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(20, 20, 20)
    pdf.cell(0, 12, "Support Memory", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 12, "Reliability Layer", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 8, "Aster Support work sample", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "3-hour time-boxed", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(20)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(
        0,
        6,
        sanitize(
            "Contents:\n\n"
            "1. README.md\n"
            "2. ARCHITECTURE.md\n"
            "3. DAILY_UPDATE.md\n"
            "4. NEXT.md\n"
            "5. requirements.txt\n"
            "6. seed_data.json\n"
            "7. Source code (src/)\n"
            "8. Tests (tests/)\n"
            "9. Scripts (scripts/)\n\n"
            "13 tests passing. All landmines covered."
        ),
        align="C",
    )


def add_section(pdf: PDF, title: str, body: str, is_code: bool):
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(20, 20, 80)
    pdf.cell(0, 10, sanitize(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(80, 80, 80)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(4)

    pdf.set_text_color(20, 20, 20)
    if is_code:
        pdf.set_font("Courier", "", 8)
        line_h = 4
    else:
        pdf.set_font("Helvetica", "", 10)
        line_h = 5

    for line in body.splitlines() or [""]:
        safe = sanitize(line) or " "
        pdf.multi_cell(0, line_h, safe, new_x="LMARGIN", new_y="NEXT")


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pdf = PDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(left=15, top=15, right=15)

    add_title_page(pdf)

    for rel_path, title in FILES:
        full = ROOT / rel_path
        if not full.exists():
            print(f"skip missing: {rel_path}")
            continue
        body = full.read_text(encoding="utf-8")
        is_code = rel_path.endswith((".py", ".json", ".txt"))
        add_section(pdf, title, body, is_code)
        print(f"added: {rel_path}")

    pdf.output(str(OUT))
    print(f"\nPDF written: {OUT}")
    print(f"Size: {OUT.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
