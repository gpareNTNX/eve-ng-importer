import io
import os
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from core import ForgeCore, ForgeError

class TestCore(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        r = Path(self.td.name)
        self.eve = r / "eve"
        self.state = r / "state"
        (self.eve / "addons/qemu/asav-old").mkdir(parents=True)
        (self.eve / "addons/qemu/asav-old/virtioa.qcow2").write_bytes(b"x")
        (self.eve / "html/templates/intel").mkdir(parents=True)
        (self.eve / "html/templates/intel/asav.yml").write_text("---\ntype: qemu\nname: ASAv\ndescription: Cisco ASAv\n")
        self.c = ForgeCore(str(self.eve), str(self.state))
    def tearDown(self): self.td.cleanup()
    def test_templates_and_inference(self):
        t = self.c.discover_templates()
        self.assertEqual(t[0]["prefix"], "asav")
        self.assertEqual(t[0]["default_disk"], "virtioa.qcow2")
    def test_zip_traversal_blocked(self):
        z = Path(self.td.name)/"x.zip"
        with zipfile.ZipFile(z,"w") as f: f.writestr("../evil.qcow2", b"x")
        dest = Path(self.td.name)/"dest"; dest.mkdir()
        with self.assertRaises(ForgeError): self.c._extract_zip(z,dest)
    def test_sanitize(self):
        self.assertEqual(self.c.sanitize_name(" NX OS / 10.4 "), "NX-OS-10.4")

if __name__ == "__main__": unittest.main()
