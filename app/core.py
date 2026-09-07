from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Iterable

SUPPORTED_QEMU = {".qcow2", ".qcow", ".vmdk", ".vdi", ".raw", ".img"}
SUPPORTED_ARCHIVES = {".zip", ".tgz", ".tar.gz", ".tar", ".ova", ".gz"}
SUPPORTED_DIRECT = SUPPORTED_QEMU | {".iso", ".bin", ".image"}
SAFE_DISK_NAMES = re.compile(r"^(?:hd|virtio|virtide|scsi|sata|lsi|megasas)[a-z]\.qcow2$")
SAFE_NAME = re.compile(r"[^A-Za-z0-9._+-]+")


class ForgeError(RuntimeError):
    pass


@dataclass
class Candidate:
    relpath: str
    kind: str
    format: str
    size: int
    sha256: str | None = None


class ForgeCore:
    def __init__(self, eve_root: str = "/opt/unetlab", state_root: str = "/var/lib/eve-image-forge"):
        self.eve_root = Path(eve_root)
        self.state_root = Path(state_root)
        self.upload_root = self.state_root / "uploads"
        self.work_root = self.state_root / "work"
        self.backup_root = self.state_root / "backups"
        for p in (self.upload_root, self.work_root, self.backup_root):
            p.mkdir(parents=True, exist_ok=True)
        self.profiles = self._load_profiles()

    def _load_profiles(self) -> dict:
        p = Path(__file__).with_name("profiles.json")
        return json.loads(p.read_text()) if p.exists() else {}

    @staticmethod
    def sanitize_name(value: str, fallback: str = "image") -> str:
        value = SAFE_NAME.sub("-", value.strip()).strip("-.")
        return value[:128] or fallback

    @staticmethod
    def compound_suffix(path: Path) -> str:
        n = path.name.lower()
        if n.endswith(".tar.gz"):
            return ".tar.gz"
        if n.endswith(".qcow2.gz"):
            return ".gz"
        return path.suffix.lower()

    @staticmethod
    def sha256(path: Path, block: int = 4 * 1024 * 1024) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            while True:
                b = f.read(block)
                if not b:
                    break
                h.update(b)
        return h.hexdigest()

    def cpu_template_dir(self) -> Path | None:
        intel = self.eve_root / "html/templates/intel"
        amd = self.eve_root / "html/templates/amd"
        # Prefer what the kernel actually reports, then whichever path exists.
        try:
            mods = Path("/proc/modules").read_text(errors="ignore")
            if "kvm_amd" in mods and amd.exists():
                return amd
            if "kvm_intel" in mods and intel.exists():
                return intel
        except Exception:
            pass
        if intel.exists():
            return intel
        if amd.exists():
            return amd
        return None

    def discover_templates(self) -> list[dict]:
        d = self.cpu_template_dir()
        rows: list[dict] = []
        if not d:
            return rows
        for yml in sorted(d.glob("*.yml")):
            text = yml.read_text(errors="ignore")
            if not re.search(r"(?m)^\s*type:\s*qemu\s*$", text):
                continue
            name_m = re.search(r"(?m)^\s*name:\s*[\"']?([^\n\"']+)", text)
            desc_m = re.search(r"(?m)^\s*description:\s*[\"']?([^\n\"']+)", text)
            prefix = yml.stem
            rows.append({
                "prefix": prefix,
                "name": (name_m.group(1).strip() if name_m else prefix),
                "description": (desc_m.group(1).strip() if desc_m else ""),
                "default_disk": self.infer_disk_name(prefix),
                "source": str(yml),
            })
        return rows

    def infer_disk_name(self, prefix: str) -> str:
        # First learn from images already installed on THIS EVE server.
        qemu = self.eve_root / "addons/qemu"
        counts: dict[str, int] = {}
        if qemu.exists():
            for folder in qemu.glob(prefix + "-*"):
                if not folder.is_dir():
                    continue
                for f in folder.iterdir():
                    if f.is_file() and SAFE_DISK_NAMES.match(f.name):
                        counts[f.name] = counts.get(f.name, 0) + 1
        if counts:
            return max(counts, key=counts.get)
        if prefix in self.profiles:
            return self.profiles[prefix].get("disk", "hda.qcow2")
        return "hda.qcow2"

    def system_status(self) -> dict:
        qemu_img = self.find_qemu_img()
        tdir = self.cpu_template_dir()
        du = shutil.disk_usage(self.state_root)
        return {
            "eve_root": str(self.eve_root),
            "eve_detected": (self.eve_root / "addons").exists(),
            "qemu_img": qemu_img,
            "fixpermissions": str(self.eve_root / "wrappers/unl_wrapper"),
            "fixpermissions_exists": (self.eve_root / "wrappers/unl_wrapper").exists(),
            "template_dir": str(tdir) if tdir else None,
            "free_bytes": du.free,
            "version": "0.1.0",
        }

    def find_qemu_img(self) -> str | None:
        candidates = ["/opt/qemu/bin/qemu-img", shutil.which("qemu-img")]
        for c in candidates:
            if c and Path(c).exists():
                return str(c)
        return None

    def prepare_upload(self, upload_id: str, filename: str, size: int) -> dict:
        uid = self.sanitize_name(upload_id, "upload")
        f = self.upload_root / f"{uid}.blob"
        meta = self.upload_root / f"{uid}.json"
        if f.exists():
            f.unlink()
        meta.write_text(json.dumps({"filename": Path(filename).name, "size": int(size)}, indent=2))
        f.touch(mode=0o600)
        return {"upload_id": uid, "path": str(f)}

    def append_upload(self, upload_id: str, offset: int, data: bytes) -> int:
        f = self.upload_root / f"{self.sanitize_name(upload_id)}.blob"
        if not f.exists():
            raise ForgeError("Upload inconnu")
        current = f.stat().st_size
        if current != offset:
            raise ForgeError(f"Offset invalide: reçu {offset}, attendu {current}")
        with f.open("ab") as out:
            out.write(data)
        return f.stat().st_size

    def upload_meta(self, upload_id: str) -> tuple[Path, dict]:
        uid = self.sanitize_name(upload_id)
        f = self.upload_root / f"{uid}.blob"
        meta = self.upload_root / f"{uid}.json"
        if not f.exists() or not meta.exists():
            raise ForgeError("Upload introuvable")
        return f, json.loads(meta.read_text())

    def finish_upload(self, upload_id: str) -> dict:
        f, meta = self.upload_meta(upload_id)
        actual = f.stat().st_size
        if actual != int(meta["size"]):
            raise ForgeError(f"Upload incomplet: {actual} / {meta['size']} octets")
        return {"size": actual, "sha256": self.sha256(f), "filename": meta["filename"]}

    def _safe_target(self, base: Path, member: str) -> Path:
        target = (base / member).resolve()
        base_r = base.resolve()
        if target != base_r and base_r not in target.parents:
            raise ForgeError(f"Archive non sécuritaire (path traversal): {member}")
        return target

    def _extract_zip(self, src: Path, dest: Path) -> None:
        with zipfile.ZipFile(src) as z:
            for info in z.infolist():
                target = self._safe_target(dest, info.filename)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                # Reject symlinks embedded in ZIP.
                mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode):
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as inp, target.open("wb") as out:
                    shutil.copyfileobj(inp, out, 4 * 1024 * 1024)

    def _extract_tar(self, src: Path, dest: Path) -> None:
        # Manual extraction keeps compatibility with the Python versions shipped
        # by current and older EVE-NG releases while still preventing traversal.
        with tarfile.open(src, "r:*") as t:
            for m in t.getmembers():
                target = self._safe_target(dest, m.name)
                if m.issym() or m.islnk() or m.isdev():
                    continue
                if m.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if not m.isfile():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                source = t.extractfile(m)
                if source is None:
                    continue
                with source, target.open("wb") as out:
                    shutil.copyfileobj(source, out, 4 * 1024 * 1024)

    def _decompress_gz(self, src: Path, dest: Path, original_name: str) -> Path:
        out_name = original_name[:-3] if original_name.lower().endswith(".gz") else "payload"
        out = dest / Path(out_name).name
        with gzip.open(src, "rb") as inp, out.open("wb") as o:
            shutil.copyfileobj(inp, o, 4 * 1024 * 1024)
        return out

    def extract_upload(self, upload_id: str) -> tuple[Path, dict]:
        blob, meta = self.upload_meta(upload_id)
        uid = self.sanitize_name(upload_id)
        work = self.work_root / uid
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(parents=True, mode=0o700)
        original = work / Path(meta["filename"]).name
        # Hardlink if possible so a direct image is not duplicated; copy otherwise.
        try:
            os.link(blob, original)
        except OSError:
            shutil.copy2(blob, original)
        suffix = self.compound_suffix(original)
        extracted = work / "extracted"
        extracted.mkdir()
        if suffix == ".zip":
            self._extract_zip(original, extracted)
        elif suffix in {".tgz", ".tar.gz", ".tar", ".ova"}:
            self._extract_tar(original, extracted)
        elif suffix == ".gz":
            self._decompress_gz(original, extracted, meta["filename"])
        else:
            # Direct image: use original itself as candidate.
            return work, meta
        return work, meta

    def classify(self, p: Path) -> tuple[str, str] | None:
        n = p.name.lower()
        if n.endswith(".qcow2"):
            return "qemu", "qcow2"
        if n.endswith(".qcow"):
            return "qemu", "qcow"
        if n.endswith(".vmdk"):
            return "qemu", "vmdk"
        if n.endswith(".vdi"):
            return "qemu", "vdi"
        if n.endswith(".raw") or n.endswith(".img"):
            return "qemu", "raw"
        if n.endswith(".iso"):
            return "qemu-iso", "iso"
        if n.endswith(".bin"):
            return "iol", "bin"
        if n.endswith(".image"):
            return "dynamips", "image"
        return None

    def analyze(self, upload_id: str) -> dict:
        work, meta = self.extract_upload(upload_id)
        root = work / "extracted"
        scan_root = root if any(root.iterdir()) else work
        candidates: list[Candidate] = []
        for p in scan_root.rglob("*"):
            if not p.is_file():
                continue
            c = self.classify(p)
            if not c:
                continue
            kind, fmt = c
            candidates.append(Candidate(
                relpath=str(p.relative_to(work)),
                kind=kind,
                format=fmt,
                size=p.stat().st_size,
            ))
        # Direct-file fallback: rglob includes original.
        candidates.sort(key=lambda x: (x.kind, -x.size, x.relpath))
        warnings = []
        if not candidates:
            warnings.append("Aucune image reconnue dans le fichier/archive.")
        if any(c.kind == "iol" for c in candidates):
            warnings.append("Les images IOL doivent être autorisées/licenciées pour votre environnement EVE-NG.")
        if any(c.kind == "qemu-iso" for c in candidates):
            warnings.append("Une ISO est un média d'installation: EVE Image Forge créera aussi un disque QCOW2 vierge.")
        return {
            "filename": meta["filename"],
            "candidates": [asdict(c) for c in candidates],
            "warnings": warnings,
        }

    def resolve_candidate(self, upload_id: str, relpath: str) -> Path:
        work = (self.work_root / self.sanitize_name(upload_id)).resolve()
        p = (work / relpath).resolve()
        if work not in p.parents or not p.exists() or not p.is_file():
            raise ForgeError("Candidat invalide")
        if not self.classify(p):
            raise ForgeError("Format candidat non supporté")
        return p

    @staticmethod
    def _run(cmd: list[str], log: Callable[[str], None]) -> None:
        log("$ " + " ".join(cmd))
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        assert proc.stdout is not None
        for line in proc.stdout:
            log(line.rstrip())
        rc = proc.wait()
        if rc != 0:
            raise ForgeError(f"Commande échouée ({rc}): {' '.join(cmd)}")

    def _backup_existing(self, target: Path, log: Callable[[str], None]) -> None:
        if not target.exists():
            return
        stamp = __import__("datetime").datetime.now().strftime("%Y%m%d-%H%M%S")
        b = self.backup_root / f"{target.name}-{stamp}"
        log(f"Sauvegarde de {target} -> {b}")
        shutil.move(str(target), str(b))

    def fix_permissions(self, log: Callable[[str], None]) -> None:
        wrapper = self.eve_root / "wrappers/unl_wrapper"
        if not wrapper.exists():
            raise ForgeError(f"fixpermissions introuvable: {wrapper}")
        self._run([str(wrapper), "-a", "fixpermissions"], log)

    def install(self, spec: dict, log: Callable[[str], None], progress: Callable[[int], None]) -> dict:
        upload_id = spec["upload_id"]
        src = self.resolve_candidate(upload_id, spec["relpath"])
        classified = self.classify(src)
        assert classified
        kind, fmt = classified
        dry = bool(spec.get("dry_run", False))
        backup = bool(spec.get("backup_existing", True))
        progress(5)
        log(f"Source: {src}")
        log(f"Type détecté: {kind} / {fmt}")

        if kind in {"qemu", "qemu-iso"}:
            prefix = self.sanitize_name(spec.get("template", "newimage"), "newimage")
            version = self.sanitize_name(spec.get("version", "imported"), "imported")
            folder = f"{prefix}-{version}"
            target_dir = self.eve_root / "addons/qemu" / folder
            disk_name = spec.get("disk_name") or self.infer_disk_name(prefix)
            if not SAFE_DISK_NAMES.match(disk_name):
                raise ForgeError("Nom de disque EVE invalide. Ex: hda.qcow2, virtioa.qcow2, sataa.qcow2")
            planned = {"target_dir": str(target_dir), "disk_name": disk_name}
            if dry:
                log(f"DRY-RUN: créer {target_dir}")
                if kind == "qemu-iso":
                    log(f"DRY-RUN: copier ISO -> {target_dir/'cdrom.iso'}")
                    log(f"DRY-RUN: créer disque vierge -> {target_dir/disk_name}")
                else:
                    log(f"DRY-RUN: préparer image -> {target_dir/disk_name}")
                progress(100)
                return {"dry_run": True, **planned}

            target_dir.parent.mkdir(parents=True, exist_ok=True)
            if target_dir.exists():
                if backup:
                    self._backup_existing(target_dir, log)
                else:
                    raise ForgeError(f"Le dossier cible existe déjà: {target_dir}")
            target_dir.mkdir(parents=True)
            progress(20)

            if kind == "qemu-iso":
                shutil.copy2(src, target_dir / "cdrom.iso")
                size_gb = max(1, min(int(spec.get("iso_disk_size_gb", 20)), 4096))
                qemu_img = self.find_qemu_img()
                if not qemu_img:
                    raise ForgeError("qemu-img est requis pour créer le disque de l'ISO")
                self._run([qemu_img, "create", "-f", "qcow2", str(target_dir / disk_name), f"{size_gb}G"], log)
            else:
                out = target_dir / disk_name
                if fmt == "qcow2":
                    shutil.copy2(src, out)
                else:
                    qemu_img = self.find_qemu_img()
                    if not qemu_img:
                        raise ForgeError("qemu-img est requis pour convertir ce format vers qcow2")
                    fmt_in = "raw" if fmt in {"raw", "img"} else fmt
                    self._run([qemu_img, "convert", "-p", "-f", fmt_in, "-O", "qcow2", str(src), str(out)], log)
            progress(85)
            self.fix_permissions(log)
            progress(100)
            return {"installed": True, **planned}

        if kind == "iol":
            target_dir = self.eve_root / "addons/iol/bin"
            filename = Path(spec.get("target_name") or src.name).name
            if not filename.lower().endswith(".bin"):
                filename += ".bin"
            target = target_dir / filename
            if dry:
                log(f"DRY-RUN: copier IOL -> {target} et rendre exécutable")
                progress(100)
                return {"dry_run": True, "target": str(target)}
            target_dir.mkdir(parents=True, exist_ok=True)
            if target.exists() and backup:
                self._backup_existing(target, log)
            shutil.copy2(src, target)
            target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            progress(80)
            self.fix_permissions(log)
            progress(100)
            return {"installed": True, "target": str(target)}

        if kind == "dynamips":
            target_dir = self.eve_root / "addons/dynamips"
            filename = Path(spec.get("target_name") or src.name).name
            target = target_dir / filename
            if dry:
                log(f"DRY-RUN: copier Dynamips -> {target}")
                progress(100)
                return {"dry_run": True, "target": str(target)}
            target_dir.mkdir(parents=True, exist_ok=True)
            if target.exists() and backup:
                self._backup_existing(target, log)
            shutil.copy2(src, target)
            progress(80)
            self.fix_permissions(log)
            progress(100)
            return {"installed": True, "target": str(target)}

        raise ForgeError(f"Type non supporté: {kind}")
