#!/usr/bin/env python3
"""Reims-owned non-TTY adapter for the pinned macOS fetcher."""
import importlib.util
import pathlib
import sys

UPSTREAM = pathlib.Path(__file__).resolve().parent.parent / "third_party/OSX-KVM/fetch-macOS-v2.py"
def load_fetcher():
    lines = UPSTREAM.read_text().splitlines(True)
    needle = "            terminalsize = max(os.get_terminal_size().columns - TERMINAL_MARGIN, 0)\n"
    indexes = [i for i, line in enumerate(lines) if line.strip() == needle.strip()]
    if len(indexes) != 2:
        raise RuntimeError("unsupported fetcher version: terminal-size contract changed")
    i = indexes[1]
    lines[i:i + 1] = ["            try:\n", "                " + needle.lstrip(), "            except OSError:\n", "                terminalsize = 80\n"]
    spec = importlib.util.spec_from_loader("reims_patched_fetcher", loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(UPSTREAM)
    exec(compile("".join(lines), str(UPSTREAM), "exec"), module.__dict__)
    return module

if __name__ == "__main__":
    module = load_fetcher()
    if len(sys.argv) == 4 and sys.argv[1] == "--verify-only":
        module.verify_image(sys.argv[2], sys.argv[3])
        raise SystemExit(0)
    sys.argv[0] = str(UPSTREAM)
    raise SystemExit(module.main())
