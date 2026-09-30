#!/usr/bin/env python3
"""生成/更新 manifest.json：扫描数据文件并写入 sha256 哈希。

用法：
    python scripts/gen_manifest.py [--version 2026.09.30]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIRS = ["rules", "knowledge", "templates", "data"]
MANIFEST = ROOT / "manifest.json"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return "sha256:" + h.hexdigest()


def collect() -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    for d in DATA_DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_file():
                files.append({"path": p.relative_to(ROOT).as_posix(), "hash": sha256_of(p)})
    return files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default=date.today().strftime("%Y.%m.%d"))
    args = parser.parse_args()

    files = collect()
    if not files:
        print("未找到任何数据文件，请检查目录结构。", file=sys.stderr)
        return 1

    manifest = {"version": args.version, "files": files}
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"manifest.json 已更新：version={args.version}，共 {len(files)} 个文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
