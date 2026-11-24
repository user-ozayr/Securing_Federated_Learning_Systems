"""Move files left by an earlier attempt out of completed run directories.

Before the suite moved unfinished attempts aside automatically, a repeated run
reused its directory; an ``*_abort.json`` of the earlier attempt could remain
next to the completed repeat. Such a file is stale when it is older than the
repeat's start time. It is moved (never deleted) next to its identical copy in
``failed_attempts/`` (identity checked by SHA-256); files without an identical
archived copy are left in place and reported. Every action is logged in
``failed_attempts/STALE_FILES_MOVED.txt``.

Usage: python move_stale_attempt_files.py <experiments_root>
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    root = Path(sys.argv[1])
    log = []
    for meta_path in sorted(root.glob("runs/*/*/run_metadata.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("status") != "completed":
            continue
        run_dir = meta_path.parent
        started = dt.datetime.strptime(meta["started_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=dt.timezone.utc).timestamp()
        for stale in sorted(run_dir.glob("*_abort.json")):
            if stale.stat().st_mtime >= started:
                log.append(f"KEPT (written by this run): {stale.relative_to(root)}")
                continue
            digest = sha256(stale)
            copies = [p for p in sorted(root.glob(f"failed_attempts/*/{meta['study']}/{run_dir.name}/{stale.name}"))
                      if sha256(p) == digest]
            if not copies:
                log.append(f"KEPT (no identical archived copy): {stale.relative_to(root)}")
                continue
            target = copies[0].with_name(stale.name + ".stale-copy-from-repeat-directory")
            shutil.move(str(stale), str(target))
            log.append(f"MOVED {stale.relative_to(root)} -> {target.relative_to(root)} "
                       f"(sha256 {digest}, identical to {copies[0].relative_to(root)})")
    header = [
        "Stale files of earlier attempts found in completed run directories",
        "",
        "Each was written by a failed earlier attempt (older than the repeat's start time).",
        "It was moved next to its identical archived copy; nothing was deleted.",
        f"Performed (UTC): {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "",
    ]
    out = root / "failed_attempts" / "STALE_FILES_MOVED.txt"
    out.write_text("\n".join(header + log) + "\n", encoding="utf-8")
    print("\n".join(log))
    print(f"{sum(line.startswith('MOVED') for line in log)} moved; log: {out}")


if __name__ == "__main__":
    main()
