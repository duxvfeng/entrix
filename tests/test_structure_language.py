from entrix.structure.language import (
    CODE_EXTENSIONS,
    LANGUAGE_BY_SUFFIX,
    SUPPORTED_QUERY_TYPES,
)


def test_language_metadata_covers_supported_source_and_queries() -> None:
    assert set(LANGUAGE_BY_SUFFIX) == CODE_EXTENSIONS
    assert {"python", "typescript", "rust", "go", "java"} <= set(LANGUAGE_BY_SUFFIX.values())
    assert "tests_for" in SUPPORTED_QUERY_TYPES
    assert "file_summary" in SUPPORTED_QUERY_TYPES
