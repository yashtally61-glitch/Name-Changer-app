import streamlit as st
import re
import zlib
import io
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, ArrayObject
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="Aashirwad Garments - Challan Converter", layout="centered")

st.title("🧵 Aashirwad Garments")
st.subheader("Challan PDF Converter")
st.markdown(
    "Upload a **Yash Gallery** job work challan PDF and download it "
    "rebranded as **Aashirwad Garments** — only the company details change, "
    "everything else stays exactly the same."
)

# ── Constants ─────────────────────────────────────────────────────────────────
SCALE      = 0.75
PAGE_W_PDF = 595.32001
PAGE_CX    = PAGE_W_PDF / 2   # 297.66  (center in PDF user-space)

# Byte ranges of target BT..ET blocks inside the decompressed content stream.
# These are fixed for every challan exported from Yash Gallery's software
# because the software always produces the same structure.
BLOCK_RANGES = {
    "company":  (3970, 4341),   # "Yash Gallery Pvt Ltd"
    "address":  (4375, 5518),   # address line
    "gstin":    (5552, 5988),   # GSTIN line
    "signature":(18563, 18998), # "For Yash Gallery Pvt Ltd"
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def stream_x_centered(text: str, font: str, pdf_size: float) -> float:
    """Stream-space x so that `text` is horizontally centred on the page."""
    w = pdfmetrics.stringWidth(text, font, pdf_size)
    return (PAGE_CX - w / 2) / SCALE


def stream_x_right_aligned(new_text: str, orig_text: str,
                            orig_sx: float, font: str, pdf_size: float) -> float:
    """Stream-space x so that `new_text` ends at the same right edge as `orig_text`."""
    orig_right = orig_sx * SCALE + pdfmetrics.stringWidth(orig_text, font, pdf_size)
    new_w      = pdfmetrics.stringWidth(new_text, font, pdf_size)
    return (orig_right - new_w) / SCALE


def make_bt_block(sx: float, sy: float, font_key: str,
                  font_size_stream: float, text: str) -> bytes:
    """Return a PDF BT…ET text block as bytes."""
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return (
        f"BT\n0 Tr\n/{font_key} {font_size_stream:.6f} Tf\n"
        f"1 0 0.000000 -1 {sx:.6f} {sy:.6f} Tm\n"
        f"({escaped}) Tj\nET\n"
    ).encode("latin-1")


def add_helvetica_fonts(page) -> None:
    """Add /FH (Helvetica) and /FHB (Helvetica-Bold) to the page font resources."""
    resources  = page["/Resources"]
    font_dict  = resources["/Font"]
    for key, base in [("/FH", "/Helvetica"), ("/FHB", "/Helvetica-Bold")]:
        if key not in font_dict:
            d = DictionaryObject()
            d[NameObject("/Type")]     = NameObject("/Font")
            d[NameObject("/Subtype")]  = NameObject("/Type1")
            d[NameObject("/BaseFont")] = NameObject(base)
            font_dict[NameObject(key)] = d


def get_content_object(page):
    """Return the single content-stream object from a page."""
    ref = page.raw_get("/Contents")
    if isinstance(ref, ArrayObject):
        return ref[0].get_object()
    return ref.get_object()


def convert_pdf(input_bytes: bytes) -> bytes:
    """
    Replace the 4 Yash Gallery fields directly in the PDF content stream
    and return the modified PDF bytes.
    """
    reader  = PdfReader(io.BytesIO(input_bytes))
    page    = reader.pages[0]
    obj     = get_content_object(page)
    dec     = bytearray(obj.get_data())

    # ── Build replacement blocks ──────────────────────────────────────────────

    # 1. Company name  (Block 0) — bold, size 21.28 stream / 15.96 pdf
    sx0 = stream_x_centered("Aashirwad Garments", "Helvetica-Bold", 21.28 * SCALE)
    b0  = make_bt_block(sx0, 47.68, "FHB", 21.28, "Aashirwad Garments")

    # 2. Address  (Block 1) — regular, size 10.72 stream / 8.04 pdf
    sx1 = stream_x_centered(
        "Plot No - 22, Tantiyawas, Birij Vihar, Amber, Jaipur 303704",
        "Helvetica", 10.72 * SCALE
    )
    b1  = make_bt_block(
        sx1, 68.16, "FH", 10.72,
        "Plot No - 22, Tantiyawas, Birij Vihar, Amber, Jaipur 303704"
    )

    # 3. GSTIN  (Block 2) — bold, size 10.72 stream / 8.04 pdf
    sx2 = stream_x_centered("GSTIN : 08ARNPK0658G1ZL", "Helvetica-Bold", 10.72 * SCALE)
    b2  = make_bt_block(sx2, 83.04, "FHB", 10.72, "GSTIN : 08ARNPK0658G1ZL")

    # 4. Signature line  (Block 61) — bold, right-aligned to original right edge
    sx61 = stream_x_right_aligned(
        "For Aashirwad Garments", "For Yash Gallery Pvt Ltd",
        610.56, "Helvetica-Bold", 10.72 * SCALE
    )
    b61 = make_bt_block(sx61, 439.84, "FHB", 10.72, "For Aashirwad Garments")

    # ── Splice into decompressed stream (reverse order keeps offsets valid) ───
    replacements = [
        (*BLOCK_RANGES["signature"], b61),
        (*BLOCK_RANGES["gstin"],     b2),
        (*BLOCK_RANGES["address"],   b1),
        (*BLOCK_RANGES["company"],   b0),
    ]
    new_dec = bytearray(dec)
    for start, end, block in replacements:          # already in reverse order
        new_dec = new_dec[:start] + bytearray(block) + new_dec[end:]

    # ── Write back ────────────────────────────────────────────────────────────
    obj._data         = zlib.compress(bytes(new_dec))
    obj._decoded_self = None

    add_helvetica_fonts(page)

    writer = PdfWriter()
    writer.add_page(page)
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
            st.success("🎉 PDF converted successfully!")

            st.markdown("### Changes made:")
            st.table({
                "Field":    ["Company Name", "Address", "GSTIN", "Signature Line"],
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
