#!/usr/bin/env python3
"""Build the standalone FedRAMP Linear template ZIP from repository resources."""

import argparse
import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
TOOL = Path(__file__).resolve().parent
RESOURCE = ROOT / "resources/fedramp/20x/class-a/linear"


def checksums(files):
    return "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in sorted(files.items()))


def recipient_readme():
    value = (TOOL / "README.md").read_text(encoding="utf-8").split("\n## Build the shareable package\n")[0]
    value = value.replace(
        "Build and share `dist/linear-fedramp-class-a.zip` with the recipient. Repository commands below run from the repository root; commands inside the ZIP use the flat filenames in the extracted folder.",
        "Share this entire folder or its ZIP with the recipient.")
    value = value.replace(
        "Install Python 3.10 or later. Open a terminal in the repository root. ZIP recipients should extract the archive and open a terminal in its `linear-fedramp-class-a` folder.",
        "Install Python 3.10 or later. Extract the ZIP and open a terminal in the `linear-fedramp-class-a` folder.")
    value = value.replace("-s tools/linear-template/tests", "-s .")
    value = value.replace("tools/linear-template/tests/", "")
    value = value.replace("tools/linear-template/", "")
    value = value.replace("resources/fedramp/20x/class-a/linear/", "")
    value = value.replace("Resource checksums; the ZIP includes its own file checksums", "Checksums for the distributed files")
    return value.encode("utf-8")


def build(output):
    resource_files = {name: (RESOURCE / name).read_bytes() for name in ("README.md", "template.json", "CONTENTS.html")}
    (RESOURCE / "SHA256SUMS").write_text(checksums(resource_files), encoding="utf-8")
    files = {
        "README.md": recipient_readme(),
        "LICENSE": (ROOT / "LICENSE").read_bytes(),
        ".gitignore": (ROOT / ".gitignore").read_bytes(),
        "import_template.py": (TOOL / "import_template.py").read_bytes(),
        "requirements.txt": (TOOL / "requirements.txt").read_bytes(),
        "test_import_template.py": (TOOL / "tests/test_import_template.py").read_bytes(),
        "template.json": resource_files["template.json"],
        "CONTENTS.html": resource_files["CONTENTS.html"],
    }
    files["SHA256SUMS"] = checksums(files).encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            item = zipfile.ZipInfo("linear-fedramp-class-a/" + name, date_time=(2026, 10, 16, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            archive.writestr(item, data)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/linear-fedramp-class-a.zip")
    args = parser.parse_args()
    output = build(args.output)
    print(f"Built {output} ({output.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
