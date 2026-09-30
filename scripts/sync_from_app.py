#!/usr/bin/env python3
"""从主程序仓库同步内置资源到本数据仓库，然后重算 manifest.json。

用法：
    python scripts/sync_from_app.py [--app ../xuanshu] [--version 2026.09.30] [--dry-run]

做的事：
    1. 把 <app>/resources/{rules,knowledge,templates,data} 下的文件全量镜像过来
       （目标目录里多出来的文件会被删除，保证两边一致）；
    2. 重新生成 manifest.json（sha256 按**原始字节**计算，与客户端校验口径一致）。

注意：
    - 本脚本只写本仓库（xuanshu-data），不碰主程序；
    - 客户端是「按字节哈希」校验的，所以这里也必须读 bytes，不能先解码成字符串。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import date
from pathlib import Path

DATA_DIRS = ["rules", "knowledge", "templates", "data"]
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_APP = ROOT.parent / "xuanshu"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return "sha256:" + h.hexdigest()


def mirror(src: Path, dst: Path, dry: bool) -> tuple[list[str], list[str]]:
    """把 src 全量镜像到 dst，返回 (新增/更新, 删除) 的文件名列表"""
    added: list[str] = []
    removed: list[str] = []
    src_files = {p.relative_to(src).as_posix(): p for p in src.rglob("*") if p.is_file()}
    dst_files = {p.relative_to(dst).as_posix(): p for p in dst.rglob("*") if p.is_file()} if dst.is_dir() else {}

    for rel, sp in sorted(src_files.items()):
        dp = dst / rel
        need = True
        if dp.is_file():
            same = sha256_of(sp) == sha256_of(dp)
            need = not same
        if need:
            added.append(rel)
            if not dry:
                dp.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(sp, dp)

    for rel, dp in sorted(dst_files.items()):
        if rel not in src_files:
            removed.append(rel)
            if not dry:
                dp.unlink()
    if not dry:
        for p in sorted(dst.rglob("*"), reverse=True):
            if p.is_dir() and not any(p.iterdir()):
                p.rmdir()
    return added, removed


def write_manifest(version: str, dry: bool) -> int:
    files: list[dict[str, object]] = []
    for d in DATA_DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_file():
                files.append(
                    {
                        "path": p.relative_to(ROOT).as_posix(),
                        "hash": sha256_of(p),
                        "size": p.stat().st_size,
                    }
                )
    if not files:
        print("未找到任何数据文件，请检查目录结构。", file=sys.stderr)
        return 1
    manifest = {"version": version, "generatedAt": date.today().isoformat(), "files": files}
    if not dry:
        (ROOT / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return len(files)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", default=str(DEFAULT_APP), help="主程序仓库路径（含 resources/）")
    ap.add_argument("--version", default=date.today().strftime("%Y.%m.%d"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    app = Path(args.app).resolve()
    src_root = app / "resources"
    if not src_root.is_dir():
        print(f"找不到资源目录：{src_root}", file=sys.stderr)
        return 1

    total_add = total_del = 0
    for d in DATA_DIRS:
        src = src_root / d
        if not src.is_dir():
            print(f"  跳过（源目录不存在）：{d}")
            continue
        added, removed = mirror(src, ROOT / d, args.dry_run)
        total_add += len(added)
        total_del += len(removed)
        flag = " [dry-run]" if args.dry_run else ""
        print(f"  {d:<10} 写入/更新 {len(added):>3}  删除 {len(removed):>3}{flag}")
        for f in added:
            print(f"      + {d}/{f}")
        for f in removed:
            print(f"      - {d}/{f}")

    n = write_manifest(args.version, args.dry_run)
    print(f"\n共 {n} 个文件；写入/更新 {total_add}，删除 {total_del}；version={args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
