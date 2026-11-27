"""Publish a common sequence of evidence panels to HTML and paginated PDF."""
import html
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (Image as PDFImage, PageBreak, Paragraph, SimpleDocTemplate,
                               Spacer, Table, TableStyle)
from PIL import Image

if __package__:
    from .evidence import fmt
else:
    from evidence import fmt


def score_grid(scores, label):
    return ([label, "Low RGB MAE", "Detail luma MAE", "Detail correlation"],
            [[f"A{i} / W{i}", f"{s['low_rgb_mae']:.2f}", f"{s['detail_luma_mae']:.2f}", fmt(s["detail_luma_r"])]
             for i, s in enumerate(scores, 1)])


def grids(page):
    yield page["columns"], page["rows"]
    if "extra_rows" in page:
        yield page["extra_columns"], page["extra_rows"]
    if "scores" in page:
        yield score_grid(page["scores"], "Scale")
    if "replay_scores" in page:
        yield score_grid(page["replay_scores"], "Replay scale")


def browser_panel(page, figure):
    def cell(value):
        if isinstance(value, Image.Image):
            return figure(value, "")
        return html.escape(str(value))
    parts = ["<h3>" + cell(page["title"]) + "</h3><p>" + cell(page["note"]) + "</p>"]
    for headers, rows in grids(page):
        parts.append('<div class="panel"><table><tr>' +
                     "".join("<th>" + cell(h) + "</th>" for h in headers) + "</tr>")
        for row in rows:
            parts.append("<tr>" + "".join("<td>" + cell(v) + "</td>" for v in row) + "</tr>")
        parts.append("</table></div>")
    parts.extend("<p>" + cell(s) + "</p>" for s in page.get("lines", []))
    return "".join(parts)


def publish_pdf(path, sections):
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=36, rightMargin=36,
                            topMargin=38, bottomMargin=42, title="Reconstruction review")
    width = doc.width - 12
    styles = {}
    for key, size, bold in [("title", 21, True), ("label", 10, True), ("body", 11, False),
                            ("cell", 9, False)]:
        styles[key] = ParagraphStyle(key, fontName="Helvetica-Bold" if bold else "Helvetica",
                                     fontSize=size, leading=size*1.35, textColor=colors.HexColor("#203a40"))
    def paragraph(value, style="body"):
        return Paragraph(html.escape(str(value)), styles[style])

    story = []
    for context, page in sections:
        if story:
            story.append(PageBreak())
        story.extend([paragraph(context, "label"), Spacer(1, 8), paragraph(page["title"], "title"),
                      Spacer(1, 8), paragraph(page["note"]), Spacer(1, 14)])
        for headers, rows in grids(page):
            widths = [width/len(headers)] * len(headers)
            if headers[0] == "Scale" and len(headers) == 5:
                widths = [38] + [(width-38)/4]*4
            cells = [[paragraph(h, "cell") for h in headers]]
            for row in rows:
                rendered = []
                for col, value in enumerate(row):
                    if isinstance(value, Image.Image):
                        limit = 85 if headers[0] == "Scale" and len(headers) == 5 else 175
                        scale = min((widths[col]-8)/value.width, limit/value.height)
                        preview = value.copy()
                        preview.thumbnail((850,850), Image.Resampling.LANCZOS)
                        buf = io.BytesIO()
                        preview.save(buf, format="PNG")
                        rendered.append(PDFImage(buf, width=value.width*scale, height=value.height*scale))
                    else:
                        rendered.append(paragraph(value, "cell"))
                cells.append(rendered)
            table = Table(cells, colWidths=widths, repeatRows=1)
            table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#e3efeb")),
                                       ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                                       ("LEFTPADDING",(0,0),(-1,-1),4),
                                       ("RIGHTPADDING",(0,0),(-1,-1),4),
                                       ("LINEBELOW",(0,-1),(-1,-1),0.5,colors.grey)]))
            story.extend([table, Spacer(1,12)])
        for line in page.get("lines", []):
            story.extend([paragraph(line), Spacer(1,7)])

    def footer(canvas, doc):
        canvas.setFont("Helvetica",9)
        canvas.drawString(42,23,"imenlarge  /  Reconstruction review")
        canvas.drawRightString(A4[0]-42,23,str(doc.page))
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
