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
PAGE_CX    = PAGE_W_PDF / 2   # Center in PDF user-space

# ── Helpers ───────────────────────────────────────────────────────────────────

def stream_x_centered(text: str, font: str, pdf_size: float) -> float:
    """Calculate stream-space x coordinate for centered text."""
    w = pdfmetrics.stringWidth(text, font, pdf_size)
    return (PAGE_CX - w / 2) / SCALE


def extract_position_from_bt_block(bt_block: bytes) -> tuple:
    """Extract x, y position from a BT...ET block."""
    # Pattern: 1 0 0.000000 -1 X Y Tm
    tm_pattern = rb'1\s+0\s+[\d.]+\s+-1\s+([\d.]+)\s+([\d.]+)\s+Tm'
    match = re.search(tm_pattern, bt_block)
    if match:
        sx = float(match.group(1))
        sy = float(match.group(2))
        return sx, sy
    return None, None


def extract_font_info_from_bt_block(bt_block: bytes) -> tuple:
    """Extract font key and size from a BT...ET block."""
    # Pattern: /FontKey FontSize Tf
    font_pattern = rb'/([A-Z0-9]+)\s+([\d.]+)\s+Tf'
    match = re.search(font_pattern, bt_block)
    if match:
        font_key = match.group(1).decode('latin-1')
        font_size = float(match.group(2))
        return font_key, font_size
    return None, None


def make_bt_block(sx: float, sy: float, font_key: str,
                  font_size_stream: float, text: str) -> bytes:
    """Create a PDF BT...ET text block."""
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return (
        f"BT\n0 Tr\n/{font_key} {font_size_stream:.6f} Tf\n"
        f"1 0 0.000000 -1 {sx:.6f} {sy:.6f} Tm\n"
        f"({escaped}) Tj\nET\n"
    ).encode("latin-1")


def find_block_by_position_and_font(stream_data: bytes, y_pos: float, font_size: float, 
                                   font_num: str = None, x_range: tuple = None) -> tuple:
    """
    Find a BT...ET block by its Y position and font size.
    Returns (start, end, block) or (None, None, None).
    """
    # Find all BT...ET blocks
    bt_blocks = re.findall(rb'BT.*?ET', stream_data, re.DOTALL)
    
    for block in bt_blocks:
        # Extract font info
        font_match = re.search(rb'/F(\d+)\s+([\d.]+)\s+Tf', block)
        # Extract position: 1 0 0.000000 -1 X Y Tm
        tm_match = re.search(rb'1\s+0\s+[\d.]+\s+-1\s+([\d.]+)\s+([\d.]+)\s+Tm', block)
        
        if font_match and tm_match:
            block_font_num = font_match.group(1).decode()
            block_font_size = float(font_match.group(2))
            block_x = float(tm_match.group(1))
            block_y = float(tm_match.group(2))
            
            # Check if this matches our criteria
            y_match = abs(block_y - y_pos) < 5  # Allow 5-point tolerance
            size_match = abs(block_font_size - font_size) < 1
            font_match_check = (font_num is None) or (block_font_num == font_num)
            x_match = (x_range is None) or (x_range[0] <= block_x <= x_range[1])
            
            if y_match and size_match and font_match_check and x_match:
                start = stream_data.find(block)
                end = start + len(block)
                return start, end, block
    
    return None, None, None


def add_helvetica_fonts(page) -> None:
    """Add Helvetica fonts to page resources."""
    resources = page["/Resources"]
    font_dict = resources["/Font"]
    for key, base in [("/FH", "/Helvetica"), ("/FHB", "/Helvetica-Bold")]:
        if key not in font_dict:
            d = DictionaryObject()
            d[NameObject("/Type")] = NameObject("/Font")
            d[NameObject("/Subtype")] = NameObject("/Type1")
            d[NameObject("/BaseFont")] = NameObject(base)
            font_dict[NameObject(key)] = d


def get_content_object(page):
    """Return the content stream object from a page."""
    ref = page.raw_get("/Contents")
    if isinstance(ref, ArrayObject):
        return ref[0].get_object()
    return ref.get_object()


def find_block_by_position_and_font(stream_data: bytes, y_pos: float, font_size: float, 
                                   font_num: str = None, x_range: tuple = None) -> tuple:
    """
    Find a BT...ET block by its Y position and font size.
    Returns (start, end, block) or (None, None, None).
    """
    # Find all BT...ET blocks
    bt_blocks = re.findall(rb'BT.*?ET', stream_data, re.DOTALL)
    
    for block in bt_blocks:
        # Extract font info
        font_match = re.search(rb'/F(\d+)\s+([\d.]+)\s+Tf', block)
        # Extract position: 1 0 0.000000 -1 X Y Tm
        tm_match = re.search(rb'1\s+0\s+[\d.]+\s+-1\s+([\d.]+)\s+([\d.]+)\s+Tm', block)
        
        if font_match and tm_match:
            block_font_num = font_match.group(1).decode()
            block_font_size = float(font_match.group(2))
            block_x = float(tm_match.group(1))
            block_y = float(tm_match.group(2))
            
            # Check if this matches our criteria
            y_match = abs(block_y - y_pos) < 5  # Allow 5-point tolerance
            size_match = abs(block_font_size - font_size) < 1
            font_match_check = (font_num is None) or (block_font_num == font_num)
            x_match = (x_range is None) or (x_range[0] <= block_x <= x_range[1])
            
            if y_match and size_match and font_match_check and x_match:
                start = stream_data.find(block)
                end = start + len(block)
                return start, end, block
    
    return None, None, None


def convert_pdf(input_bytes: bytes) -> bytes:
    """
    Replace Yash Gallery fields with Aashirwad Garments fields.
    This version finds blocks by their position and font characteristics.
    """
    reader = PdfReader(io.BytesIO(input_bytes))
    page = reader.pages[0]
    obj = get_content_object(page)
    dec = obj.get_data()

    # Track replacements to apply in reverse order (to preserve byte positions)
    replacements = []

    # 1. Company name: Y~47.68, Font size 21.28, F1, centered
    start, end, block = find_block_by_position_and_font(dec, 47.68, 21.28, font_num="1")
    if start is not None and block is not None:
        sx, sy = extract_position_from_bt_block(block)
        font_key, font_size = extract_font_info_from_bt_block(block)
        
        if sx and sy and font_key and font_size:
            new_sx = stream_x_centered("Aashirwad Garments", "Helvetica-Bold", font_size * SCALE)
            new_block = make_bt_block(new_sx, sy, font_key, font_size, "Aashirwad Garments")
            replacements.append((start, end, new_block))

    # 2. Address: Y~68.16, Font size 10.72, F2, centered
    start, end, block = find_block_by_position_and_font(dec, 68.16, 10.72, font_num="2")
    if start is not None and block is not None:
        sx, sy = extract_position_from_bt_block(block)
        font_key, font_size = extract_font_info_from_bt_block(block)
        
        if sx and sy and font_key and font_size:
            new_text = "Plot No - 22, Tantiyawas, Birij Vihar, Amber, Jaipur 303704"
            new_sx = stream_x_centered(new_text, "Helvetica", font_size * SCALE)
            new_block = make_bt_block(new_sx, sy, font_key, font_size, new_text)
            replacements.append((start, end, new_block))

    # 3. GSTIN: Y~83.04, Font size 10.72, F1, centered
    start, end, block = find_block_by_position_and_font(dec, 83.04, 10.72, font_num="1")
    if start is not None and block is not None:
        sx, sy = extract_position_from_bt_block(block)
        font_key, font_size = extract_font_info_from_bt_block(block)
        
        if sx and sy and font_key and font_size:
            new_text = "GSTIN : 08ARNPK0658G1ZL"
            new_sx = stream_x_centered(new_text, "Helvetica-Bold", font_size * SCALE)
            new_block = make_bt_block(new_sx, sy, font_key, font_size, new_text)
            replacements.append((start, end, new_block))

    # 4. Signature: Y~457.76 (or nearby), Font size 10.72, F1, X > 550 (right-aligned)
    start, end, block = find_block_by_position_and_font(
        dec, 457.76, 10.72, font_num="1", x_range=(550, 650)
    )
    if start is not None and block is not None:
        sx, sy = extract_position_from_bt_block(block)
        font_key, font_size = extract_font_info_from_bt_block(block)
        
        if sx and sy and font_key and font_size:
            # Right-align: maintain the right edge position
            orig_text = "For Yash Gallery Pvt Ltd"
            new_text = "For Aashirwad Garments"
            
            orig_right = sx * SCALE + pdfmetrics.stringWidth(orig_text, "Helvetica-Bold", font_size * SCALE)
            new_w = pdfmetrics.stringWidth(new_text, "Helvetica-Bold", font_size * SCALE)
            new_sx = (orig_right - new_w) / SCALE
            
            new_block = make_bt_block(new_sx, sy, font_key, font_size, new_text)
            replacements.append((start, end, new_block))

    # Apply replacements in reverse order to preserve byte positions
    replacements.sort(reverse=True, key=lambda x: x[0])
    
    new_dec = bytearray(dec)
    for start, end, new_block in replacements:
        new_dec = new_dec[:start] + bytearray(new_block) + new_dec[end:]

    # Write back compressed data
    obj._data = zlib.compress(bytes(new_dec))
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
