import streamlit as st
import io
from pypdf import PdfReader, PdfWriter

st.set_page_config(page_title="Aashirwad Garments - Challan Generator", layout="centered")

st.title("🧵 Aashirwad Garments")
st.subheader("Challan PDF Converter")
st.markdown("Upload a **Yash Gallery** job work challan PDF and download it rebranded as **Aashirwad Garments**.")

REPLACEMENTS = {
    "Yash Gallery Pvt Ltd": "Aashirwad Garments",
    "55 TO 64, Tantiyawas, Birij Vihar, Amber, Jaipur 303704 Rajasthan (08)": "Plot No - 22, Tantiyawas, Birij Vihar, Amber, Jaipur 303704",
    "55 TO 64, Tantiyawas, Birij Vihar, Amber, Jaipur  303704 Rajasthan (08)": "Plot No - 22, Tantiyawas, Birij Vihar, Amber, Jaipur 303704",
    "GSTIN : 08AABCY3804E1ZJ": "GSTIN : 08ARNPK0658G1ZL",
    "GSTIN: 08AABCY3804E1ZJ": "GSTIN : 08ARNPK0658G1ZL",
    "08AABCY3804E1ZJ": "08ARNPK0658G1ZL",
    "For Yash Gallery Pvt Ltd": "For Aashirwad Garments",
}


def replace_in_stream(data: bytes) -> bytes:
    for old, new in REPLACEMENTS.items():
        for encoding in ["latin-1", "utf-8", "cp1252"]:
            try:
                old_bytes = old.encode(encoding)
                new_bytes = new.encode(encoding)
                data = data.replace(old_bytes, new_bytes)
            except Exception:
                pass
    return data


def replace_text_in_pdf(input_bytes: bytes) -> bytes:
    reader = PdfReader(io.BytesIO(input_bytes))
    writer = PdfWriter()

    for page in reader.pages:
        if "/Contents" in page:
            contents = page["/Contents"]

            # Single stream object
            if hasattr(contents, "get_data"):
                raw = contents.get_data()
                contents._data = replace_in_stream(raw)
                contents._decoded_self = None

            # Array of stream objects
            else:
                try:
                    for item in contents:
                        obj = item.get_object()
                        if hasattr(obj, "get_data"):
                            raw = obj.get_data()
                            obj._data = replace_in_stream(raw)
                            obj._decoded_self = None
                except Exception:
                    pass

        writer.add_page(page)

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


uploaded_file = st.file_uploader("📂 Upload Yash Gallery Challan PDF", type=["pdf"])

if uploaded_file is not None:
    st.success(f"✅ File uploaded: **{uploaded_file.name}**")

    with st.spinner("Processing PDF..."):
        input_bytes = uploaded_file.read()
        try:
            output_bytes = replace_text_in_pdf(input_bytes)
            st.success("🎉 PDF successfully converted!")

            st.markdown("### Changes Applied:")
            st.markdown("""
| Original | Replaced With |
|----------|--------------|
| Yash Gallery Pvt Ltd | Aashirwad Garments |
| 55 TO 64, Tantiyawas... | Plot No - 22, Tantiyawas... |
| GSTIN : 08AABCY3804E1ZJ | GSTIN : 08ARNPK0658G1ZL |
| For Yash Gallery Pvt Ltd | For Aashirwad Garments |
""")

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
