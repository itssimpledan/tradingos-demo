"""
pdf_report.py  –  Portfolio PDF report generator for TradingOS
Requires: reportlab>=4.0.0
"""

from __future__ import annotations
import io
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm, mm
from reportlab.pdfgen import canvas as _canvas
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.graphics.shapes import Drawing, Circle, Rect, Line
from reportlab.graphics.charts.piecharts import Pie

# ──────────────────────────────────────────────────────────────
#  Brand palette (print-friendly light theme)
# ──────────────────────────────────────────────────────────────
C_NAVY   = colors.HexColor("#1a2440")
C_NAVY2  = colors.HexColor("#243060")
C_BLUE   = colors.HexColor("#3b6fd4")
C_BLUE_L = colors.HexColor("#dbeafe")
C_GREEN  = colors.HexColor("#16a34a")
C_GREEN_L= colors.HexColor("#dcfce7")
C_RED    = colors.HexColor("#dc2626")
C_RED_L  = colors.HexColor("#fee2e2")
C_AMBER  = colors.HexColor("#d97706")
C_MUTED  = colors.HexColor("#64748b")
C_LIGHT  = colors.HexColor("#f1f5f9")
C_BORDER = colors.HexColor("#e2e8f0")
C_WHITE  = colors.white
C_TEXT   = colors.HexColor("#1e293b")

CHART_COLORS = [
    colors.HexColor(h) for h in [
        "#3b6fd4","#22c55e","#f59e0b","#ef4444","#7c5bf0",
        "#06b6d4","#ec4899","#84cc16","#f97316","#a78bfa",
        "#14b8a6","#fb923c","#e879f9","#34d399","#fbbf24",
    ]
]

W, H = A4   # 595 x 842 pt


# ──────────────────────────────────────────────────────────────
#  Formatters
# ──────────────────────────────────────────────────────────────
def _fmt(n, prefix="S$", dp=0, abbr=True):
    if n is None:
        return "—"
    n = float(n)
    sign = "-" if n < 0 else ""
    abs_n = abs(n)
    if abbr and abs_n >= 1_000_000:
        s = f"{abs_n/1_000_000:.2f}M"
    elif abbr and abs_n >= 1_000:
        s = f"{abs_n/1_000:.1f}K"
    else:
        s = f"{abs_n:,.{dp}f}"
    return f"{sign}{prefix}{s}"

def _pct(n, dp=2):
    if n is None:
        return "—"
    v = float(n)
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.{dp}f}%"

def _pnl_color(n):
    try:
        return C_GREEN if float(n or 0) >= 0 else C_RED
    except Exception:
        return C_MUTED


# ──────────────────────────────────────────────────────────────
#  Style factory
# ──────────────────────────────────────────────────────────────
_base = getSampleStyleSheet()

def S(name, **kw):
    return ParagraphStyle(name, parent=_base["Normal"], **kw)

STYLES = {
    "section" : S("section",  fontSize=13, textColor=C_NAVY,  fontName="Helvetica-Bold",
                  spaceBefore=14, spaceAfter=6),
    "body"    : S("body",     fontSize=9,  textColor=C_TEXT,  leading=14),
    "muted"   : S("muted",    fontSize=8,  textColor=C_MUTED),
    "th"      : S("th",       fontSize=8,  textColor=C_WHITE, fontName="Helvetica-Bold",
                  alignment=TA_CENTER),
    "td"      : S("td",       fontSize=8,  textColor=C_TEXT),
    "td_r"    : S("td_r",     fontSize=8,  textColor=C_TEXT,  alignment=TA_RIGHT),
    "td_c"    : S("td_c",     fontSize=8,  textColor=C_TEXT,  alignment=TA_CENTER),
    "disc"    : S("disc",     fontSize=7,  textColor=C_MUTED, alignment=TA_CENTER),
    "kpi_v"   : S("kpi_v",   fontSize=18, textColor=C_NAVY,  fontName="Helvetica-Bold",
                  alignment=TA_CENTER, leading=22),
    "kpi_l"   : S("kpi_l",   fontSize=7,  textColor=C_MUTED, fontName="Helvetica-Bold",
                  alignment=TA_CENTER),
    "chart_h" : S("chart_h", fontSize=9,  textColor=C_NAVY,  fontName="Helvetica-Bold",
                  alignment=TA_CENTER, spaceAfter=4),
    "leg_name": S("leg_name",fontSize=8,  textColor=C_TEXT),
    "leg_pct" : S("leg_pct", fontSize=8,  textColor=C_MUTED, alignment=TA_RIGHT),
}


# ──────────────────────────────────────────────────────────────
#  Cover page  (drawn directly with canvas)
# ──────────────────────────────────────────────────────────────
def _cover_page(c: _canvas.Canvas, data: dict) -> None:
    r = data["risk"]
    now = datetime.now()

    # ── Top navy banner ──
    banner_h = H * 0.52
    c.setFillColor(C_NAVY)
    c.rect(0, H - banner_h, W, banner_h, fill=1, stroke=0)

    # Accent strip
    c.setFillColor(C_BLUE)
    c.rect(0, H - banner_h, W, 4, fill=1, stroke=0)

    # Diagonal geometric accent (subtle)
    c.setFillColorRGB(1, 1, 1, alpha=0.03)
    c.setFillColor(colors.HexColor("#243060"))
    c.rect(W * 0.6, H - banner_h, W * 0.5, banner_h, fill=1, stroke=0)

    # Brand label
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(C_BLUE)
    c.drawString(2 * cm, H - 1.6 * cm, "TradingOS")
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor("#8899bb"))
    c.drawString(2 * cm, H - 2.4 * cm, "Portfolio Management System")

    # Generated date (top-right)
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor("#8899bb"))
    c.drawRightString(W - 2 * cm, H - 1.8 * cm, f"Generated {now.strftime('%d %B %Y  %H:%M')}")

    # Main title
    c.setFont("Helvetica-Bold", 38)
    c.setFillColor(C_WHITE)
    c.drawCentredString(W / 2, H - banner_h + banner_h * 0.52, "PORTFOLIO")
    c.drawCentredString(W / 2, H - banner_h + banner_h * 0.38, "REPORT")

    # Blue underline below title
    c.setStrokeColor(C_BLUE)
    c.setLineWidth(2.5)
    c.line(W / 2 - 60, H - banner_h + banner_h * 0.32, W / 2 + 60, H - banner_h + banner_h * 0.32)

    # ── Portfolio value ──
    val_y = H - banner_h - 3.5 * cm
    c.setFont("Helvetica-Bold", 34)
    c.setFillColor(C_NAVY)
    total_str = f"S${r['total_sgd']:,.0f}"
    c.drawCentredString(W / 2, val_y, total_str)
    c.setFont("Helvetica", 10)
    c.setFillColor(C_MUTED)
    c.drawCentredString(W / 2, val_y - 18, "Total Portfolio Value (SGD Equivalent)")

    # P&L badge
    pnl = r["total_pnl_sgd"]
    pnl_pct = r["total_pnl_pct"]
    badge_color = C_GREEN if pnl >= 0 else C_RED
    pnl_str = f"{'+'if pnl>=0 else ''}{_fmt(pnl,'S$')}  ({'+'if pnl_pct>=0 else ''}{pnl_pct:.2f}%)"
    bw = 180
    bx = W / 2 - bw / 2
    by = val_y - 44
    c.setFillColor(C_GREEN_L if pnl >= 0 else C_RED_L)
    c.roundRect(bx, by, bw, 20, 4, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(badge_color)
    c.drawCentredString(W / 2, by + 6, pnl_str)

    # ── KPI boxes row ──
    kpis = [
        ("Holdings",       str(r["num_holdings"])),
        ("Sectors",        str(r["num_sectors"])),
        ("Options Open",   str(r["open_options"])),
        ("Diversification",f"{r['div_score']}/100"),
    ]
    box_y = by - 2.8 * cm
    box_w = (W - 4 * cm) / len(kpis)
    for i, (label, value) in enumerate(kpis):
        bx2 = 2 * cm + i * box_w
        c.setFillColor(C_LIGHT)
        c.setStrokeColor(C_BORDER)
        c.setLineWidth(0.5)
        c.roundRect(bx2 + 4, box_y, box_w - 8, 1.8 * cm, 5, fill=1, stroke=1)
        c.setFont("Helvetica-Bold", 16)
        c.setFillColor(C_NAVY)
        c.drawCentredString(bx2 + box_w / 2, box_y + 0.9 * cm, value)
        c.setFont("Helvetica", 7)
        c.setFillColor(C_MUTED)
        c.drawCentredString(bx2 + box_w / 2, box_y + 0.3 * cm, label.upper())

    # ── Divider ──
    c.setStrokeColor(C_BORDER)
    c.setLineWidth(0.5)
    c.line(2 * cm, box_y - 0.6 * cm, W - 2 * cm, box_y - 0.6 * cm)

    # ── Disclaimer ──
    disc_y = 2 * cm
    c.setFont("Helvetica", 7)
    c.setFillColor(C_MUTED)
    disc = ("This report is generated automatically by TradingOS for informational purposes only. "
            "It does not constitute financial advice. Past performance is not indicative of future results. "
            "Market values are indicative and sourced from Yahoo Finance.")
    # word-wrap manually
    words = disc.split()
    line_str = ""
    line_y = disc_y + 14
    for word in words:
        test = (line_str + " " + word).strip()
        if c.stringWidth(test, "Helvetica", 7) > W - 4 * cm:
            c.drawCentredString(W / 2, line_y, line_str)
            line_y -= 11
            line_str = word
        else:
            line_str = test
    if line_str:
        c.drawCentredString(W / 2, line_y, line_str)

    c.showPage()


# ──────────────────────────────────────────────────────────────
#  Page header / footer helpers
# ──────────────────────────────────────────────────────────────
def _page_header(c: _canvas.Canvas, title: str, page_num: int) -> None:
    # Top rule
    c.setFillColor(C_NAVY)
    c.rect(0, H - 1.6 * cm, W, 1.6 * cm, fill=1, stroke=0)
    c.setFillColor(C_BLUE)
    c.rect(0, H - 1.6 * cm, 4, 1.6 * cm, fill=1, stroke=0)

    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(C_WHITE)
    c.drawString(2 * cm, H - 1.1 * cm, title)
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#8899bb"))
    c.drawRightString(W - 2 * cm, H - 1.1 * cm, "TradingOS")

    # Footer rule
    c.setFillColor(C_BORDER)
    c.rect(0, 1.6 * cm, W, 0.5, fill=1, stroke=0)
    c.setFont("Helvetica", 7)
    c.setFillColor(C_MUTED)
    now = datetime.now().strftime("%d %b %Y")
    c.drawString(2 * cm, 0.9 * cm, f"TradingOS Portfolio Report · {now}")
    c.drawRightString(W - 2 * cm, 0.9 * cm, f"Page {page_num}")


# ──────────────────────────────────────────────────────────────
#  Section header (inline, used in Platypus flow)
# ──────────────────────────────────────────────────────────────
def _sec(text: str) -> list:
    return [
        Paragraph(text, STYLES["section"]),
        HRFlowable(width="100%", thickness=0.5, color=C_BORDER, spaceAfter=6),
    ]


# ──────────────────────────────────────────────────────────────
#  Donut chart (reportlab graphics)
# ──────────────────────────────────────────────────────────────
def _donut(data_dict: dict, size: float = 160) -> Drawing:
    entries = [(k, v) for k, v in data_dict.items() if v > 0]
    d = Drawing(size, size)
    if not entries:
        return d
    pie = Pie()
    cx = size / 2
    pie.x = cx - size * 0.44
    pie.y = cx - size * 0.44
    pie.width  = size * 0.88
    pie.height = size * 0.88
    pie.data   = [v for _, v in entries]
    pie.labels = [""] * len(entries)
    pie.simpleLabels = 1
    pie.sideLabels = 0
    for i in range(len(entries)):
        cc = CHART_COLORS[i % len(CHART_COLORS)]
        pie.slices[i].fillColor   = cc
        pie.slices[i].strokeColor = C_WHITE
        pie.slices[i].strokeWidth = 1.5
    d.add(pie)
    # Donut hole
    hole_r = size * 0.25
    d.add(Circle(cx, cx, hole_r, fillColor=C_WHITE, strokeColor=C_WHITE, strokeWidth=0))
    return d


def _legend(data_dict: dict, total: float, col_w: list) -> Table:
    entries = [(k, v) for k, v in data_dict.items() if v > 0][:10]
    rows = []
    for i, (k, v) in enumerate(entries):
        cc = CHART_COLORS[i % len(CHART_COLORS)]
        dot = Drawing(10, 10)
        dot.add(Circle(5, 5, 4.5, fillColor=cc, strokeColor=cc))
        pct  = f"{v/total*100:.1f}%" if total else "—"
        val  = _fmt(v, "S$")
        rows.append([dot, Paragraph(k[:22], STYLES["leg_name"]), Paragraph(pct, STYLES["leg_pct"]), Paragraph(val, STYLES["leg_pct"])])

    if not rows:
        return Spacer(1, 1)

    t = Table(rows, colWidths=col_w)
    t.setStyle(TableStyle([
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [C_WHITE, C_LIGHT]),
        ("LEFTPADDING",    (0, 0), (-1, -1), 3),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 3),
        ("TOPPADDING",     (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 3),
        ("FONTSIZE",       (0, 0), (-1, -1), 8),
        ("LINEBELOW",      (0, 0), (-1, -2), 0.3, C_BORDER),
    ]))
    return t


# ──────────────────────────────────────────────────────────────
#  Risk gauge (horizontal bar)
# ──────────────────────────────────────────────────────────────
def _gauge_row(label: str, value_str: str, pct: float, bar_color, desc: str, bar_w: float = 200) -> Table:
    """Returns a small 2-column table: label+bar | value"""
    bg = Drawing(bar_w, 10)
    bg.add(Rect(0, 3, bar_w, 6, fillColor=C_LIGHT, strokeColor=C_BORDER, strokeWidth=0.3, rx=3))
    fill_w = max(4, min(bar_w, bar_w * pct / 100))
    bg.add(Rect(0, 3, fill_w, 6, fillColor=bar_color, strokeColor=bar_color, strokeWidth=0, rx=3))

    inner = Table([
        [Paragraph(f"<b>{label}</b>", STYLES["body"]), Paragraph(f"<b>{value_str}</b>", S("gv", fontSize=13, textColor=bar_color, fontName="Helvetica-Bold", alignment=TA_RIGHT))],
        [bg, ""],
        [Paragraph(desc, STYLES["muted"]), ""],
    ], colWidths=[bar_w + 10, 60])
    inner.setStyle(TableStyle([
        ("SPAN",       (0, 1), (-1, 1)),
        ("SPAN",       (0, 2), (-1, 2)),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return inner


# ──────────────────────────────────────────────────────────────
#  Main builder
# ──────────────────────────────────────────────────────────────
def build_portfolio_pdf(data: dict) -> bytes:
    """
    data = result of the /api/analytics/portfolio endpoint.
    Returns PDF bytes.
    """
    buf = io.BytesIO()
    r   = data["risk"]

    # We build a multi-page PDF using a hybrid approach:
    #   - Cover drawn with low-level canvas
    #   - Content pages drawn with Platypus inside a custom onPage callback

    page_num = [1]   # mutable counter for footer

    def on_first_page(canvas, doc):
        pass   # cover already drawn

    def on_later_pages(canvas, doc):
        PAGE_TITLES = {
            2: "Executive Summary",
            3: "Holdings",
            4: "Allocation & Exposure",
            5: "Risk & Options",
        }
        title = PAGE_TITLES.get(doc.page, "Portfolio Report")
        _page_header(canvas, title, doc.page)

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2.4 * cm,
        bottomMargin=2.4 * cm,
        title="Portfolio Report",
        author="TradingOS",
    )

    # ── Build Platypus story ──
    story = []

    # ── PAGE 1 placeholder  (drawn manually below via canvasmaker) ──
    # We draw the cover using a canvasmaker trick: build with a temporary canvas first,
    # then stitch. Simpler: just start Platypus from page 2 and prepend cover later.
    # SIMPLEST: use a custom FirstPageTemplate that draws the cover, then content.
    # For now: add a PageBreak so page 1 is "empty" and we overlay via on_first_page.

    # ── PAGE 2: Executive Summary ──
    top_eq  = sorted(data.get("top_holdings", []), key=lambda h: h.get("market_value_sgd") or 0, reverse=True)
    total   = r["total_sgd"] or 1

    # Summary grid  (2×4 table of KPI boxes)
    kpi_data = [
        ("Total Portfolio", _fmt(r["total_sgd"], "S$"), "SGD equivalent"),
        ("Equity Value",    _fmt(r["total_eq_sgd"], "S$"), "SGD equivalent"),
        ("Crypto Value",    _fmt(r["total_cr_sgd"], "S$"), "SGD equivalent"),
        ("Unrealised P&L",  _fmt(r["total_pnl_sgd"], "S$"), _pct(r["total_pnl_pct"])),
        ("Holdings",        str(r["num_holdings"]), "positions"),
        ("Sectors",         str(r["num_sectors"]), "unique sectors"),
        ("Largest Position",f"{r['max_weight_pct']}%", "of portfolio"),
        ("Diversification", f"{r['div_score']}/100", "score"),
    ]

    def _kpi_cell(label, value, sub):
        return Table([[
            Paragraph(value, STYLES["kpi_v"]),
            Paragraph(label.upper(), STYLES["kpi_l"]),
            Paragraph(sub, STYLES["muted"] if sub else STYLES["kpi_l"]),
        ]], rowHeights=[26, 14, 12])

    kpi_cells = []
    for i in range(0, len(kpi_data), 4):
        row = []
        for label, value, sub in kpi_data[i:i+4]:
            inner = Table([
                [Paragraph(value, STYLES["kpi_v"])],
                [Paragraph(label.upper(), STYLES["kpi_l"])],
                [Paragraph(sub, STYLES["muted"])],
            ], colWidths=[(W - 4*cm) / 4 - 8])
            inner.setStyle(TableStyle([
                ("BOX",           (0,0), (-1,-1), 0.5, C_BORDER),
                ("BACKGROUND",    (0,0), (-1,-1), C_LIGHT),
                ("TOPPADDING",    (0,0), (-1,-1), 8),
                ("BOTTOMPADDING", (0,0), (-1,-1), 8),
                ("ALIGN",         (0,0), (-1,-1), "CENTER"),
                ("ROWBACKGROUNDS",(0,0), (-1,-1), [C_LIGHT]),
            ]))
            row.append(inner)
        kpi_cells.append(row)

    kpi_table = Table(kpi_cells, colWidths=[(W - 4*cm) / 4] * 4, hAlign="LEFT")
    kpi_table.setStyle(TableStyle([
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING",   (0,0), (-1,-1), 3),
        ("RIGHTPADDING",  (0,0), (-1,-1), 3),
    ]))

    story += _sec("Executive Summary")
    story.append(kpi_table)
    story.append(Spacer(1, 0.5 * cm))

    # Options summary row
    wr = r.get("win_rate")
    story += _sec("Options Snapshot")
    opt_summary = Table([[
        Paragraph(f"<b>Open Positions</b><br/><font size=16>{r['open_options']}</font>", STYLES["body"]),
        Paragraph(f"<b>Options P&L</b><br/><font size=16>{_fmt(r['opt_pnl'],'$')}</font>", STYLES["body"]),
        Paragraph(f"<b>Win Rate</b><br/><font size=16>{wr}%</font>" if wr is not None else "<b>Win Rate</b><br/><font size=16>—</font>", STYLES["body"]),
    ]], colWidths=[(W - 4*cm) / 3] * 3)
    opt_summary.setStyle(TableStyle([
        ("BOX",           (0,0), (-1,-1), 0.5, C_BORDER),
        ("INNERGRID",     (0,0), (-1,-1), 0.3, C_BORDER),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING",   (0,0), (-1,-1), 12),
        ("BACKGROUND",    (0,0), (-1,-1), C_LIGHT),
    ]))
    story.append(opt_summary)
    story.append(PageBreak())

    # ── PAGE 3: Holdings ──
    story += _sec("Top Holdings by Market Value")

    # Table header
    hdr = [
        Paragraph("#",           STYLES["th"]),
        Paragraph("Ticker",      STYLES["th"]),
        Paragraph("Company",     STYLES["th"]),
        Paragraph("Sector",      STYLES["th"]),
        Paragraph("CCY",         STYLES["th"]),
        Paragraph("Mkt Val SGD", STYLES["th"]),
        Paragraph("P&L SGD",     STYLES["th"]),
        Paragraph("P&L %",       STYLES["th"]),
        Paragraph("Weight",      STYLES["th"]),
    ]
    tbl_rows = [hdr]
    for i, h in enumerate(top_eq[:15]):
        wt   = (h.get("market_value_sgd") or 0) / total * 100
        pnl  = h.get("unrealized_pnl_sgd")
        pnl_p= h.get("unrealized_pnl_pct")
        row  = [
            Paragraph(str(i + 1),               STYLES["td_c"]),
            Paragraph(f"<b>{h['ticker']}</b>",  STYLES["td"]),
            Paragraph((h.get("company") or "—")[:20], STYLES["td"]),
            Paragraph((h.get("sector")  or "—")[:16], STYLES["td"]),
            Paragraph(h.get("currency") or "USD",      STYLES["td_c"]),
            Paragraph(_fmt(h.get("market_value_sgd"), "S$"), STYLES["td_r"]),
            Paragraph(_fmt(pnl, "S$") if pnl is not None else "—",  STYLES["td_r"]),
            Paragraph(_pct(pnl_p) if pnl_p is not None else "—",    STYLES["td_r"]),
            Paragraph(f"{wt:.1f}%", STYLES["td_r"]),
        ]
        tbl_rows.append(row)

    cw = [18, 42, 100, 80, 28, 70, 65, 48, 38]
    holdings_tbl = Table(tbl_rows, colWidths=cw, repeatRows=1)
    holdings_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  C_NAVY),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_WHITE, C_LIGHT]),
        ("LINEBELOW",     (0, 0), (-1, 0),  1, C_BLUE),
        ("LINEBELOW",     (0, 1), (-1, -2), 0.3, C_BORDER),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
    ]))
    story.append(holdings_tbl)
    story.append(PageBreak())

    # ── PAGE 4: Allocation charts ──
    story += _sec("Allocation & Exposure")

    # Build three donut + legend columns
    charts_data = [
        ("Sector Allocation",   data.get("sectors",    {})),
        ("Currency Exposure",   data.get("currencies", {})),
        ("Platform Exposure",   data.get("platforms",  {})),
    ]

    chart_cols = []
    leg_col_w = [12, 75, 32, 48]
    for title, cdata in charts_data:
        csum = sum(v for v in cdata.values() if v > 0)
        donut = _donut(cdata, size=150)
        legend = _legend(cdata, csum, leg_col_w)
        col_table = Table([
            [Paragraph(title, STYLES["chart_h"])],
            [donut],
            [Paragraph(f"Total: {_fmt(csum,'S$')}", STYLES["muted"])],
            [Spacer(1, 4)],
            [legend],
        ], colWidths=[(W - 4*cm) / 3 - 8])
        col_table.setStyle(TableStyle([
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("BOX",           (0, 0), (-1, -1), 0.5, C_BORDER),
            ("BACKGROUND",    (0, 0), (-1, -1), C_LIGHT),
        ]))
        chart_cols.append(col_table)

    chart_row = Table([chart_cols], colWidths=[(W - 4*cm) / 3] * 3)
    chart_row.setStyle(TableStyle([
        ("LEFTPADDING",  (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("VALIGN",       (0,0), (-1,-1), "TOP"),
    ]))
    story.append(chart_row)
    story.append(PageBreak())

    # ── PAGE 5: Risk & Options ──
    story += _sec("Risk Metrics")

    # HHI description
    hhi = r["hhi"]
    hhi_label = ("Well diversified"       if hhi < 0.10 else
                 "Moderate concentration" if hhi < 0.25 else
                 "High concentration — single-stock risk elevated")
    maxw = r["max_weight_pct"]
    div  = r["div_score"]

    risk_rows = [
        ("Concentration (HHI)",   f"{hhi:.3f}",  hhi * 100,
         C_GREEN if hhi < 0.10 else C_AMBER if hhi < 0.25 else C_RED,
         hhi_label + "  ·  0 = perfect diversification, 1 = single holding"),
        ("Largest Position",      f"{maxw}%",    maxw,
         C_GREEN if maxw < 20 else C_AMBER if maxw < 35 else C_RED,
         "Healthy portfolios target < 20% in any single position"),
        ("Diversification Score", f"{div}/100",  div,
         C_GREEN if div >= 70 else C_AMBER if div >= 40 else C_RED,
         "100 = perfectly distributed  ·  0 = fully concentrated"),
        ("Options Win Rate",      f"{wr}%" if wr is not None else "—", wr or 0,
         C_GREEN if (wr or 0) >= 50 else C_RED,
         "Percentage of closed options trades with positive P&L"),
    ]

    risk_tbl_rows = []
    for label, val_str, pct_val, bar_col, desc in risk_rows:
        # bar drawing
        bar_draw = Drawing(220, 10)
        bar_draw.add(Rect(0, 3, 220, 6, fillColor=C_LIGHT, strokeColor=C_BORDER, strokeWidth=0.3, rx=3))
        fw = max(4, min(220, 220 * float(pct_val) / 100))
        bar_draw.add(Rect(0, 3, fw, 6, fillColor=bar_col, strokeColor=bar_col, strokeWidth=0, rx=3))

        risk_tbl_rows.append([
            Table([
                [Paragraph(f"<b>{label}</b>", STYLES["body"]),
                 Paragraph(val_str, S("rv", fontSize=14, fontName="Helvetica-Bold",
                                      textColor=bar_col, alignment=TA_RIGHT))],
                [bar_draw, ""],
                [Paragraph(desc, STYLES["muted"]), ""],
            ], colWidths=[240, 70]),
        ])

    risk_tbl = Table(risk_tbl_rows, colWidths=[W - 4*cm])
    risk_tbl.setStyle(TableStyle([
        ("TOPPADDING",    (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("LEFTPADDING",   (0,0), (-1,-1), 12),
        ("RIGHTPADDING",  (0,0), (-1,-1), 12),
        ("ROWBACKGROUNDS",(0,0), (-1,-1), [C_WHITE, C_LIGHT]),
        ("BOX",           (0,0), (-1,-1), 0.5, C_BORDER),
        ("LINEBELOW",     (0,0), (-1,-2), 0.3, C_BORDER),
    ]))
    story.append(risk_tbl)

    # Open options table
    story.append(Spacer(1, 0.6 * cm))
    story += _sec("Open Options Positions")

    open_opts = data.get("open_trades", [])
    if open_opts:
        opt_hdr = [Paragraph(t, STYLES["th"]) for t in
                   ["Ticker","Strategy","Platform","Type","Dir","Strike","Expiry","Contracts","Premium"]]
        opt_rows = [opt_hdr]
        for t in open_opts[:20]:
            opt_rows.append([
                Paragraph(f"<b>{t.get('ticker','')}</b>",          STYLES["td"]),
                Paragraph(t.get("strategy","—")[:20],              STYLES["td"]),
                Paragraph(t.get("platform","—") or "—",            STYLES["td"]),
                Paragraph(t.get("option_type","—"),                 STYLES["td_c"]),
                Paragraph(t.get("direction","—"),                   STYLES["td_c"]),
                Paragraph(f"${t.get('strike',0)}",                  STYLES["td_r"]),
                Paragraph(str(t.get("expiry","—")),                 STYLES["td_c"]),
                Paragraph(str(t.get("contracts",0)),                STYLES["td_c"]),
                Paragraph(f"${float(t.get('premium',0)):.2f}",      STYLES["td_r"]),
            ])
        opt_tbl = Table(opt_rows, colWidths=[45,110,65,35,30,45,55,45,45], repeatRows=1)
        opt_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0),  C_NAVY),
            ("ROWBACKGROUNDS",(0,1), (-1,-1), [C_WHITE, C_LIGHT]),
            ("LINEBELOW",     (0,0), (-1,0),  1, C_BLUE),
            ("LINEBELOW",     (0,1), (-1,-2), 0.3, C_BORDER),
            ("TOPPADDING",    (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ("LEFTPADDING",   (0,0), (-1,-1), 4),
            ("RIGHTPADDING",  (0,0), (-1,-1), 4),
            ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ]))
        story.append(opt_tbl)
    else:
        story.append(Paragraph("No open options positions.", STYLES["muted"]))

    # ── Build PDF ──
    doc.build(story, onFirstPage=on_first_page, onLaterPages=on_later_pages)

    # ── Prepend cover page ──
    # Re-open buffer and inject cover as first page using PyPDF if available,
    # else use a two-pass approach: draw cover into a separate buffer then merge.
    pdf_bytes = buf.getvalue()

    # Draw cover into its own buffer
    cover_buf = io.BytesIO()
    cc = _canvas.Canvas(cover_buf, pagesize=A4)
    _cover_page(cc, data)
    cc.save()
    cover_bytes = cover_buf.getvalue()

    # Merge: cover first, then content pages
    try:
        from pypdf import PdfWriter, PdfReader
        writer = PdfWriter()
        for src in [cover_bytes, pdf_bytes]:
            reader = PdfReader(io.BytesIO(src))
            for page in reader.pages:
                writer.add_page(page)
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()
    except ImportError:
        # pypdf not available — just return content (no separate cover)
        return pdf_bytes
