import io
import sys
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
        templates = {
            "asav": "Cisco ASAv",
            "fortinet": "Fortinet FortiGate",
            "clearpass": "Aruba ClearPass",
            "vtmgmt": "Cisco vManage",
            "newimage": "Generic QEMU",
        }
        for prefix, name in templates.items():
            (self.eve / f"html/templates/intel/{prefix}.yml").write_text(
                f"---\ntype: qemu\nname: {name}\ndescription: {name}\n"
            )
        wrapper = self.eve / "wrappers/unl_wrapper"
        wrapper.parent.mkdir(parents=True)
        wrapper.write_text("#!/bin/sh\nexit 0\n")
        wrapper.chmod(0o755)
        self.c = ForgeCore(str(self.eve), str(self.state))

    def tearDown(self):
        self.td.cleanup()

    def _upload_bytes(self, filename: str, data: bytes, uid: str = "u1"):
        self.c.prepare_upload(uid, filename, len(data))
        self.c.append_upload(uid, 0, data)
        self.c.finish_upload(uid)
        return self.c.analyze(uid)

    def test_templates_and_inference(self):
        t = {x["prefix"]: x for x in self.c.discover_templates()}
        self.assertEqual(t["asav"]["default_disk"], "virtioa.qcow2")
        self.assertEqual(t["asav"]["disk_layout"], ["virtioa.qcow2"])

    def test_zip_traversal_blocked(self):
        z = Path(self.td.name) / "x.zip"
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("../evil.qcow2", b"x")
        dest = Path(self.td.name) / "dest"
        dest.mkdir()
        with self.assertRaises(ForgeError):
            self.c._extract_zip(z, dest)

    def test_sanitize(self):
        self.assertEqual(self.c.sanitize_name(" NX OS / 10.4 "), "NX-OS-10.4")
        self.assertEqual(self.c._extract_version("vjunos-router-24.2R1.17.qcow2"), "24.2R1.17")

    def test_smart_detect_fortigate(self):
        a = self._upload_bytes("FortiGate_VM64_KVM-v7.6.3.qcow2", b"qcow")
        p = a["smart_plan"]
        self.assertEqual(p["template"], "fortinet")
        self.assertEqual(p["version"], "7.6.3")
        self.assertEqual(p["disks"][0]["disk_name"], "virtioa.qcow2")
        self.assertGreaterEqual(p["confidence"], 80)
        self.assertTrue(p["template_available"])

    def test_smart_multidisk_clearpass(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("ClearPass-6.12-disk1.qcow2", b"a")
            z.writestr("ClearPass-6.12-disk2.qcow2", b"bb")
        a = self._upload_bytes("Aruba-ClearPass-6.12.zip", buf.getvalue(), "u2")
        p = a["smart_plan"]
        self.assertEqual(p["template"], "clearpass")
        self.assertEqual([d["disk_name"] for d in p["disks"]], ["hda.qcow2", "hdb.qcow2"])

    def test_vmanage_generates_second_disk(self):
        a = self._upload_bytes("viptela-vmanage-19.2.3-genericx86-64.qcow2", b"x", "u3")
        p = a["smart_plan"]
        self.assertEqual(p["template"], "vtmgmt")
        self.assertEqual(p["version"], "19.2.3")
        self.assertEqual(p["generated_disks"], [{"disk_name": "virtiob.qcow2", "size_gb": 100}])

    def test_existing_target_detected(self):
        target = self.eve / "addons/qemu/fortinet-7.6.3"
        target.mkdir(parents=True)
        (target / "virtioa.qcow2").write_bytes(b"old")
        a = self._upload_bytes("FortiGate-7.6.3.qcow2", b"new", "u4")
        p = a["smart_plan"]
        self.assertTrue(p["target_exists"])
        self.assertIn("fortinet-7.6.3", p["existing_versions"])

    def test_preserve_eve_disk_name_from_archive(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("FortiGate-7.4/virtioa.qcow2", b"a")
            z.writestr("FortiGate-7.4/virtiob.qcow2", b"b")
        a = self._upload_bytes("FortiGate-7.4.zip", buf.getvalue(), "u5")
        p = a["smart_plan"]
        self.assertEqual([d["disk_name"] for d in p["disks"]], ["virtioa.qcow2", "virtiob.qcow2"])

    def test_smart_install_multidisk(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("ClearPass-6.12-disk1.qcow2", b"disk-a")
            z.writestr("ClearPass-6.12-disk2.qcow2", b"disk-b")
        a = self._upload_bytes("Aruba-ClearPass-6.12.zip", buf.getvalue(), "u6")
        p = a["smart_plan"]
        spec = {
            "upload_id": "u6", "smart_mode": True, "template": p["template"], "version": p["version"],
            "disks": [{"relpath": d["relpath"], "disk_name": d["disk_name"]} for d in p["disks"]],
            "generated_disks": p["generated_disks"], "cdrom_relpath": p["cdrom_relpath"],
            "backup_existing": True, "dry_run": False,
        }
        logs, progress = [], []
        result = self.c.install(spec, logs.append, progress.append)
        target = Path(result["target_dir"])
        self.assertEqual((target / "hda.qcow2").read_bytes(), b"disk-a")
        self.assertEqual((target / "hdb.qcow2").read_bytes(), b"disk-b")
        self.assertEqual(progress[-1], 100)

    def test_smart_install_generated_disk(self):
        a = self._upload_bytes("viptela-vmanage-19.2.3-genericx86-64.qcow2", b"primary", "u7")
        p = a["smart_plan"]
        fake = Path(self.td.name) / "qemu-img"
        fake.write_text('#!/bin/sh\nif [ "$1" = create ]; then : > "$4"; exit 0; fi\nexit 1\n')
        fake.chmod(0o755)
        self.c.find_qemu_img = lambda: str(fake)
        spec = {
            "upload_id": "u7", "smart_mode": True, "template": p["template"], "version": p["version"],
            "disks": [{"relpath": d["relpath"], "disk_name": d["disk_name"]} for d in p["disks"]],
            "generated_disks": p["generated_disks"], "cdrom_relpath": None,
            "backup_existing": True, "dry_run": False,
        }
        result = self.c.install(spec, lambda _: None, lambda _: None)
        target = Path(result["target_dir"])
        self.assertTrue((target / "virtioa.qcow2").exists())
        self.assertTrue((target / "virtiob.qcow2").exists())


if __name__ == "__main__":
    unittest.main()
