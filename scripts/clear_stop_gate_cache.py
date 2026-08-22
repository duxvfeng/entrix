"""清理 Stop Gate 缓存的错误状态"""

import argparse
import json
import sys
from pathlib import Path

# 保证脚本使用所在 checkout 的 entrix，而不是全局安装的旧版本
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Windows 控制台默认 GBK，无法编码 emoji 输出
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from entrix.stop_gate.revalidation import StopGateStateStore


def cmd_clear_state(args: argparse.Namespace) -> int:
    """清理 Stop Gate 缓存状态"""
    workspace = Path(args.repo).resolve() if args.repo else Path.cwd().resolve()
    state_store = StopGateStateStore(args.state_dir)

    # 列出所有缓存的状态
    state_dir = state_store.sessions_dir(workspace)
    if not state_dir.exists():
        print(f"✅ 没有缓存状态: {state_dir}")
        return 0

    # 读取所有缓存文件
    cache_files = list(state_dir.glob("*.json"))
    if not cache_files:
        print(f"✅ 缓存目录为空: {state_dir}")
        return 0

    print(f"📁 缓存目录: {state_dir}")
    print(f"📊 找到 {len(cache_files)} 个缓存文件:\n")

    for cache_file in cache_files:
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            status = data.get("status", "unknown")
            summary = data.get("summary", "")[:50]
            print(f"  - {cache_file.name}")
            print(f"    状态: {status}")
            print(f"    摘要: {summary}...")
        except Exception as e:
            print(f"  - {cache_file.name}")
            print(f"    错误: {e}")

    if args.dry_run:
        print("\n🔍 预览模式，不删除文件")
        return 0

    # 确认删除
    if not args.force:
        response = input(f"\n❓ 确认删除所有 {len(cache_files)} 个缓存文件? [y/N] ")
        if response.lower() != "y":
            print("❌ 取消删除")
            return 1

    # 删除所有缓存文件
    deleted = 0
    for cache_file in cache_files:
        try:
            cache_file.unlink()
            deleted += 1
        except Exception as e:
            print(f"❌ 删除失败 {cache_file.name}: {e}")

    print(f"\n✅ 已删除 {deleted}/{len(cache_files)} 个缓存文件")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="清理 Stop Gate 缓存的错误状态"
    )
    parser.add_argument(
        "--repo",
        help="项目根目录（默认当前目录）",
    )
    parser.add_argument(
        "--state-dir",
        help="状态存储目录（默认用户级 Entrix 缓存目录）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览模式，不实际删除",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制删除，不询问确认",
    )

    args = parser.parse_args()
    raise SystemExit(cmd_clear_state(args))
