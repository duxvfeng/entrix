"""Language metadata used by the built-in Tree-sitter graph adapter."""

from __future__ import annotations

CODE_EXTENSIONS = {
    ".go",
    ".java",
    ".py",
    ".rs",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
}

LANGUAGE_BY_SUFFIX = {
    ".go": "go",
    ".java": "java",
    ".py": "python",
    ".rs": "rust",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
}

CALL_NODE_TYPES = {
    "go": {"call_expression"},
    "java": {"method_invocation", "object_creation_expression"},
    "python": {"call"},
    "rust": {"call_expression", "macro_invocation"},
    "typescript": {"call_expression", "new_expression"},
    "tsx": {"call_expression", "new_expression"},
    "javascript": {"call_expression", "new_expression"},
}

SYMBOL_KINDS = {
    "go": {
        "type_spec": "Struct",
        "function_declaration": "Function",
        "method_declaration": "Function",
    },
    "java": {
        "class_declaration": "Class",
        "interface_declaration": "Interface",
        "enum_declaration": "Enum",
        "method_declaration": "Function",
    },
    "python": {
        "class_definition": "Class",
        "function_definition": "Function",
    },
    "rust": {
        "struct_item": "Struct",
        "enum_item": "Enum",
        "trait_item": "Trait",
        "function_item": "Function",
    },
    "typescript": {
        "class_declaration": "Class",
        "interface_declaration": "Interface",
        "enum_declaration": "Enum",
        "function_declaration": "Function",
        "method_definition": "Function",
        "variable_declarator": "Function",
    },
    "tsx": {
        "class_declaration": "Class",
        "interface_declaration": "Interface",
        "enum_declaration": "Enum",
        "function_declaration": "Function",
        "method_definition": "Function",
        "variable_declarator": "Function",
    },
    "javascript": {
        "class_declaration": "Class",
        "function_declaration": "Function",
        "method_definition": "Function",
        "variable_declarator": "Function",
    },
}

SUPPORTED_QUERY_TYPES = {
    "tests_for",
    "callers_of",
    "callees_of",
    "imports_of",
    "importers_of",
    "children_of",
    "inheritors_of",
    "file_summary",
}
