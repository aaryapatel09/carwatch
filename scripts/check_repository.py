"""Fail if local artifacts, secrets, or machine-specific paths enter tracked files."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "README.md",
    "LICENSE",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "pyproject.toml",
    "requirements.lock.txt",
    ".github/workflows/ci.yml",
]
FORBIDDEN_SUFFIXES = {
    ".pt",
    ".pth",
    ".joblib",
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".onnx",
    ".pem",
    ".key",
}
# Patterns assembled to avoid matching this checker's own source literals.
HOME_PATH = re.compile(r"/(?:Users|home)/[A-Za-z0-9_.-]+/")
TOKEN = re.compile(
    r"(?:gh"
    + r"p_[A-Za-z0-9]{30,}|sk-"
    + r"[A-Za-z0-9_-]{35,}|AKIA"
    + r"[A-Z0-9]{16}|tk_"
    + r"[A-Za-z0-9]{25,})"
)


def check():
    failures = []
    for name in REQUIRED:
        if not (ROOT / name).is_file():
            failures.append("Missing required file: " + name)
    paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    for name in filter(None, paths):
        p = Path(name)
        if (p.name == ".env" or p.name.startswith(".env.")) and p.name != ".env.example":
            failures.append("Local environment file tracked: " + name)
        if p.as_posix() == ".streamlit/secrets.toml":
            failures.append("Local application secrets tracked: " + name)
        if p.parts[0] in ("runtime", ".venv") or p.suffix.lower() in FORBIDDEN_SUFFIXES:
            failures.append("Local artifact tracked: " + name)
        path = ROOT / p
        if not path.is_file():
            continue  # tracked deletion awaiting commit
        if path.stat().st_size > 2_000_000:
            failures.append("Unexpected large tracked file: " + name)
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeError:
            continue
        if HOME_PATH.search(text):
            failures.append("Machine-specific home path: " + name)
        if TOKEN.search(text):
            failures.append("Possible credential: " + name)
    if failures:
        raise SystemExit("\n".join(failures))
    print("Repository hygiene checks passed")


if __name__ == "__main__":
    check()
