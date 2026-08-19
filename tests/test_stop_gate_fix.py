"""测试 Stop Gate 异常处理"""

import subprocess
from pathlib import Path


def test_stop_gate_with_invalid_config():
    """测试 Stop Gate 处理无效配置"""
    print("[TEST 1] Invalid config")

    # 创建临时目录
    import tempfile
    temp_dir = Path(tempfile.mkdtemp())

    # 创建无效的 harness.yaml
    invalid_config = temp_dir / "harness.yaml"
    invalid_config.write_text("invalid: yaml: content: [", encoding="utf-8")

    # 运行 stop-gate
    result = subprocess.run(
        ["python", "-m", "entrix.cli", "stop-gate"],
        cwd=temp_dir,
        capture_output=True,
        text=True,
        timeout=5,
    )

    print(f"   Exit code: {result.returncode}")
    print(f"   stderr: {result.stderr[:200]}")

    # 应该返回 0（放行），而不是阻塞
    if result.returncode == 0:
        print("   PASS: Exception handled correctly\n")
        return True
    else:
        print("   FAIL: Should pass on exception\n")
        return False


def test_stop_gate_no_config():
    """测试 Stop Gate 处理没有配置的情况"""
    print("[TEST 2] No config file")

    import tempfile
    temp_dir = Path(tempfile.mkdtemp())

    result = subprocess.run(
        ["python", "-m", "entrix.cli", "stop-gate"],
        cwd=temp_dir,
        capture_output=True,
        text=True,
        timeout=5,
    )

    print(f"   Exit code: {result.returncode}")

    if result.returncode == 0:
        print("   PASS: No config handled correctly\n")
        return True
    else:
        print("   FAIL: Should pass with no config\n")
        return False


def test_clear_cache_script():
    """测试缓存清理脚本"""
    print("[TEST 3] Cache clear script")

    result = subprocess.run(
        ["python", "scripts/clear_stop_gate_cache.py", "--dry-run"],
        capture_output=True,
        text=True,
        timeout=5,
    )

    print(f"   Exit code: {result.returncode}")
    print(f"   stdout: {result.stdout[:200]}")

    if "--dry-run" in result.stdout:
        print("   PASS: Clear script works\n")
        return True
    else:
        print("   FAIL: Clear script output abnormal\n")
        return False


def main():
    print("=" * 60)
    print("Stop Gate Exception Handling Tests")
    print("=" * 60 + "\n")

    results = []

    results.append(test_stop_gate_no_config())
    results.append(test_stop_gate_with_invalid_config())
    results.append(test_clear_cache_script())

    print("=" * 60)
    print(f"Results: {sum(results)}/{len(results)} passed")
    print("=" * 60)

    if all(results):
        print("\n[PASS] All tests passed!")
        return 0
    else:
        print("\n[FAIL] Some tests failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
