"""Build infra/build/query.zip: the query package, the ingest package it imports, and their dependencies
for Lambda (arm64, Python 3.13).

Wheels target manylinux_2_28: the python3.13 runtime is Amazon Linux 2023 (glibc 2.34), and rapidfuzz
no longer publishes manylinux2014 arm64 wheels.

The zip is reproducible (sorted entries, fixed timestamps and permissions), so Terraform's
filebase64sha256 changes only when the content does.

Run: uv run --directory backend/query python scripts/build.py
"""

import shutil
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # backend/query
INGEST = ROOT.parent / "ingest"                     # backend/ingest, archived as ingest/…
BUILD = ROOT / "build"
PKG = BUILD / "pkg"
OUT = ROOT.parents[1] / "infra" / "build" / "query.zip"
FIXED_TIME = (1980, 1, 1, 0, 0, 0)
SKIP_PARTS = {"__pycache__"}


def run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def files_under(base: Path, sub: Path) -> list[tuple[Path, str]]:
    """(source path, archive name) for every file under base/sub, skipping caches."""
    return [
        (path, path.relative_to(base).as_posix())
        for path in (base / sub).rglob("*")
        if path.is_file() and not SKIP_PARTS & set(path.parts) and path.suffix != ".pyc"
    ]


def main() -> None:
    shutil.rmtree(BUILD, ignore_errors=True)
    BUILD.mkdir()
    run("uv", "export", "--no-dev", "--no-hashes", "--frozen", "--no-emit-project", "-o", "build/requirements.txt")
    run(
        "uv", "pip", "install", "-r", "build/requirements.txt", "--target", "build/pkg",
        "--python-platform", "aarch64-manylinux_2_28", "--python-version", "3.13", "--only-binary", ":all:",
    )

    entries = files_under(PKG, Path(".")) + files_under(ROOT, Path("query")) + files_under(INGEST, Path("ingest"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path, name in sorted(entries, key=lambda e: e[1]):
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, path.read_bytes(), compresslevel=9)
    print(f"{OUT} ({OUT.stat().st_size / 1e6:.1f} MB, {len(entries)} files)")


if __name__ == "__main__":
    main()
