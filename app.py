import streamlit as st
import fitz  # PyMuPDF
import io
import os
from pathlib import Path

st.set_page_config(page_title="Aashirwad Garments - Challan Generator", layout="centered")

st.title("🧵 Aashirwad Garments")
st.subheader("Challan PDF Converter")
st.markdown("Upload a **Yash Gallery** job work challan PDF and download it rebranded as **Aashirwad Garments**.")

# Replacements mapping
REPLACEMENTS = {
    "Yash Gallery Pvt Ltd": "Aashirwad Garments",
    "55 TO 64, Tantiyawas, Birij Vihar, Amber, Jaipur 303704 Rajasthan (08)": "Plot No - 22, Tantiyawas, Birij Vihar, Amber, Jaipur 303704",
    "55 TO 64, Tantiyawas, Birij Vihar, Amber, Jaipur  303704 Rajasthan (08)": "Plot No - 22, Tantiyawas, Birij Vihar, Amber, Jaipur 303704",
    "GSTIN : 08AABCY3804E1ZJ": "GSTIN : 08ARNPK0658G1ZL",
    "GSTIN: 08AABCY3804E1ZJ": "GSTIN : 08ARNPK0658G1ZL",
    "08AABCY3804E1ZJ": "08ARNPK0658G1ZL",
    "For Yash Gallery Pvt Ltd": "For Aashirwad Garments",
}


def replace_text_in_pdf(input_bytes: bytes) -> bytes:
    """Replace text in PDF using PyMuPDF redaction."""
    doc = fitz.open(stream=input_bytes, filetype="pdf")

    for page in doc:
        for old_text, new_text in REPLACEMENTS.items():
            # Search for text instances (case-sensitive)
            instances = page.search_for(old_text)
            for inst in instances:
                # Add redaction annotation to cover old text
                page.add_redact_annot(inst, fill=(1, 1, 1))  # white fill

            page.apply_redactions()

            # Now re-insert new text at the same locations
            instances = page.search_for(old_text)
            # Search again after redaction (won't find old text, so we track separately)

        # Do a second pass: search & redact & re-write
        # We need to track positions before redacting, so restart with fresh approach

    doc.close()

    # --- Better approach: search → record rects → redact → insert new text ---
    doc = fitz.open(stream=input_bytes, filetype="pdf")

    for page in doc:
        replacements_to_do = []

        for old_text, new_text in REPLACEMENTS.items():
            instances = page.search_for(old_text)
            for rect in instances:
                replacements_to_do.append((rect, old_text, new_text))

        # Apply redactions first
        for rect, old_text, new_text in replacements_to_do:
            page.add_redact_annot(rect, fill=(1, 1, 1))

        page.apply_redactions()

        # Now insert new text at recorded positions
        for rect, old_text, new_text in replacements_to_do:
            # Get font size by checking surrounding text blocks
            font_size = 9  # default

            # Try to detect font size from nearby text
            blocks = page.get_text("dict")["blocks"]
            min_dist = float("inf")
            for block in blocks:
                if block["type"] == 0:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            span_rect = fitz.Rect(span["bbox"])
                            dist = abs(span_rect.y0 - rect.y0)
                            if dist < min_dist:
                                min_dist = dist
                                font_size = span["size"]

            # Bold for title (company name)
            font = "helv"
            if old_text in ["Yash Gallery Pvt Ltd", "For Yash Gallery Pvt Ltd"]:
                font = "hebo"  # Helvetica Bold
                if old_text == "Yash Gallery Pvt Ltd":
                    font_size = max(font_size, 14)

            page.insert_text(
                (rect.x0, rect.y1 - 1),
                new_text,
                fontsize=font_size,
                fontname=font,
                color=(0, 0, 0),
            )

    output_buffer = io.BytesIO()
    doc.save(output_buffer)
    doc.close()
    return output_buffer.getvalue()


uploaded_file = st.file_uploader("📂 Upload Yash Gallery Challan PDF", type=["pdf"])

if uploaded_file is not None:
    st.success(f"✅ File uploaded: **{uploaded_file.name}**")

    with st.spinner("Processing PDF..."):
        input_bytes = uploaded_file.read()
        try:
            output_bytes = replace_text_in_pdf(input_bytes)
            st.success("🎉 PDF successfully converted!")

            # Preview info
            st.markdown("### Changes Applied:")
            st.markdown("""
| Original | Replaced With |
|----------|--------------|
| Yash Gallery Pvt Ltd | Aashirwad Garments |
| 55 TO 64, Tantiyawas... | Plot No - 22, Tantiyawas... |
| GSTIN : 08AABCY3804E1ZJ | GSTIN : 08ARNPK0658G1ZL |
| For Yash Gallery Pvt Ltd | For Aashirwad Garments |
""")

            # Download button
            output_filename = uploaded_file.name.replace(".pdf", "_aashirwad.pdf")
            st.download_button(
                label="⬇️ Download Converted PDF",
                data=output_bytes,
                file_name=output_filename,
                mime="application/pdf",
            )

        except Exception as e:
            st.error(f"❌ Error processing PDF: {str(e)}")
            st.exception(e)

st.markdown("---")
st.caption("Aashirwad Garments | Plot No - 22, Tantiyawas, Birij Vihar, Amber, Jaipur 303704 | GSTIN: 08ARNPK0658G1ZL")
