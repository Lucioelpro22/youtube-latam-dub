"""Build a source/Windows installer ZIP using an explicit public-file allowlist."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = ["README.md", "LICENSE", "PRIVACY.md", "THIRD_PARTY_NOTICES.md", "CHANGELOG.md", ".gitignore", ".gitattributes", "install.bat", "run_server.bat", "test_pipeline.py"]


def public_files(root=ROOT):
    paths = [root / name for name in ROOT_FILES]
    for directory, extensions in [("backend", {".py", ".txt"}), ("extension", {".js", ".html", ".css", ".json", ".png"}), ("tests", {".py", ".cjs"}), ("scripts", {".py"}), (".github/workflows", {".yml"})]:
        paths.extend(p for p in (root / directory).iterdir() if p.is_file() and p.suffix in extensions)
    return sorted(paths)


def build(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    version = json.loads((ROOT / "extension/manifest.json").read_text(encoding="utf-8"))["version_name"]
    name = "youtube-latam-dub-v" + version
    archive = output / (name + "-windows.zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
        for path in public_files():
            package.write(path, name + "/" + path.relative_to(ROOT).as_posix())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / "SHA256SUMS.txt").write_text(digest + "  " + archive.name + "\n", encoding="utf-8")
    print(archive)
    return archive


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "dist"))
    build(parser.parse_args().output)
