import xml.etree.ElementTree as ET
import zipfile


def get_ofd_page_count(ofd_path):
    try:
        with zipfile.ZipFile(ofd_path) as archive:
            root = ET.fromstring(archive.read("OFD.xml"))
            namespace = root.tag.partition("}")[0] + "}" if root.tag.startswith("{") else ""
            doc_body = root.find(f".//{namespace}DocBody")
            if doc_body is not None:
                doc_root = doc_body.find(f"{namespace}DocRoot")
                if doc_root is not None and doc_root.text and doc_root.text.strip():
                    document = ET.fromstring(archive.read(doc_root.text.strip()))
                    doc_namespace = (document.tag.partition("}")[0] + "}"
                                     if document.tag.startswith("{") else "")
                    return len(document.findall(f".//{doc_namespace}Page"))

            page_files = [name for name in archive.namelist()
                          if name.startswith("Pages/") and name.endswith(".xml")]
            if page_files:
                return len(page_files)
    except (OSError, ValueError, KeyError, ET.ParseError, zipfile.BadZipFile) as error:
        print(f"Error reading OFD: {error}")
    return -1
