"""Compose the reading edition from measured frames and optional visual observations."""
from io import BytesIO
from textwrap import shorten
from xml.sax.saxutils import escape

import numpy as np

from PIL import Image, ImageDraw
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph


def write_summary(path, original, frames, results, maps, wavelet, native_reference=None):
    if __package__:
        from .evidence import magnitude, native_box, signed
    else:
        from evidence import magnitude, native_box, signed
    rows = results["candidates"]
    workflow = results.get("workflow", {})
    stages = workflow.get("stages", [])
    selected = workflow.get("selected_stage", len(rows)) - 1
    frame, row = frames[selected], rows[selected]
    review = stages[selected] if stages else results.get("decision", {})
    names = [s["name"] for s in stages] if stages else [r["name"] for r in rows]
    checks = [c for c in review.get("checks", []) if c["region"] != "full"]
    check = next((c for c in checks if c["status"] != "aligned"), next(iter(checks), {}))
    regions = row["inspection_regions"]
    native = review.get("native_review", {}) if workflow.get("final") else {}
    name = native.get("region", row.get("primary_region", check.get("region", next(iter(regions)))))
    check = next((item for item in checks if item["region"] == name), {})
    box = regions[name]
    c = Canvas(str(path), pagesize=(660, 800), pageCompression=1)
    c.setTitle("Image enlargement review")
    teal = "#196D65"
    ink = "#182D32"

    def label(x, y, value, size=12, bold=False, color=ink):
        c.setFillColor(colors.HexColor(color))
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(x, y, value)

    def para(x, top, width, value, limit=220, size=12):
        text = shorten(value, width=limit, placeholder="...")
        p = Paragraph(escape(text), ParagraphStyle("body", fontName="Helvetica",
                      fontSize=size, leading=size*1.3, textColor=colors.HexColor(ink)))
        _, height = p.wrap(width, 800)
        p.drawOn(c, x, top-height)

    def header(section, title):
        label(34, 756, "imenlarge   /   " + section, 12, True, teal)
        label(34, 711, title, 27, True)
        c.setStrokeColor(colors.HexColor("#AFC2BF"))
        c.line(34, 693, 626, 693)

    def end():
        c.line(34, 49, 626, 49)
        label(34, 30, "Image enlargement review   /   Detailed evidence in review.html", 10)
        label(600, 30, str(c.getPageNumber()), 10)
        c.showPage()

    def mapped(im):
        return native_box(im, original.size, box)

    def picture(im, x, top, w, h, mark=False):
        scale = min(w/im.width, h/im.height)
        dw, dh = im.width*scale, im.height*scale
        preview = im.copy()
        preview.thumbnail((max(1, int(dw*2.5)), max(1, int(dh*2.5))), Image.Resampling.LANCZOS)
        if mark:
            left, up, right, bottom = mapped(preview)
            ImageDraw.Draw(preview).rectangle((left, up, right-1, bottom-1),
                                               outline="#FFCC48", width=max(1, preview.width//160))
        buf = BytesIO()
        preview.save(buf, "JPEG", quality=94, subsampling=0) if mark else preview.save(buf, "PNG")
        c.drawImage(ImageReader(buf), x+(w-dw)/2, top-h+(h-dh)/2, dw, dh)

    # A matching field of view at native pixel density for each frame.
    # Centering a bounded window keeps large crops practical to open at 100%.
    recent_parent = stages[selected].get("parent_stage") if stages else None
    comparison = workflow.get("comparison_stage")
    indices = list(dict.fromkeys([0, (recent_parent or 1)-1, (comparison or 1)-1, selected]))
    if not workflow.get("final"):
        indices = list(range(len(frames)))
    native_crops = [original.crop(box)]
    captions = ["Source pixels"]
    for i in indices:
        native_crops.append(frames[i].crop(mapped(frames[i])))
        captions.append(shorten(names[i], width=52, placeholder="..."))
    # Match the native sampling grid and use the same centered window for both images.
    rect = mapped(frame)
    source_at_output = original.resize(frame.size, Image.Resampling.LANCZOS).crop(rect)
    native_crops.insert(1, source_at_output)
    captions.insert(1, "Source at output scale (Lanczos)")
    max_width, max_height = 630, 440
    windows = []
    for crop in native_crops:
        w, h = min(crop.width, max_width), min(crop.height, max_height)
        x, y = (crop.width-w)//2, (crop.height-h)//2
        windows.append(crop.crop((x, y, x+w, y+h)))
    measure = ImageDraw.Draw(windows[0])
    widths = [max(im.width, int(measure.textlength(title))+1) for im, title in zip(windows, captions)]
    sheet = Image.new("RGB", (sum(w+24 for w in widths)+24,
                              max(im.height for im in windows)+64), "#ffffff")
    draw = ImageDraw.Draw(sheet)
    x = 12
    for im, caption, width in zip(windows, captions, widths):
        draw.text((x, 8), caption, fill=ink)
        sheet.paste(im, (x, 38))
        x += width+24
    sheet.save(path.with_name("native-crops.png"))

    verdict = {"revise": "Revision in progress", "retain": "Retained for comparison"}
    if workflow.get("final"):
        verdict["retain"] = "Selected enlargement"
    header("Final review" if workflow.get("final") else "Working review", verdict.get(review.get("action"), "Source and output comparison"))
    para(34, 677, 592, workflow.get("selection_reason") or check.get("candidate_evidence") or
         "Compare the marked region at both resolutions. Measurements describe source-grid agreement.", limit=325)
    left = frames[comparison-1] if comparison else original
    left_title = names[comparison-1] if comparison else "Source"
    for x, im, title in [(34, left, left_title), (337, frame, names[selected])]:
        picture(im, x, 608, 285, 242, True)
        label(x, 345, f"{shorten(title, width=26, placeholder='...')}   /   {im.width} x {im.height} px", 12, True)
        picture(im.crop(mapped(im)), x, 277, 285, 133)
    para(34, 321, 592, "Marked region: " + name, 75)
    left_note = check.get("source_evidence", "Source crop at the marked coordinates.")
    if comparison:
        peer = next((v for v in stages[comparison-1]["checks"] if v["region"] == name), {})
        left_note = peer.get("candidate_evidence", stages[comparison-1]["reason"])
    para(34, 127, 282, left_note, 125)
    para(337, 127, 286, check.get("candidate_evidence", "Native output crop at the same field of view."), 125)
    end()

    if native_reference is not None:
        benchmark = results["native_reference"]
        header("Reference comparison", "Compare the supplied native reference")
        titles = [("Source", original), (names[selected], frame), ("Supplied reference", native_reference)]
        for index, (title, im) in enumerate(titles):
            x = 34 + index*199
            para(x, 667, 187, title, 52, 11)
            picture(im, x, 618, 183, 195, True)
            picture(im.crop(mapped(im)), x, 402, 183, 165)
        para(34, 218, 592, "Whole image and matching region: " + name, 130)
        for line, region in enumerate(dict.fromkeys(["full", name])):
            if region in benchmark["wavelet"]:
                selected_mae = row["wavelet"][region][0]["low_rgb_mae"]
                reference_mae = benchmark["wavelet"][region][0]["low_rgb_mae"]
                para(34, 171-line*43, 592, f"{region} / A1 RGB MAE at source size: "
                     f"selected {selected_mae:.2f}, supplied reference {reference_mae:.2f}.", 170)
        end()

    if workflow.get("final"):
        header("Native detail", "Detail at delivery size")
        para(34, 675, 592, name + " / " + names[selected])
        selected_crop = frame.crop(rect)
        width, height = min(276, selected_crop.width), min(210, selected_crop.height)
        x = (selected_crop.width-width)//2
        y = (selected_crop.height-height)//2
        window = (x, y, x+width, y+height)
        for left, crop, title in [(34, source_at_output, "Lanczos enlargement"),
                                  (337, selected_crop, "Selected output")]:
            label(left, 600, title, 13, True)
            picture(crop.crop(window), left, 570, width, height)
        para(34, 315, 590, native["detail_gain"], 340)
        para(34, 195, 590, native["continuity"], 340)
        end()

    baseline = (comparison or recent_parent or 1) - 1
    projected = frame.resize(original.size, Image.Resampling.LANCZOS)
    difference = np.asarray(projected, dtype=float) - np.asarray(original, dtype=float)
    absolute = np.abs(difference).mean(axis=2)
    luma = difference @ np.array([0.299, 0.587, 0.114])
    heat = magnitude(absolute)
    direction = signed(luma)
    overlay = Image.blend(original, projected, 0.5)

    x0, y0, x1, y1 = box
    local_diff = difference[y0:y1, x0:x1]
    header("Resize round-trip test", "How much changes after downsampling?")
    para(34, 676, 592, f"{names[selected]} ({frame.width} x {frame.height})  ->  Lanczos downsample ({original.width} x {original.height})  ->  subtract original at matching pixels. Values below use 8-bit red, green and blue channels before any smoothing.")
    for x, field, title in [(34, difference, "Whole frame"), (337, local_diff, "Marked region")]:
        label(x, 615, title, 12, True, teal)
        label(x, 593, f"Mean absolute error  {np.abs(field).mean():.2f} / 255", 14, True)
        label(x, 573, f"Root mean square error  {np.sqrt(np.mean(field**2)):.2f} / 255", 11)
    columns = [(34, overlay, "Half source, half output"), (235, heat, "Absolute color error"),
               (436, direction, "Signed brightness residual")]
    for x, im, title in columns:
        label(x, 536, title, 12, True, teal)
        picture(im, x, 518, 188, 154, True)
        picture(im.crop(box), x, 308, 188, 89)
    para(34, 345, 592, "The gold box locates the enlarged strip below each map: " + name + ".")
    labels = ["Double edges in the blend suggest a shift. Compare the corresponding native crops.",
              "Navy = 0; yellow = 40 or more. Color error is the mean absolute difference of red, green and blue (RGB), each on a 0-255 scale.",
              "Blue = darker output; ivory = equal; rust = brighter output. Colors saturate at -32 and +32 brightness units."]
    for (x, _, _), description in zip(columns, labels):
        para(x, 200, 186, description, 175, 10)
    x0,y0,x1,y1 = box
    local_mean = absolute[y0:y1,x0:x1].mean()
    para(34, 117, 592, f"Average color error is {absolute.mean():.2f} levels over the frame and {local_mean:.2f} in the marked area. Opposite colors along an edge can indicate displacement; an extended single color suggests a tone shift.")
    end()

    if "replay_wavelet" in row:
        header("Observation process", "What survives the encoding replay?")
        process = results.get("recompression") or str(results["brief"].get("projection", {}))
        para(34, 670, 590, f"Replay settings: {process}. All versions use the same projection onto the original grid.")
        versions = [("Selected output", row)]
        if native_reference is not None:
            versions.append(("Supplied reference", results["native_reference"]))
        y = 582
        for title, version in versions:
            label(34, y, title, 14, True)
            y -= 30
            for i, heading in enumerate(["Region", "Projection", "A1", "A2", "A3", "A4"]):
                label([34, 192, 322, 400, 478, 556][i], y, heading, 11, True)
            y -= 22
            for region in dict.fromkeys(["full", name]):
                if region not in version["replay_wavelet"]:
                    continue
                for key, caption in [("wavelet", "Direct resize"), ("replay_wavelet", "Process replay")]:
                    label(34, y, shorten(region, width=23, placeholder="..."), 11)
                    label(192, y, caption, 11)
                    for i, band in enumerate(version[key][region]):
                        label(322+78*i, y, f"{band['low_rgb_mae']:.2f}", 11)
                    y -= 20
            y -= 20
        para(34, 190, 590, "The columns measure mean absolute RGB error from fine to coarse approximations. "
             "Inspect detail bands at the same coordinates in the full evidence. Block patterns and ringing can "
             "change after encoding. A persistent displaced edge calls for checking the physical contour.", 350)
        end()

    header("Local evidence", "What does amplifying the residual reveal?")
    para(34, 674, 592, f"{name}. Source coordinates ({x0}, {y0}) to ({x1}, {y1}), measured from the upper left. The two photographs use the same field of view.")
    for x, im, text in [(34, original.crop(box), "Original region"), (337, frame.crop(mapped(frame)), "Native candidate region")]:
        label(x, 610, text, 13, True, teal)
        picture(im, x, 588, 285, 140)
    h, w = local_diff.shape[:2]
    # Compare subareas on the source grid so the magnified residual has a locator.
    regions_local = []
    for j in range(min(2,h)):
        for i in range(min(3,w)):
            l, r = i*w//min(3,w), (i+1)*w//min(3,w)
            u, b = j*h//min(2,h), (j+1)*h//min(2,h)
            regions_local.append((np.abs(local_diff[u:b,l:r]).mean(), (l,u,r,b)))
    peak, (l,u,r,b) = max(regions_local, key=lambda item: item[0])
    for x, gain in [(34, 1), (337, 4)]:
        residual = Image.fromarray(np.uint8(np.clip(np.rint(128 + gain*local_diff), 0, 255)))
        if gain == 4:
            ImageDraw.Draw(residual).rectangle((l,u,r-1,b-1), outline="#ffcb33")
        label(x, 403, f"Signed color residual at {gain}x gain", 13, True, teal)
        picture(residual, x, 380, 285, 140)
    para(34, 214, 592, "Mid-gray means equal channel values. The right view multiplies each red, green and blue difference by four before adding mid-gray. This reveals faint color casts and displaced edges; saturated pixels reach the display limit.", 250)
    para(34, 128, 592, check.get("residual_evidence") or f"The gold box marks the highest-error subarea of this crop: {peak:.2f} levels on average, versus {local_mean:.2f} across the crop. Gain alters visibility; the underlying errors stay the same.", 220)
    end()

    header("Smoothed color", "Did the final step improve color?")
    para(34, 674, 592, "Each column compares red, green and blue after progressively stronger smoothing. Read across a row for scale and down a column to compare frames.")
    for k, (im, caption) in enumerate([(original, "Source"), (frames[baseline], shorten(names[baseline], width=28, placeholder="...")), (frame, shorten(names[selected], width=28, placeholder="..."))]):
        picture(im, 35+203*k, 607, 173, 103)
        label(35+203*k, 485, caption, 11, True, teal)
    for j, tag in enumerate(("1 / finest", "2", "3", "4 / broadest")):
        label(105+j*131, 453, tag, 13, True, teal)
    indices = list(dict.fromkeys([baseline, selected]))
    for line, i in enumerate(indices):
        y = 439-line*112
        para(34, y-33, 68, names[i], 30, 9)
        for j, heatmap in enumerate(maps[i]):
            x = 105+j*131
            picture(heatmap, x, y, 119, 78)
            mae = rows[i]["wavelet"]["full"][j]["low_rgb_mae"]
            label(x, y-94, f"Mean {mae:.2f}", 11)
    for j in range(101):
        c.setFillColor(colors.linearlyInterpolatedColor(colors.HexColor("#122942"),
                       colors.HexColor("#ffd36f"), 0, 100, j))
        c.rect(107+j*1.4, 199, 1.5, 9, fill=1, stroke=0)
    label(106, 181, "0", 10)
    label(227, 181, "40+", 10)
    para(270, 216, 350, "Mean absolute error (MAE) averages the magnitudes of the channel differences. Lower is closer. Colors and units match the preceding heatmap.", 170, 11)
    coarse = row["wavelet"]["full"][-1]["low_rgb_mae"]
    report_line = f"At the broadest scale, {names[selected]} differs from the source by {coarse:.2f} color levels on average."
    if baseline != selected:
        previous = rows[baseline]["wavelet"]["full"][-1]["low_rgb_mae"]
        report_line += f" {names[baseline]} differs by {previous:.2f}. The change is {coarse-previous:+.2f} levels."
    para(34, 147, 592, report_line)
    para(34, 108, 592, "Smoothing largely removes fine texture. The next page measures the detail removed at each step.")
    end()

    header("Wavelet decomposition", "Which local details agree?")
    para(34, 675, 592, f"Enlarged region: {name}. Each row shows the brightness detail removed by a smoothing step. Read from fine texture (row 1) to broader contours (row 4).")
    for x,title in [(34,"Scale"),(102,"Source"),(232,"Output"),(362,"Output - source"),(499,"Agreement")]:
        label(x,609,title,12,True,teal)
    pairs = zip(wavelet(original), wavelet(projected), row["wavelet"][name])
    for j, ((_, source_band), (_, output_band), score) in enumerate(pairs, 1):
        top = 590-(j-1)*100
        label(34,top-31,str(j),16,True)
        for x,band in [(102,source_band),(232,output_band),(362,output_band-source_band)]:
            picture(signed(band[y0:y1,x0:x1]),x,top,122,86)
        corr = score["detail_luma_r"]
        label(499,top-28,"r = undefined" if corr is None else f"r = {corr:.3f}",11,True)
        label(499,top-48,f"MAE = {score['detail_luma_mae']:.2f}",11)
    para(34, 184, 592, "Ivory is zero detail, blue is negative, and rust is positive. Endpoints are -32 and +32 brightness levels. In the difference column, pale areas agree; colored outlines locate a mismatch.", 230, 11)
    para(34, 127, 592, "Pearson correlation (r) measures whether variations line up: +1 is perfect alignment, 0 is uncorrelated, and -1 is inverted. A constant band has undefined correlation. MAE gives the size of the difference in brightness levels.", 260, 11)
    end()
    for start in range(0, len(rows), 4):
        header("Processing record", "Compare the same region across frames")
        para(34, 671, 592, f"Follow {name} through each candidate. Each crop uses the same source coordinates.")
        for i in range(start, min(start+4, len(rows))):
            y = 622-(i-start)*141
            stage = stages[i] if stages else {}
            parent = stage.get("parent_stage")
            para(34, y, 119, names[i], 44, 11)
            para(34, y-30, 120, stage.get("tool", "Measured output"), 48, 11)
            if stages:
                origin = names[parent-1] if parent else "source"
                label(34, y-98, "From " + shorten(origin, width=19, placeholder="..."), 10)
                label(34, y-112, stage["action"].capitalize(), 10)
            picture(frames[i].crop(mapped(frames[i])), 159, y, 213, 107)
            local = next((v for v in stage.get("checks", []) if v["region"] == name), {})
            para(393, y, 230, local.get("candidate_evidence") or rows[i]["findings"][0], 140)
            if stages:
                para(393, y-74, 230, stage["reason"], 78, 10)
            c.line(34, y-121, 626, y-121)
        end()

    c.save()
