from entrix.cli_runtime import runtime_mode


def test_runtime_mode_normalizes_full_run_tiers() -> None:
    assert runtime_mode(None) == "full"
    assert runtime_mode("") == "full"
    assert runtime_mode("normal") == "full"
    assert runtime_mode("fast") == "fast"
