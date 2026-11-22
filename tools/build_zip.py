"""Build cs_environment_elements.zip (layout cs_environment_elements/...) next to this
project, without __pycache__ / .blend1 / editor folders. Run with any Python 3."""

import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = "cs_environment_elements"
SKIP_DIRS = {"__pycache__", ".vscode", ".git"}
SKIP_EXT = {".blend1", ".pyc"}


def build():
    out = os.path.join(ROOT, PKG + ".zip")
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for d, dirs, files in os.walk(os.path.join(ROOT, PKG)):
            dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS)
            for fn in sorted(files):
                if os.path.splitext(fn)[1].lower() in SKIP_EXT:
                    continue
                path = os.path.join(d, fn)
                z.write(path, os.path.relpath(path, ROOT))
                n += 1
    print(f"{out}: {n} files, {os.path.getsize(out) / 1e6:.1f} MB")
    return out


if __name__ == "__main__":
    build()
