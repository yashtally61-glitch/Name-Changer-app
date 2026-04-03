import streamlit as st
import io
import pdfplumber
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, NameObject, DictionaryObject
from reportlab.pdfbase import pdfmetrics

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Aashirwad Garments - Challan Converter", layout="centered")

st.title("🧵 Aashirwad Garments")
st.subheader("Challan PDF Converter")
st.markdown(
    "Upload a **Yash Gallery** job work challan PDF and download it "
    "rebranded as **Aashirwad Garments** — only the company details change, "
    "everything else stays exactly the same."
)

# ── New values ────────────────────────────────────────────────────────────────
NEW_COMPANY = "Aashirwad Garments"
NEW_ADDRESS = "Plot No - 22, Tantiyawas, Birij Vihar, Amber, Jaipur 303704"
NEW_GSTIN   = "GSTIN : 08ARNPK0658G1ZL"
NEW_SIG     = "For Aashirwad Garments"

# Strings to search for in the old PDF (partial match)
SEARCH_COMPANY = "Yash Gallery"
SEARCH_ADDRESS = "Tantiyawas"
SEARCH_GSTIN   = "08AABCY3804E1ZJ"
SEARCH_SIG     = "For Yash Gallery"


# ── pdfplumber helpers ────────────────────────────────────────────────────────

def find_line_bbox(words, search: str, y_tol: float = 3.0):
    """
    Find the first word containing `search`, then collect all words on
    the same horizontal line (within y_tol pts). Returns merged bbox
    (x0, top, x1, bottom) in pdfplumber coordinates, or None.
    """
    search_lo = search.lower()
    anchor = next((w for w in words if search_lo in w["text"].lower()), None)
    if anchor is None:
        return None
    line = [w for w in words if abs(w["top"] - anchor["top"]) <= y_tol]
    return (
        min(w["x0"]     for w in line),
        min(w["top"]    for w in line),
        max(w["x1"]     for w in line),
        max(w["bottom"] for w in line),
    )


# ── pypdf helpers ─────────────────────────────────────────────────────────────

def add_fonts_to_page(page) -> None:
    if "/Resources" not in page:
        page[NameObject("/Resources")] = DictionaryObject()
    res = page["/Resources"]
    if "/Font" not in res:
        res[NameObject("/Font")] = DictionaryObject()
    fd = res["/Font"]
    for key, base in [("/FHB", "/Helvetica-Bold"), ("/FHR", "/Helvetica")]:
        if NameObject(key) not in fd:
            d = DictionaryObject()
            d[NameObject("/Type")]     = NameObject("/Font")
            d[NameObject("/Subtype")]  = NameObject("/Type1")
            d[NameObject("/BaseFont")] = NameObject(base)
            d[NameObject("/Encoding")] = NameObject("/WinAnsiEncoding")
            fd[NameObject(key)] = d


def get_raw_content(page) -> bytes:
    c = page.get("/Contents")
    if c is None:
        return b""
    c = c.get_object()
    if isinstance(c, ArrayObject):
        return b"\n".join(item.get_object().get_data() for item in c)
    return c.get_data()


def set_page_content(page, data: bytes) -> None:
    c = page["/Contents"]
    if isinstance(c, ArrayObject):
        first = c[0].get_object()
        first.set_data(data)
        page[NameObject("/Contents")] = c[0]
    else:
        c.get_object().set_data(data)


# ── PDF drawing primitives ────────────────────────────────────────────────────

def white_rect(sx, sy, sw, sh) -> bytes:
    return (f"q\n1 1 1 rg\n{sx:.4f} {sy:.4f} {sw:.4f} {sh:.4f} re\nf\nQ\n").encode()


def bt_block(sx, sy, font_key, font_size, text) -> bytes:
    esc = text.replace("\\","\\\\").replace("(","\\(").replace(")","\\)")
    return (
        f"q\n0 0 0 rg\n"
        f"BT\n/{font_key} {font_size:.4f} Tf\n"
        f"1 0 0 -1 {sx:.4f} {sy:.4f} Tm\n"
        f"({esc}) Tj\nET\nQ\n"
    ).encode("latin-1")


def centered_sx(text, font_name, font_size, stream_width) -> float:
    w = pdfmetrics.stringWidth(text, font_name, font_size)
    return (stream_width - w) / 2


# ── Main conversion ───────────────────────────────────────────────────────────

def convert_pdf(input_bytes: bytes) -> bytes:

    # ── 1. Use pdfplumber to DETECT real positions of old text ────────────────
    with pdfplumber.open(io.BytesIO(input_bytes)) as pdf:
        pl  = pdf.pages[0]
        words = pl.extract_words()

        pl_width  = float(pl.width)
        pl_height = float(pl.height)

        bbox_company = find_line_bbox(words, SEARCH_COMPANY)
        bbox_address = find_line_bbox(words, SEARCH_ADDRESS)
        bbox_gstin   = find_line_bbox(words, SEARCH_GSTIN)
        bbox_sig     = find_line_bbox(words, SEARCH_SIG)

    # ── 2. Detect scale: pdfplumber pt width vs pypdf MediaBox width ──────────
    reader  = PdfReader(io.BytesIO(input_bytes))
    mb      = reader.pages[0].mediabox
    pdf_w   = float(mb.width)   # raw PDF units (e.g. 595.32 for A4)
    # pdfplumber always reports in pts; if CTM scales by 0.75 the raw pdf_w
    # will be ~793.76 (=595/0.75). Derive scale = pl_width / pdf_w ... but
    # pdfplumber already accounts for rotation/CTM so pl_width == pdf_w in pts.
    # The content stream however uses a CTM that may scale coords.
    # We detect by comparing pl_width (pts) to the raw stream space width.
    # Common case: CTM is `0.75 0 0 -0.75 0 H cm` → stream_width = pl_w/0.75
    # We infer scale from the fact stream_width * scale = pl_width.
    # Default assumption: scale = 0.75 (covers most Yash Gallery PDFs).
    scale = 0.75
    stream_width = pl_width / scale   # e.g. 793.76

    PAD = 3.0  # padding in pdfplumber pts around each white box

    parts = []

    # ── 3. White-out + redraw header ──────────────────────────────────────────
    header_bboxes = [b for b in [bbox_company, bbox_address, bbox_gstin] if b]
    if header_bboxes:
        # One big white rectangle covering entire header zone
        zone_top    = min(b[1] for b in header_bboxes) - PAD
        zone_bottom = max(b[3] for b in header_bboxes) + PAD
        # In stream space: origin top-left, y increases downward (after CTM flip)
        parts.append(white_rect(
            0,
            zone_top / scale,
            stream_width,
            (zone_bottom - zone_top) / scale
        ))

        font_bold = 14.0
        font_reg  =  8.0

        # Company — centred, bold, large; baseline = old company bottom
        if bbox_company:
            sy = bbox_company[3] / scale
            sx = centered_sx(NEW_COMPANY, "Helvetica-Bold", font_bold, stream_width)
            parts.append(bt_block(sx, sy, "FHB", font_bold, NEW_COMPANY))

        # Address — centred, regular, small; baseline = old address bottom
        if bbox_address:
            sy = bbox_address[3] / scale
            sx = centered_sx(NEW_ADDRESS, "Helvetica", font_reg, stream_width)
            parts.append(bt_block(sx, sy, "FHR", font_reg, NEW_ADDRESS))

        # GSTIN — centred, bold, small; baseline = old GSTIN bottom
        if bbox_gstin:
            sy = bbox_gstin[3] / scale
            sx = centered_sx(NEW_GSTIN, "Helvetica-Bold", font_reg, stream_width)
            parts.append(bt_block(sx, sy, "FHB", font_reg, NEW_GSTIN))

    # ── 4. White-out + redraw signature line ──────────────────────────────────
    if bbox_sig:
        x0, top, x1, bottom = bbox_sig
        # White box exactly over old signature
        parts.append(white_rect(
            (x0 - PAD) / scale,
            (top - PAD) / scale,
            (x1 - x0 + 2 * PAD) / scale,
            (bottom - top + 2 * PAD) / scale,
        ))
        # New sig: right-aligned to same right edge as old text
        font_reg = 8.0
        tw  = pdfmetrics.stringWidth(NEW_SIG, "Helvetica-Bold", font_reg)
        tsx = x1 / scale - tw          # right edge preserved
        tsy = bottom / scale           # baseline preserved
        parts.append(bt_block(tsx, tsy, "FHB", font_reg, NEW_SIG))

    overlay = b"\n".join(parts)

    # ── 5. Apply overlay with pypdf ───────────────────────────────────────────
    writer = PdfWriter()
    writer.clone_reader_document_root(reader)
    page = writer.pages[0]
    add_fonts_to_page(page)
    orig = get_raw_content(page)
    set_page_content(page, orig + b"\n" + overlay)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


# ── Streamlit UI ──────────────────────────────────────────────────────────────

uploaded = st.file_uploader("📂 Upload Yash Gallery Challan PDF", type=["pdf"])

if uploaded:
    st.success(f"✅ Uploaded: **{uploaded.name}**")
    with st.spinner("Converting…"):
        try:
            output_bytes = convert_pdf(uploaded.read())
            st.success("🎉 Converted successfully!")

            st.markdown("### Changes made:")
            st.table({
                "Field":         ["Company Name", "Address", "GSTIN", "Signature"],
                "Original":      [
                    "Yash Gallery Pvt Ltd",
                    "55 TO 64, Tantiyawas, Birij Vihar, Amber, Jaipur 303704 Rajasthan (08)",
                    "GSTIN : 08AABCY3804E1ZJ",
                    "For Yash Gallery Pvt Ltd",
                ],
                "Replaced With": [NEW_COMPANY, NEW_ADDRESS, NEW_GSTIN, NEW_SIG],
            })

            out_name = uploaded.name.replace(".pdf", "_Aashirwad.pdf")
            st.download_button("⬇️ Download Converted PDF",
                               data=output_bytes,
                               file_name=out_name,
                               mime="application/pdf")
        except Exception as e:
            st.error(f"❌ Error: {e}")
            st.exception(e)

st.markdown("---")
st.caption("Aashirwad Garments | Plot No - 22, Tantiyawas, Birij Vihar, Amber, Jaipur 303704 | GSTIN : 08ARNPK0658G1ZL")
