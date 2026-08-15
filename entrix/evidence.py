"""loader 层 evidence API 的兼容包装器。"""

from entrix.loaders.evidence_loader import load_dimensions, parse_frontmatter, validate_weights

__all__ = ["load_dimensions", "parse_frontmatter", "validate_weights"]
