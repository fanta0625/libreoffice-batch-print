import tempfile
import unittest
import zipfile
from pathlib import Path

from utils.ofd_page_count import get_ofd_page_count


class OfdPageCountTest(unittest.TestCase):
    def test_supported_namespaces(self):
        for namespace in ("http://www.ofdspec.org", "http://www.ofdspec.org/2016", ""):
            with self.subTest(namespace=namespace), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "sample.ofd"
                xmlns = f' xmlns:ofd="{namespace}"' if namespace else ""
                prefix = "ofd:" if namespace else ""
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr("OFD.xml", (
                        f"<{prefix}OFD{xmlns}><{prefix}DocBody>"
                        f"<{prefix}DocRoot>Doc_0/Document.xml</{prefix}DocRoot>"
                        f"</{prefix}DocBody></{prefix}OFD>"
                    ))
                    archive.writestr("Doc_0/Document.xml", (
                        f"<{prefix}Document{xmlns}><{prefix}Pages>"
                        + "".join(f'<{prefix}Page ID="{i}"/>' for i in range(10))
                        + f"</{prefix}Pages></{prefix}Document>"
                    ))
                self.assertEqual(get_ofd_page_count(path), 10)

    def test_invalid_file_returns_minus_one(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.ofd"
            path.write_bytes(b"not an OFD")
            self.assertEqual(get_ofd_page_count(path), -1)


if __name__ == "__main__":
    unittest.main()
