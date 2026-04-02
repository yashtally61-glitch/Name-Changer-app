import streamlit as st
import io
import zlib
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, NameObject, DictionaryObject
from reportlab.pdfbase import pdfmetrics
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
SCALE      = 0.75
PAGE_W_PDF = 595.32001
STREAM_W   = PAGE_W_PDF / SCALE   # stream-space page width (~793.8)

# ── Core helpers ─────────────────────────────────────────────────────────────

def add_fonts_to_page(page) -> None:
    """Add Helvetica and Helvetica-Bold as /FHR and /FHB to page resources."""
    resources = page["/Resources"]
    if "/Font" not in resources:
        resources[NameObject("/Font")] = DictionaryObject()
    font_dict = resources["/Font"]
    for key, base in [("/FHB", "/Helvetica-Bold"), ("/FHR", "/Helvetica")]:
        if key not in font_dict:
            d = DictionaryObject()
            d[NameObject("/Type")]     = NameObject("/Font")
            d[NameObject("/Subtype")]  = NameObject("/Type1")
            d[NameObject("/BaseFont")] = NameObject(base)
            font_dict[NameObject(key)] = d


def get_content_object(page):
    """Return the writable content-stream object from a page."""
    ref = page.raw_get("/Contents")
    if isinstance(ref, ArrayObject):
        return ref[0].get_object()
    return ref.get_object()


def bt_block(x: float, y: float, font_key: str,
             font_size: float, text: str) -> bytes:
    """Emit a simple BT…ET text block in stream coordinates."""
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return (
        f"0 0 0 rg\n"
        f"BT\n/{font_key} {font_size:.4f} Tf\n"
        f"1 0 0.000000 -1 {x:.4f} {y:.4f} Tm\n"
        f"({escaped}) Tj\nET\n"
    ).encode("latin-1")


def centered_x(text: str, font: str, font_size: float) -> float:
    """Return stream-space x so that text is horizontally centred."""
    w = pdfmetrics.stringWidth(text, font, font_size)
    return (STREAM_W - w) / 2


def make_overlay(stream_data: bytes) -> bytes:
    """
    Build a PDF content snippet (in the original stream's coordinate space)
    that:
      1. Paints a white rectangle over the header area.
      2. Draws the Aashirwad Garments header text.
      3. Whites-out the old signature and writes the new one.

    The original stream uses the CTM:  0.75 0 0 -0.75 0 841.92 cm
    so all positions here are in *stream* space (stream_y increases downward).
    """
    # ── 1. White rectangle covering the header (stream y 30 → 115) ──────────
    white_header = b"1 1 1 rg\n0 30 794 86 re\nf\n"

    # ── 2. Company name (stream y 47.68, bold 21.28 pt) ────────────────────
    font_bold  = 21.28
    font_reg   = 10.72
    company    = "Aashirwad Garments"
    address    = "Plot No - 22, Tantiyawas, Birij Vihar, Amber, Jaipur 303704"
    gstin_text = "GSTIN : 08ARNPK0658G1ZL"
    sig_text   = "For Aashirwad Garments"

    cx_company = centered_x(company,    "Helvetica-Bold", font_bold)
    cx_address = centered_x(address,    "Helvetica",      font_reg)
    cx_gstin   = centered_x(gstin_text, "Helvetica-Bold", font_reg)

    # Signature: right-align to stream x ≈ 750
    sig_w = pdfmetrics.stringWidth(sig_text, "Helvetica-Bold", font_reg)
    x_sig = 750 - sig_w

    # ── 3. White rectangle over signature line (stream y ≈ 450–464) ─────────
    white_sig = b"1 1 1 rg\n590 450 200 14 re\nf\n"

    parts = [
        white_header,
        bt_block(cx_company, 47.68,  "FHB", font_bold, company),
        bt_block(cx_address, 68.16,  "FHR", font_reg,  address),
        bt_block(cx_gstin,   83.04,  "FHB", font_reg,  gstin_text),
        white_sig,
        bt_block(x_sig,      457.76, "FHB", font_reg,  sig_text),
    ]
    return b"".join(parts)


# ── Main conversion function ──────────────────────────────────────────────────

def convert_pdf(input_bytes: bytes) -> bytes:
    """
    Replace Yash Gallery header / signature with Aashirwad Garments.

    Strategy:
      • Keep the original content stream completely intact.
      • Append a small overlay snippet that paints white boxes over the
        old text and draws the new text — all in the same coordinate space
        as the original stream, so no transform arithmetic is needed.
      • Register Helvetica / Helvetica-Bold as new font resources (/FHB, /FHR).
    """
    reader = PdfReader(io.BytesIO(input_bytes))
    page   = reader.pages[0]

    # 1. Register new fonts
    add_fonts_to_page(page)

    # 2. Fetch original content stream
    obj        = get_content_object(page)
    orig_data  = obj.get_data()

    # 3. Build and append overlay
    overlay    = make_overlay(orig_data)
    combined   = orig_data + b"\n" + overlay

    # 4. Write back (compressed)
    obj._data         = zlib.compress(combined)
    obj._decoded_self = None

    # 5. Output
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
