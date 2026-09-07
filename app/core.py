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
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

SUPPORTED_QEMU = {".qcow2", ".qcow", ".vmdk", ".vdi", ".raw", ".img"}
SUPPORTED_ARCHIVES = {".zip", ".tgz", ".tar.gz", ".tar", ".ova", ".gz"}
SUPPORTED_DIRECT = SUPPORTED_QEMU | {".iso", ".bin", ".image"}
SAFE_DISK_NAMES = re.compile(r"^(?:hd|virtio|virtide|scsi|sata|lsi|megasas)[a-z]\.qcow2$")
SAFE_NAME = re.compile(r"[^A-Za-z0-9._+-]+")
VERSION_PATTERNS = [
    re.compile(r"(?<![A-Za-z0-9])([0-9]{2}\.[0-9]+R[0-9]+(?:\.[0-9]+)?(?:-S[0-9.]+)?)(?![A-Za-z0-9])", re.I),
    re.compile(r"(?<![A-Za-z0-9])v?([0-9]{1,4}(?:\.[0-9]+){1,4}(?:[A-Za-z])?(?:[-_](?:S|R|P)[A-Za-z0-9.]+)?)(?![A-Za-z0-9])", re.I),
]


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
    VERSION = "0.2.0"

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
    def normalize(value: str) -> str:
        return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())

    @staticmethod
    def natural_key(value: str) -> list[tuple[int, object]]:
        return [(0, int(x)) if x.isdigit() else (1, x.lower()) for x in re.split(r"(\d+)", value)]

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
                "disk_layout": self.infer_disk_layout(prefix),
                "source": str(yml),
            })
        return rows

    @staticmethod
    def _disk_order(name: str) -> tuple[int, str]:
        families = ["hd", "virtio", "virtide", "scsi", "sata", "lsi", "megasas"]
        for i, family in enumerate(families):
            if name.startswith(family):
                return i, name
        return 99, name

    def infer_disk_layout(self, prefix: str) -> list[str]:
        qemu = self.eve_root / "addons/qemu"
        layouts: Counter[tuple[str, ...]] = Counter()
        if qemu.exists():
            for folder in qemu.glob(prefix + "-*"):
                if not folder.is_dir():
                    continue
                disks = tuple(sorted(
                    (f.name for f in folder.iterdir() if f.is_file() and SAFE_DISK_NAMES.match(f.name)),
                    key=self._disk_order,
                ))
                if disks:
                    layouts[disks] += 1
        if layouts:
            return list(layouts.most_common(1)[0][0])
        profile = self.profiles.get(prefix, {})
        disks = profile.get("disks") or ([profile["disk"]] if profile.get("disk") else [])
        return [d for d in disks if SAFE_DISK_NAMES.match(d)] or ["hda.qcow2"]

    def infer_disk_name(self, prefix: str) -> str:
        return self.infer_disk_layout(prefix)[0]

    def installed_images(self, prefix: str | None = None) -> list[dict]:
        root = self.eve_root / "addons/qemu"
        if not root.exists():
            return []
        rows: list[dict] = []
        for folder in sorted(root.iterdir(), key=lambda p: p.name.lower()):
            if not folder.is_dir() or folder.name.startswith("."):
                continue
            if prefix and not folder.name.startswith(prefix + "-"):
                continue
            disks = []
            total = 0
            for f in sorted(folder.iterdir(), key=lambda p: self.natural_key(p.name)):
                if f.is_file() and (SAFE_DISK_NAMES.match(f.name) or f.name == "cdrom.iso"):
                    size = f.stat().st_size
                    total += size
                    disks.append({"name": f.name, "size": size})
            rows.append({
                "folder": folder.name,
                "path": str(folder),
                "disks": disks,
                "size": total,
                "mtime": int(folder.stat().st_mtime),
            })
        return rows

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
            "installed_qemu_images": len(self.installed_images()),
            "smart_import": True,
            "version": self.VERSION,
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
                mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode):
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as inp, target.open("wb") as out:
                    shutil.copyfileobj(inp, out, 4 * 1024 * 1024)

    def _extract_tar(self, src: Path, dest: Path) -> None:
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

    def _extract_version(self, text: str) -> str:
        stem = text
        for suffix in [".tar.gz", ".qcow2", ".vmdk", ".vdi", ".raw", ".img", ".iso", ".zip", ".tgz", ".ova", ".gz"]:
            if stem.lower().endswith(suffix):
                stem = stem[:-len(suffix)]
                break
        matches: list[str] = []
        for pattern in VERSION_PATTERNS:
            matches.extend(m.group(1) for m in pattern.finditer(stem))
        matches = [m.strip("-_.") for m in matches if not re.fullmatch(r"(?:32|64|86|100|200|8000|9000)", m)]
        if matches:
            return max(matches, key=len)
        return "imported"

    def _smart_template(self, context: str) -> dict:
        hay = self.normalize(context)
        templates = self.discover_templates()
        installed = {t["prefix"]: t for t in templates}
        ranked: list[tuple[int, str, str]] = []

        for prefix, profile in self.profiles.items():
            if prefix == "newimage":
                continue
            score = 0
            reason = ""
            pnorm = self.normalize(prefix)
            if pnorm and pnorm in hay:
                score = max(score, 70 + min(len(pnorm), 15))
                reason = f"préfixe {prefix} trouvé"
            for pattern in profile.get("patterns", []):
                norm = self.normalize(pattern)
                if norm and norm in hay:
                    candidate_score = 82 + min(len(norm), 16)
                    if candidate_score > score:
                        score = candidate_score
                        reason = f"signature « {pattern} » trouvée"
            if prefix in installed and score:
                score += 4
            if score:
                ranked.append((score, prefix, reason))

        for t in templates:
            prefix = t["prefix"]
            pieces = [prefix, t.get("name", ""), t.get("description", "")]
            score = 0
            reason = ""
            for piece in pieces:
                norm = self.normalize(piece)
                if norm and len(norm) >= 3 and norm in hay:
                    s = 68 + min(len(norm), 18)
                    if s > score:
                        score = s
                        reason = f"template EVE « {piece} » correspond"
            tokens = set(self.normalize(" ".join(pieces)).split())
            overlap = [x for x in tokens if len(x) >= 4 and x in set(hay.split())]
            if len(overlap) >= 2:
                score = max(score, 58 + min(len(overlap) * 5, 20))
                reason = f"mots du template EVE: {', '.join(sorted(overlap)[:4])}"
            if score:
                ranked.append((score, prefix, reason))

        if not ranked:
            return {
                "prefix": "newimage",
                "score": 25,
                "confidence": 25,
                "reason": "aucune signature produit suffisamment précise",
                "available": "newimage" in installed,
                "template": installed.get("newimage"),
            }

        ranked.sort(key=lambda x: (x[0], len(x[1])), reverse=True)
        score, prefix, reason = ranked[0]
        confidence = min(99, max(35, score))
        return {
            "prefix": prefix,
            "score": score,
            "confidence": confidence,
            "reason": reason,
            "available": prefix in installed,
            "template": installed.get(prefix),
        }

    @staticmethod
    def _disk_family(name: str) -> str:
        m = re.match(r"^(hd|virtio|virtide|scsi|sata|lsi|megasas)[a-z]\.qcow2$", name)
        return m.group(1) if m else "hd"

    @staticmethod
    def _disk_name(family: str, index: int) -> str:
        if index < 0 or index > 25:
            raise ForgeError("Trop de disques pour une appliance EVE-NG")
        return f"{family}{chr(ord('a') + index)}.qcow2"

    def _map_smart_disks(self, qemu: list[dict], prefix: str) -> tuple[list[dict], list[dict], list[str]]:
        profile = self.profiles.get(prefix, {})
        layout = self.infer_disk_layout(prefix)
        family = self._disk_family(layout[0] if layout else profile.get("disk", "hda.qcow2"))
        qemu_sorted = sorted(qemu, key=lambda c: self.natural_key(Path(c["relpath"]).name))
        assigned: dict[str, str] = {}
        used: set[str] = set()

        for c in qemu_sorted:
            base = Path(c["relpath"]).name.lower()
            if SAFE_DISK_NAMES.match(base) and base not in used:
                assigned[c["relpath"]] = base
                used.add(base)

        available = [d for d in layout if d not in used]
        next_idx = 0
        for c in qemu_sorted:
            if c["relpath"] in assigned:
                continue
            if available:
                disk = available.pop(0)
            else:
                while self._disk_name(family, next_idx) in used:
                    next_idx += 1
                disk = self._disk_name(family, next_idx)
                next_idx += 1
            assigned[c["relpath"]] = disk
            used.add(disk)

        mapped = []
        for c in qemu_sorted:
            mapped.append({
                "relpath": c["relpath"],
                "source_name": Path(c["relpath"]).name,
                "disk_name": assigned[c["relpath"]],
                "format": c["format"],
                "size": c["size"],
                "action": "copy" if c["format"] == "qcow2" else "convert",
            })

        generated = []
        for extra in profile.get("extra_disks", []):
            name = extra.get("name", "")
            if SAFE_DISK_NAMES.match(name) and name not in used:
                generated.append({"disk_name": name, "size_gb": int(extra.get("size_gb", 20))})
                used.add(name)

        warnings = []
        expected = [d for d in layout if d]
        missing = [d for d in expected if d not in used]
        if missing and len(expected) > 1:
            warnings.append("Ce template utilise souvent plusieurs disques; non fournis: " + ", ".join(missing))
        return mapped, generated, warnings

    def build_smart_plan(self, meta: dict, candidates: list[Candidate]) -> dict | None:
        rows = [asdict(c) for c in candidates]
        qemu = [c for c in rows if c["kind"] == "qemu"]
        isos = [c for c in rows if c["kind"] == "qemu-iso"]
        iol = [c for c in rows if c["kind"] == "iol"]
        dynamips = [c for c in rows if c["kind"] == "dynamips"]

        context = " ".join([meta.get("filename", "")] + [c["relpath"] for c in rows])
        if qemu or isos:
            match = self._smart_template(context)
            prefix = match["prefix"]
            profile = self.profiles.get(prefix, {})
            version = self._extract_version(context)
            folder = f"{prefix}-{self.sanitize_name(version, 'imported')}"
            target_dir = self.eve_root / "addons/qemu" / folder
            mapped, generated, map_warnings = self._map_smart_disks(qemu, prefix)
            cdrom = isos[0]["relpath"] if isos else None

            if not qemu and cdrom:
                primary = self.infer_disk_name(prefix)
                generated.insert(0, {"disk_name": primary, "size_gb": 20})

            existing = self.installed_images(prefix)
            warnings = list(map_warnings)
            if not match["available"]:
                warnings.append(f"Le template « {prefix} » n'est pas présent dans les templates QEMU détectés sur ce serveur EVE-NG.")
            if target_dir.exists():
                warnings.append(f"La cible {folder} existe déjà; une sauvegarde sera requise avant remplacement.")
            if len(isos) > 1:
                warnings.append("Plusieurs ISO détectées; Smart Import utilise la première. Le mode manuel permet de choisir autrement.")
            if match["confidence"] < 70:
                warnings.append("Confiance de détection faible: vérifie le template avant installation réelle.")

            return {
                "mode": "qemu",
                "confidence": match["confidence"],
                "template": prefix,
                "template_available": match["available"],
                "template_name": (match["template"] or {}).get("name") or profile.get("label") or prefix,
                "vendor": profile.get("vendor", "Inconnu"),
                "product": profile.get("label", (match["template"] or {}).get("name", prefix)),
                "version": version,
                "folder": folder,
                "target_dir": str(target_dir),
                "target_exists": target_dir.exists(),
                "existing_versions": [x["folder"] for x in existing[-12:]],
                "disks": mapped,
                "generated_disks": generated,
                "cdrom_relpath": cdrom,
                "warnings": warnings,
                "reasons": [match["reason"], f"layout disque: {', '.join(self.infer_disk_layout(prefix))}"],
            }

        if iol:
            c = iol[0]
            return {
                "mode": "iol",
                "confidence": 100,
                "target_name": Path(c["relpath"]).name,
                "relpath": c["relpath"],
                "target_dir": str(self.eve_root / "addons/iol/bin"),
                "warnings": ["Smart Import ne gère pas et ne génère pas les licences IOL."],
                "reasons": ["extension .bin reconnue comme image IOL"],
            }

        if dynamips:
            c = dynamips[0]
            return {
                "mode": "dynamips",
                "confidence": 100,
                "target_name": Path(c["relpath"]).name,
                "relpath": c["relpath"],
                "target_dir": str(self.eve_root / "addons/dynamips"),
                "warnings": [],
                "reasons": ["extension .image reconnue comme image Dynamips"],
            }
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
        candidates.sort(key=lambda x: (x.kind, self.natural_key(x.relpath)))
        warnings = []
        if not candidates:
            warnings.append("Aucune image reconnue dans le fichier/archive.")
        if any(c.kind == "iol" for c in candidates):
            warnings.append("Les images IOL doivent être autorisées/licenciées pour votre environnement EVE-NG.")
        if any(c.kind == "qemu-iso" for c in candidates):
            warnings.append("Une ISO est un média d'installation; Smart Import peut créer un disque QCOW2 vierge.")
        smart = self.build_smart_plan(meta, candidates)
        return {
            "filename": meta["filename"],
            "candidates": [asdict(c) for c in candidates],
            "warnings": warnings,
            "smart_plan": smart,
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
        proc.stdout.close()
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

    def _copy_or_convert_qemu(self, src: Path, out: Path, fmt: str, log: Callable[[str], None]) -> None:
        if fmt == "qcow2":
            shutil.copy2(src, out)
            return
        qemu_img = self.find_qemu_img()
        if not qemu_img:
            raise ForgeError("qemu-img est requis pour convertir ce format vers qcow2")
        fmt_in = "raw" if fmt in {"raw", "img"} else fmt
        self._run([qemu_img, "convert", "-p", "-f", fmt_in, "-O", "qcow2", str(src), str(out)], log)

    def _install_qemu_plan(self, spec: dict, log: Callable[[str], None], progress: Callable[[int], None]) -> dict:
        upload_id = spec["upload_id"]
        prefix = self.sanitize_name(spec.get("template", "newimage"), "newimage")
        version = self.sanitize_name(spec.get("version", "imported"), "imported")
        target_dir = self.eve_root / "addons/qemu" / f"{prefix}-{version}"
        backup = bool(spec.get("backup_existing", True))
        dry = bool(spec.get("dry_run", False))

        disk_specs = spec.get("disks") or []
        generated_specs = spec.get("generated_disks") or []
        cdrom_relpath = spec.get("cdrom_relpath")
        if not isinstance(disk_specs, list) or not isinstance(generated_specs, list):
            raise ForgeError("Plan de disques Smart Import invalide")
        if len(disk_specs) + len(generated_specs) > 26:
            raise ForgeError("Trop de disques dans le plan Smart Import")

        resolved: list[tuple[Path, str, str]] = []
        names: set[str] = set()
        for item in disk_specs:
            relpath = item["relpath"]
            disk_name = item["disk_name"]
            if not SAFE_DISK_NAMES.match(disk_name) or disk_name in names:
                raise ForgeError(f"Nom de disque EVE invalide/dupliqué: {disk_name}")
            src = self.resolve_candidate(upload_id, relpath)
            classified = self.classify(src)
            if not classified or classified[0] != "qemu":
                raise ForgeError(f"Source Smart Import non QEMU: {relpath}")
            names.add(disk_name)
            resolved.append((src, disk_name, classified[1]))

        generated: list[tuple[str, int]] = []
        for item in generated_specs:
            disk_name = item["disk_name"]
            size_gb = max(1, min(int(item.get("size_gb", 20)), 4096))
            if not SAFE_DISK_NAMES.match(disk_name) or disk_name in names:
                raise ForgeError(f"Nom de disque généré invalide/dupliqué: {disk_name}")
            names.add(disk_name)
            generated.append((disk_name, size_gb))

        cdrom = None
        if cdrom_relpath:
            cdrom = self.resolve_candidate(upload_id, cdrom_relpath)
            classified = self.classify(cdrom)
            if not classified or classified[0] != "qemu-iso":
                raise ForgeError("Le média CD-ROM Smart Import n'est pas une ISO")

        if not resolved and not generated and not cdrom:
            raise ForgeError("Plan Smart Import QEMU vide")
        if target_dir.exists() and not backup:
            raise ForgeError(f"Le dossier cible existe déjà: {target_dir}")

        log(f"Smart Import: {prefix} / {version}")
        log(f"Cible: {target_dir}")
        if dry:
            for src, disk_name, fmt in resolved:
                action = "copier" if fmt == "qcow2" else f"convertir {fmt} -> qcow2"
                log(f"DRY-RUN: {action}: {src.name} -> {disk_name}")
            for disk_name, size_gb in generated:
                log(f"DRY-RUN: créer disque vierge {disk_name} ({size_gb}G)")
            if cdrom:
                log(f"DRY-RUN: copier {cdrom.name} -> cdrom.iso")
            if target_dir.exists():
                log("DRY-RUN: la cible existe; elle sera sauvegardée avant remplacement")
            progress(100)
            return {
                "dry_run": True,
                "smart_import": True,
                "target_dir": str(target_dir),
                "disks": sorted(names),
                "cdrom": bool(cdrom),
            }

        target_dir.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".eif-smart-", dir=str(target_dir.parent)))
        try:
            total_steps = max(1, len(resolved) + len(generated) + (1 if cdrom else 0))
            done = 0
            for src, disk_name, fmt in resolved:
                log(f"Préparation {src.name} -> {disk_name}")
                self._copy_or_convert_qemu(src, stage / disk_name, fmt, log)
                done += 1
                progress(10 + int(65 * done / total_steps))

            if generated:
                qemu_img = self.find_qemu_img()
                if not qemu_img:
                    raise ForgeError("qemu-img est requis pour créer les disques additionnels")
                for disk_name, size_gb in generated:
                    self._run([qemu_img, "create", "-f", "qcow2", str(stage / disk_name), f"{size_gb}G"], log)
                    done += 1
                    progress(10 + int(65 * done / total_steps))

            if cdrom:
                shutil.copy2(cdrom, stage / "cdrom.iso")
                done += 1
                progress(10 + int(65 * done / total_steps))

            if target_dir.exists():
                self._backup_existing(target_dir, log)
            stage.rename(target_dir)
            progress(85)
            self.fix_permissions(log)
            progress(100)
            return {
                "installed": True,
                "smart_import": True,
                "target_dir": str(target_dir),
                "disks": sorted(names),
                "cdrom": bool(cdrom),
            }
        except Exception:
            if stage.exists():
                shutil.rmtree(stage, ignore_errors=True)
            raise

    def install(self, spec: dict, log: Callable[[str], None], progress: Callable[[int], None]) -> dict:
        if spec.get("smart_mode") or isinstance(spec.get("disks"), list):
            return self._install_qemu_plan(spec, log, progress)

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
            disk_name = spec.get("disk_name") or self.infer_disk_name(prefix)
            if not SAFE_DISK_NAMES.match(disk_name):
                raise ForgeError("Nom de disque EVE invalide. Ex: hda.qcow2, virtioa.qcow2, sataa.qcow2")
            plan = {
                "upload_id": upload_id,
                "template": prefix,
                "version": version,
                "backup_existing": backup,
                "dry_run": dry,
                "smart_mode": True,
                "disks": [],
                "generated_disks": [],
            }
            if kind == "qemu-iso":
                plan["cdrom_relpath"] = spec["relpath"]
                plan["generated_disks"] = [{"disk_name": disk_name, "size_gb": int(spec.get("iso_disk_size_gb", 20))}]
            else:
                plan["disks"] = [{"relpath": spec["relpath"], "disk_name": disk_name}]
            return self._install_qemu_plan(plan, log, progress)

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
            if target.exists():
                if backup:
                    self._backup_existing(target, log)
                else:
                    raise ForgeError(f"Le fichier cible existe déjà: {target}")
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
            if target.exists():
                if backup:
                    self._backup_existing(target, log)
                else:
                    raise ForgeError(f"Le fichier cible existe déjà: {target}")
            shutil.copy2(src, target)
            progress(80)
            self.fix_permissions(log)
            progress(100)
            return {"installed": True, "target": str(target)}

        raise ForgeError(f"Type non supporté: {kind}")
