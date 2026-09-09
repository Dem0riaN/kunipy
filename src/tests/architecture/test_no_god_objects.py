"""Architecture tests: prevent god objects.

Enforces Single Responsibility Principle (ТЗ-001 punkt 4-11).
"""

import ast
from pathlib import Path
import pytest


def count_class_methods(file_path: Path, class_name: str) -> int:
    """Count public methods in a class (excluding __init__, private, properties)."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=str(file_path))
    except SyntaxError:
        return 0

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            methods = [
                item for item in node.body
                if isinstance(item, ast.FunctionDef) and
                not item.name.startswith('_') and
                item.name != '__init__'
            ]
            return len(methods)

    return 0


def count_file_lines(file_path: Path) -> int:
    """Count non-empty, non-comment lines in file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except:
        return 0

    count = 0
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith('#'):
            count += 1

    return count


def get_class_lines(file_path: Path, class_name: str) -> int:
    """Count lines in a specific class."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=str(file_path))
    except SyntaxError:
        return 0

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            # end_lineno - lineno gives approximate class size
            if hasattr(node, 'end_lineno') and node.end_lineno:
                return node.end_lineno - node.lineno

    return 0


class TestNoGodObjects:
    """Test that no god objects exist in the codebase."""

    @pytest.fixture
    def src_dir(self) -> Path:
        """Get src directory."""
        return Path(__file__).parent.parent.parent / "src"

    def test_no_class_exceeds_300_lines(self, src_dir: Path):
        """No class should exceed 300 lines.

        ТЗ-001 punkt 5: Split god objects into focused classes.
        Large classes violate Single Responsibility Principle.
        """
        violations = []

        for file in src_dir.rglob("*.py"):
            if "test_" in file.name or file.name == "__init__.py":
                continue

            try:
                with open(file, 'r', encoding='utf-8') as f:
                    tree = ast.parse(f.read(), filename=str(file))
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    class_lines = get_class_lines(file, node.name)
                    if class_lines > 300:
                        violations.append(
                            f"{file.relative_to(src_dir)}::{node.name}: "
                            f"{class_lines} lines (max 300)"
                        )

        assert not violations, (
            "Classes must not exceed 300 lines:\n" +
            "\n".join(f"  - {v}" for v in violations)
        )

    def test_no_class_has_too_many_responsibilities(self, src_dir: Path):
        """No class should have more than 10 public methods.

        ТЗ-001 punkt 5: God object app.py had 11+ responsibilities.
        Classes with many methods likely violate SRP.
        """
        violations = []

        for file in src_dir.rglob("*.py"):
            if "test_" in file.name or file.name == "__init__.py":
                continue

            try:
                with open(file, 'r', encoding='utf-8') as f:
                    tree = ast.parse(f.read(), filename=str(file))
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    method_count = count_class_methods(file, node.name)
                    if method_count > 10:
                        violations.append(
                            f"{file.relative_to(src_dir)}::{node.name}: "
                            f"{method_count} public methods (max 10)"
                        )

        assert not violations, (
            "Classes must not have more than 10 public methods:\n" +
            "\n".join(f"  - {v}" for v in violations)
        )

    def test_app_py_is_thin_composition_root(self, src_dir: Path):
        """app.py should be a thin composition root (<100 lines).

        ТЗ-001 punkt 5: app.py was 727 lines god object.
        After refactoring, it should only wire dependencies.
        """
        app_file = src_dir / "app.py"
        if not app_file.exists():
            pytest.skip("app.py not found")

        line_count = count_file_lines(app_file)

        assert line_count < 100, (
            f"app.py should be thin composition root (<100 lines), "
            f"but has {line_count} lines. "
            f"Business logic should be in application/ layer."
        )

    def test_no_module_exceeds_500_lines(self, src_dir: Path):
        """No module (file) should exceed 500 lines.

        ТЗ-001 punkt 4: Keep modules focused.
        telegram_client.py was 800+ lines.
        """
        violations = []

        for file in src_dir.rglob("*.py"):
            if "test_" in file.name or file.name == "__init__.py":
                continue

            line_count = count_file_lines(file)
            if line_count > 500:
                violations.append(
                    f"{file.relative_to(src_dir)}: {line_count} lines (max 500)"
                )

        assert not violations, (
            "Modules must not exceed 500 lines:\n" +
            "\n".join(f"  - {v}" for v in violations)
        )

    def test_telegram_client_is_split(self, src_dir: Path):
        """TelegramClient should be split into client + service.

        ТЗ-001 punkt 5: telegram_client.py (800+ lines) must be split.
        """
        telegram_client = src_dir / "telegram_client.py"
        telegram_service = src_dir / "infrastructure" / "telegram_message_service.py"

        if not telegram_client.exists():
            pytest.skip("telegram_client.py not found")

        client_lines = count_file_lines(telegram_client)

        # After Phase 1, telegram_client should be <400 lines (thin TDLib wrapper)
        assert client_lines < 400, (
            f"TelegramClient should be split into client + service. "
            f"Current size: {client_lines} lines (should be <400). "
            f"High-level operations should be in TelegramMessageService."
        )
