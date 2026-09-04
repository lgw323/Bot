import ast
from pathlib import Path


def test_f001_f045_fr029_preserve_characterization_metadata() -> None:
    """Features F001-F045; FR-029; PRESERVE trace metadata requirement."""
    missing: list[str] = []
    test_dir = Path(__file__).parent

    for path in sorted(test_dir.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue
            docstring = ast.get_docstring(node) or ""
            if not (
                "Feature" in docstring
                and "F0" in docstring
                and "FR-" in docstring
                and any(
                    mode in docstring
                    for mode in ("PRESERVE", "CORRECT", "DECIDE")
                )
            ):
                missing.append(f"{path.name}::{node.name}")

    assert missing == []
