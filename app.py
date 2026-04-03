import streamlit as st
import io
import zlib
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

# ── Constants ─────────────────────────────────────────────────────────────────
# The original PDF stream uses CTM: 0.75 0 0 -0.75 0 841.92 cm
# After this transform: stream space has origin top-left, y increases downward
# pdfplumber coordinates / 0.75 = stream coordinates

def p2s(v):
    """Convert pdfplumber coordinate to stream coordinate."""
    return v / 0.75

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
        f"q\n0 0 0 rg\n"
        f"BT\n/{font_key} {font_size:.4f} Tf\n"
        f"1 0 0.000000 -1 {sx:.4f} {sy:.4f} Tm\n"
        f"({escaped}) Tj\nET\nQ\n"
    ).encode("latin-1")


def centered_sx(text: str, font: str, font_size: float,
                page_stream_width: float = 793.76) -> float:
    """Return stream-space x so that text is horizontally centred."""
    w = pdfmetrics.stringWidth(text, font, font_size)
    return (page_stream_width - w) / 2


def make_overlay(orig_data: bytes) -> bytes:
    """
    Build a PDF content snippet that:
      1. Paints a white rectangle over the header area (covers old company text).
      2. Draws the Aashirwad Garments header text.
      3. Whites-out the old signature and writes the new one.

    All coordinates are in stream space (pdfplumber_coord / 0.75).
    The stream uses CTM: 0.75 0 0 -0.75 0 841.92 cm
    so stream space: origin top-left, y increases downward.

    Key: this overlay is APPENDED to the original stream, so it renders AFTER
    the original content. White rectangles cover the old text, then new text
    is drawn on top — correct visual layering.
    """
    # ── 1. White rectangle covering header (pdfplumber top=0 to 83) ─────────
    # Stream rect: lower-left=(0,0), width=793.76, height=p2s(83)=110.67
    white_header = b"q\n1 1 1 rg\n0 0 793.76 110.67 re\nf\nQ\n"

    # ── 2. New company header text ───────────────────────────────────────────
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
    x_sig = p2s(566.7) - sig_w  # original right edge was at pdfplumber x=566.7

    # ── 3. White rectangle over signature area ───────────────────────────────
    # "For Yash Gallery Pvt Ltd" at pdfplumber top=344.5, bottom=352.6
    # White rect: covers from x=440 to x=595, top=340 to bottom=358
    sig_sy_top = p2s(340)
    sig_height = p2s(358) - sig_sy_top
    white_sig = (
        f"q\n1 1 1 rg\n"
        f"{p2s(440):.2f} {sig_sy_top:.2f} {p2s(595-440):.2f} {sig_height+4:.2f} re\n"
        f"f\nQ\n"
    ).encode()

    parts = [
        white_header,
        # Company name baseline at pdfplumber bottom ≈ 39.1
        bt_block(cx_company, p2s(39.1), "FHB", font_bold, company),
        # Address baseline at pdfplumber bottom ≈ 52.8
        bt_block(cx_address, p2s(52.8), "FHR", font_reg,  address),
        # GSTIN baseline at pdfplumber bottom ≈ 64.0
        bt_block(cx_gstin,   p2s(64.0), "FHB", font_reg,  gstin_text),
        white_sig,
        # Signature baseline at pdfplumber bottom ≈ 352.6
        bt_block(x_sig, p2s(352.6), "FHB", font_reg, sig_text),
    ]
    return b"\n".join(parts)


# ── Main conversion function ──────────────────────────────────────────────────

def convert_pdf(input_bytes: bytes) -> bytes:
    """
    Replace Yash Gallery header / signature with Aashirwad Garments.

    Strategy:
      • Keep the original content stream completely intact.
      • Append a small overlay snippet that:
          - Paints white boxes over the old header and signature text
          - Draws the new Aashirwad Garments text
        Since the overlay is appended, it renders AFTER the original content,
        so white boxes correctly cover old text and new text renders cleanly on top.
      • Register Helvetica / Helvetica-Bold as new font resources (/FHB, /FHR).

    Note: Text extraction tools (like pdfplumber) may still show both old and
    new text since they read raw stream data without simulating visual rendering.
    The output PDF is visually correct — white rectangles properly hide old text.
    """
    reader = PdfReader(io.BytesIO(input_bytes))
    page   = reader.pages[0]

    # 1. Register new fonts
    add_fonts_to_page(page)

    # 2. Fetch original content stream
    obj       = get_content_object(page)
    orig_data = obj.get_data()

    # 3. Build and append overlay
    overlay  = make_overlay(orig_data)
    combined = orig_data + b"\n" + overlay

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
