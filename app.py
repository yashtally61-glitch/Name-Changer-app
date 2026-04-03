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

# ── Configuration Constants ───────────────────────────────────────────────────
# Adjust these if positioning needs fine-tuning
SCALE      = 0.75
PAGE_W_PDF = 595.32001
STREAM_W   = PAGE_W_PDF / SCALE   # stream-space page width (~793.8)

# Header text positions (Y coordinates in stream space)
COMPANY_Y = 47.68
ADDRESS_Y = 68.16
GSTIN_Y   = 83.04

# White rectangle coordinates for header (x, y, width, height)
# Format: x=left edge, y=top edge, width, height (all in stream coordinates)
HEADER_RECT_1 = (150, 42, 494, 18)   # Company name area
HEADER_RECT_2 = (80, 62, 634, 14)    # Address area
HEADER_RECT_3 = (280, 79, 234, 12)   # GSTIN area

# Signature positioning
SIG_Y = 457.76              # Y position for signature text
SIG_RIGHT_MARGIN = 750      # Right edge for signature alignment

# White rectangle for signature (x, y, width, height)
SIG_RECT = (540, 452, 155, 14)  # Covers "For Yash Gallery Pvt Ltd"

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


def white_rect(x: float, y: float, w: float, h: float) -> bytes:
    """Create a white rectangle at specified coordinates."""
    return f"1 1 1 rg\n{x:.2f} {y:.2f} {w:.2f} {h:.2f} re\nf\n".encode("latin-1")


def centered_x(text: str, font: str, font_size: float) -> float:
    """Return stream-space x so that text is horizontally centred."""
    w = pdfmetrics.stringWidth(text, font, font_size)
    return (STREAM_W - w) / 2


def make_overlay(stream_data: bytes) -> bytes:
    """
    Build a PDF content snippet that overlays new company details.
    
    Strategy:
      1. Paint small white rectangles over ONLY the text that needs replacing
      2. Draw new text in the correct positions
      3. Preserve all borders, lines, and document structure
    
    All coordinates are in stream space (CTM: 0.75 0 0 -0.75 0 841.92 cm)
    """
    # Font sizes
    font_bold  = 21.28  # Company name
    font_reg   = 10.72  # Address, GSTIN, signature
    
    # New company details
    company    = "Aashirwad Garments"
    address    = "Plot No - 22, Tantiyawas, Birij Vihar, Amber, Jaipur 303704"
    gstin_text = "GSTIN : 08ARNPK0658G1ZL"
    sig_text   = "For Aashirwad Garments"

    # Calculate centered X positions
    cx_company = centered_x(company,    "Helvetica-Bold", font_bold)
    cx_address = centered_x(address,    "Helvetica",      font_reg)
    cx_gstin   = centered_x(gstin_text, "Helvetica-Bold", font_reg)

    # Calculate signature X position (right-aligned)
    sig_w = pdfmetrics.stringWidth(sig_text, "Helvetica-Bold", font_reg)
    x_sig = SIG_RIGHT_MARGIN - sig_w

    # Build the overlay
    parts = [
        # White rectangles over old text
        white_rect(*HEADER_RECT_1),  # Company name
        white_rect(*HEADER_RECT_2),  # Address
        white_rect(*HEADER_RECT_3),  # GSTIN
        white_rect(*SIG_RECT),       # Signature
        
        # New text
        bt_block(cx_company, COMPANY_Y, "FHB", font_bold, company),
        bt_block(cx_address, ADDRESS_Y, "FHR", font_reg,  address),
        bt_block(cx_gstin,   GSTIN_Y,   "FHB", font_reg,  gstin_text),
        bt_block(x_sig,      SIG_Y,     "FHB", font_reg,  sig_text),
    ]
    
    return b"".join(parts)


# ── Main conversion function ──────────────────────────────────────────────────

def convert_pdf(input_bytes: bytes) -> bytes:
    """
    Replace Yash Gallery header / signature with Aashirwad Garments.
    
    This function:
      1. Registers Helvetica fonts
      2. Appends an overlay to the existing content stream
      3. Compresses and returns the modified PDF
    """
    reader = PdfReader(io.BytesIO(input_bytes))
    page   = reader.pages[0]

    # 1. Register fonts
    add_fonts_to_page(page)

    # 2. Get original content stream
    obj        = get_content_object(page)
    orig_data  = obj.get_data()

    # 3. Build and append overlay
    overlay    = make_overlay(orig_data)
    combined   = orig_data + b"\n" + overlay

    # 4. Compress and update
    obj._data         = zlib.compress(combined)
    obj._decoded_self = None

    # 5. Write output
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

# ── Adjustment Instructions ──────────────────────────────────────────────────
with st.expander("🔧 Need to adjust positioning?"):
    st.markdown("""
    If the text or borders aren't aligned perfectly, you can adjust the 
    coordinates at the top of the code:
    
    **Header positioning:**
    - `COMPANY_Y`, `ADDRESS_Y`, `GSTIN_Y` - Y positions for text
    - `HEADER_RECT_1/2/3` - White rectangles (x, y, width, height)
    
    **Signature positioning:**
    - `SIG_Y` - Y position for signature text
    - `SIG_RIGHT_MARGIN` - Right edge alignment
    - `SIG_RECT` - White rectangle dimensions
    
    **Tips:**
    - Increase Y values to move text DOWN
    - Decrease Y values to move text UP
    - Adjust rectangle width/height to cover more/less area
    - Keep changes small (try ±2 to ±5 points at a time)
    """)

st.markdown("---")
st.caption(
    "Aashirwad Garments | Plot No - 22, Tantiyawas, Birij Vihar, Amber, Jaipur 303704 "
    "| GSTIN : 08ARNPK0658G1ZL"
)
