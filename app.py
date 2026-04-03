import streamlit as st
import io
import zlib
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject, NameObject, DictionaryObject,
    DecodedStreamObject, EncodedStreamObject
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFont
from reportlab.pdfbase.ttfonts import TTFont

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Aashirwad Garments - Challan Converter", layout="centered")

st.title("🧵 Aashirwad Garments")
st.subheader("Challan PDF Converter")
st.markdown(
    "Upload a **Yash Gallery** job work challan PDF and download it "
    "rebranded as **Aashirwad Garments** — only the company details change, "
    "everything else stays exactly the same."
)

# ── Constants ─────────────────────────────────────────────────────────────────
def p2s(v):
    """Convert pdfplumber coordinate to stream coordinate."""
    return v / 0.75


# ── Core helpers ──────────────────────────────────────────────────────────────

def add_fonts_to_page(page) -> None:
    """Add Helvetica and Helvetica-Bold as /FHR and /FHB to page resources."""
    if "/Resources" not in page:
        page[NameObject("/Resources")] = DictionaryObject()

    resources = page["/Resources"]

    # Get or create the font dictionary
    if "/Font" not in resources:
        resources[NameObject("/Font")] = DictionaryObject()

    font_dict = resources["/Font"]

    for key, base in [("/FHB", "/Helvetica-Bold"), ("/FHR", "/Helvetica")]:
        if NameObject(key) not in font_dict:
            d = DictionaryObject()
            d[NameObject("/Type")]     = NameObject("/Font")
            d[NameObject("/Subtype")]  = NameObject("/Type1")
            d[NameObject("/BaseFont")] = NameObject(base)
            d[NameObject("/Encoding")] = NameObject("/WinAnsiEncoding")
            font_dict[NameObject(key)] = d


def get_raw_content(page) -> bytes:
    """Decode and return the full content stream bytes from a page."""
    contents = page.get("/Contents")
    if contents is None:
        return b""

    # Resolve if it's an indirect reference
    contents = contents.get_object()

    if isinstance(contents, ArrayObject):
        # Multiple content streams — concatenate all
        parts = []
        for item in contents:
            obj = item.get_object()
            parts.append(obj.get_data())
        return b"\n".join(parts)
    else:
        return contents.get_data()


def set_page_content(page, new_data: bytes) -> None:
    """
    Replace the page's content stream with new_data.
    Works whether /Contents is a single object or an array.
    """
    contents = page.raw_get("/Contents")
    contents_obj = page["/Contents"]

    if isinstance(contents_obj, ArrayObject):
        # Collapse all streams into the first one, discard the rest
        first_obj = contents_obj[0].get_object()
        first_obj.set_data(new_data)
        # Replace array with single reference
        page[NameObject("/Contents")] = contents_obj[0]
    else:
        contents_obj = contents_obj.get_object()
        contents_obj.set_data(new_data)


def bt_block(sx: float, sy: float, font_key: str,
             font_size: float, text: str) -> bytes:
    """
    Emit a BT…ET text block in stream coordinates.
    sx, sy are stream-space coordinates (pdfplumber_coord / 0.75).
    sy should be the BOTTOM of the text (pdfplumber 'bottom' value / 0.75).
    The text matrix uses -1 y-scale to match the CTM flip.
    """
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return (
        f"q\n"
        f"0 0 0 rg\n"
        f"BT\n"
        f"/{font_key} {font_size:.4f} Tf\n"
        f"1 0 0.000000 -1 {sx:.4f} {sy:.4f} Tm\n"
        f"({escaped}) Tj\n"
        f"ET\n"
        f"Q\n"
    ).encode("latin-1")


def centered_sx(text: str, font: str, font_size: float,
                page_stream_width: float = 793.76) -> float:
    """Return stream-space x so that text is horizontally centred."""
    w = pdfmetrics.stringWidth(text, font, font_size)
    return (page_stream_width - w) / 2


def make_overlay() -> bytes:
    """
    Build a PDF content snippet that:
      1. Paints a white rectangle over the header area (covers old company text).
      2. Draws the Aashirwad Garments header text.
      3. Whites-out the old signature and writes the new one.
    """
    # ── 1. White rectangle covering header (pdfplumber top=0 to 83) ──────────
    white_header = b"q\n1 1 1 rg\n0 0 793.76 110.67 re\nf\nQ\n"

    # ── 2. New company header text ────────────────────────────────────────────
    font_bold = 21.28
    font_reg  = 8.0
    company    = "Aashirwad Garments"
    address    = "Plot No - 22, Tantiyawas, Birij Vihar, Amber, Jaipur 303704"
    gstin_text = "GSTIN : 08ARNPK0658G1ZL"
    sig_text   = "For Aashirwad Garments"

    cx_company = centered_sx(company,    "Helvetica-Bold", font_bold)
    cx_address = centered_sx(address,    "Helvetica",      font_reg)
    cx_gstin   = centered_sx(gstin_text, "Helvetica-Bold", font_reg)

    # Signature: right-align to match original
    sig_w = pdfmetrics.stringWidth(sig_text, "Helvetica-Bold", font_reg)
    x_sig = p2s(566.7) - sig_w

    # ── 3. White rectangle over signature area ────────────────────────────────
    sig_sy_top = p2s(340)
    sig_height = p2s(358) - sig_sy_top
    white_sig = (
        f"q\n1 1 1 rg\n"
        f"{p2s(440):.2f} {sig_sy_top:.2f} {p2s(595-440):.2f} {sig_height+4:.2f} re\n"
        f"f\nQ\n"
    ).encode()

    parts = [
        white_header,
        bt_block(cx_company, p2s(39.1), "FHB", font_bold, company),
        bt_block(cx_address, p2s(52.8), "FHR", font_reg,  address),
        bt_block(cx_gstin,   p2s(64.0), "FHB", font_reg,  gstin_text),
        white_sig,
        bt_block(x_sig, p2s(352.6), "FHB", font_reg, sig_text),
    ]
    return b"\n".join(parts)


# ── Main conversion function ───────────────────────────────────────────────────

def convert_pdf(input_bytes: bytes) -> bytes:
    """
    Replace Yash Gallery header / signature with Aashirwad Garments.
    Uses PdfWriter.clone_reader_document_root for proper indirect object handling.
    """
    reader = PdfReader(io.BytesIO(input_bytes))
    writer = PdfWriter()

    # Clone the entire document so indirect references remain valid
    writer.clone_reader_document_root(reader)

    page = writer.pages[0]

    # 1. Register new fonts on the writer's page
    add_fonts_to_page(page)

    # 2. Read the original content
    orig_data = get_raw_content(page)

    # 3. Build overlay and combine
    overlay  = make_overlay()
    combined = orig_data + b"\n" + overlay

    # 4. Write back using set_data (the correct pypdf API)
    set_page_content(page, combined)

    # 5. Output
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


# ── Streamlit UI ───────────────────────────────────────────────────────────────

uploaded = st.file_uploader("📂 Upload Yash Gallery Challan PDF", type=["pdf"])

if uploaded:
    st.success(f"✅ Uploaded: **{uploaded.name}**")

    with st.spinner("Converting…"):
        try:
            output_bytes = convert_pdf(uploaded.read())
            st.success("🎉 PDF converted successfully!")

            st.markdown("### Changes made:")
            st.table({
                "Field": ["Company Name", "Address", "GSTIN", "Signature Line"],
                "Original": [
                    "Yash Gallery Pvt Ltd",
                    "55 TO 64, Tantiyawas, Birij Vihar, Amber, Jaipur 303704 Rajasthan (08)",
                    "GSTIN : 08AABCY3804E1ZJ",
                    "For Yash Gallery Pvt Ltd",
                ],
                "Replaced With": [
                    "Aashirwad Garments",
                    "Plot No - 22, Tantiyawas, Birij Vihar, Amber, Jaipur 303704",
                    "GSTIN : 08ARNPK0658G1ZL",
                    "For Aashirwad Garments",
                ],
            })

            out_name = uploaded.name.replace(".pdf", "_Aashirwad.pdf")
            st.download_button(
                label="⬇️ Download Converted PDF",
                data=output_bytes,
                file_name=out_name,
                mime="application/pdf",
            )

        except Exception as e:
            st.error(f"❌ Error: {e}")
            st.exception(e)

st.markdown("---")
st.caption(
    "Aashirwad Garments | Plot No - 22, Tantiyawas, Birij Vihar, Amber, Jaipur 303704 "
    "| GSTIN : 08ARNPK0658G1ZL"
)
