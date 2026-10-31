"""Package the add-on as dist/powerhouse.ankiaddon (zip of the folder's contents)."""
import json
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "addon"
DIST = ROOT / "dist"
DIST.mkdir(exist_ok=True)
out = DIST / "powerhouse.ankiaddon"

manifest = json.loads((SRC / "manifest.json").read_text())
manifest["mod"] = int(time.time())
(SRC / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

skip_dirs = {"__pycache__", "saves"}
count = 0
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for path in sorted(SRC.rglob("*")):
        rel = path.relative_to(SRC)
        if any(part in skip_dirs for part in rel.parts):
            continue
        if path.is_dir():
            continue
        if rel.parts[0] == "user_files" and rel.name != "README.txt":
            continue
        if rel.as_posix() == "meta.json":  # written by Anki at runtime; never ship it
            continue
        if path.suffix in (".pyc", ".tmp", ".bak") or path.name.endswith(".log") or path.name.endswith(".old"):
            continue
        z.write(path, rel.as_posix())
        count += 1
print(f"wrote {out} ({count} files, {out.stat().st_size/1024:.0f} KB)")
