"""Import provenance check for a tree under test.

The shared interpreter (.venv311) carries an editable install of the other
worktree (``/home/ubuntu/gemini/fl-security-research/src``), and ``fl_security``
and most of its subpackages are PEP 420 namespace packages. A module that is
missing from the tree under test would therefore resolve silently to the other
tree. This check shows that

1. every module of the tree under test resolves to that tree (PYTHONPATH first);
2. no module that exists only in the other tree is referenced by the tree under
   test, so nothing can fall through to it.

Usage: PYTHONPATH=<tree>/src python import_provenance_check.py <tree> <other_src>
"""
from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path


def module_names(src_root: Path) -> set[str]:
    names = set()
    for path in (src_root / "fl_security").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        parts = list(path.relative_to(src_root).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        names.add(".".join(parts))
    for path in (src_root / "fl_security").rglob("*"):
        if path.is_dir() and "__pycache__" not in path.parts and any(path.glob("*.py")):
            names.add(".".join(path.relative_to(src_root).parts))
    names.add("fl_security")
    return names


def main() -> int:
    tree = Path(sys.argv[1]).resolve()
    other_src = Path(sys.argv[2]).resolve()
    src = tree / "src"
    own = module_names(src)
    foreign = sorted(module_names(other_src) - own)
    print(f"tree under test: {tree}")
    print(f"other tree on sys.path via editable install: {other_src}")
    print(f"sys.path (first 4): {sys.path[:4]}")
    bad = 0
    for name in sorted(own):
        try:
            module = importlib.import_module(name)
        except Exception as exc:  # reported, never hidden
            print(f"IMPORT-ERROR {name}: {type(exc).__name__}: {exc}")
            bad += 1
            continue
        location = getattr(module, "__file__", None)
        if location is None:
            paths = [str(p) for p in getattr(module, "__path__", [])]
            ok = bool(paths) and Path(paths[0]).resolve().is_relative_to(src)
            print(f"{'ok ' if ok else 'BAD'} {name} [namespace; search order {paths}]")
        else:
            ok = Path(location).resolve().is_relative_to(src)
            print(f"{'ok ' if ok else 'BAD'} {name} -> {location}")
        bad += not ok
    outside = sorted(
        name for name, module in sys.modules.items()
        if name.startswith("fl_security") and getattr(module, "__file__", None)
        and not Path(module.__file__).resolve().is_relative_to(src)
    )
    print(f"loaded fl_security modules with a file outside the tree: {outside or 'none'}")
    bad += len(outside)

    sources = [p for p in tree.rglob("*.py")
               if not {"__pycache__", ".git", "data"} & set(p.parts)]
    texts = {p: p.read_text(encoding="utf-8", errors="ignore") for p in sources}
    print(f"modules present only in the other tree: {len(foreign)}")
    for name in foreign:
        parent, _, leaf = name.rpartition(".")
        patterns = [re.compile(re.escape(name) + r"\b")]
        if parent:
            patterns.append(re.compile(r"from\s+" + re.escape(parent) + r"\s+import\s+[^\n]*\b"
                                       + re.escape(leaf) + r"\b"))
        hits = sorted(str(p.relative_to(tree)) for p, text in texts.items()
                      if any(pattern.search(text) for pattern in patterns))
        print(f"  {name}: referenced by tree under test: {hits or 'no'}")
        bad += bool(hits)
    print(f"RESULT: {'PASS' if bad == 0 else f'FAIL ({bad} findings)'}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
