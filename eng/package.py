"""Build a deterministic local archive for an independent consumer."""

import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE, = (path.name for path in (ROOT / "src").iterdir() if (path / "engine.py").is_file())
output = ROOT / "artifacts" / f"{PACKAGE}.pyz"
output.parent.mkdir(exist_ok=True)
payloads = {
    path.relative_to(ROOT / "src").as_posix(): path.read_bytes()
    for path in sorted((ROOT / "src" / PACKAGE).iterdir()) if path.suffix in (".py", ".json")
}
payloads["__main__.py"] = f"from {PACKAGE}.engine import main\nraise SystemExit(main())\n".encode()
payloads["LICENSE"] = (ROOT / "LICENSE").read_bytes()
payloads["NOTICE"] = (ROOT / "NOTICE").read_bytes()
with zipfile.ZipFile(output, "w") as archive:
    for name, data in sorted(payloads.items()):
        info = zipfile.ZipInfo(name, date_time=(2026, 11, 22, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, data)
print(output)
print(hashlib.sha256(output.read_bytes()).hexdigest())
