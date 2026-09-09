"""Architecture tests: layer boundaries.

Enforces clean architecture rules (ТЗ-001 punkt 10).
Prevents forbidden dependencies between layers.
"""

import ast
from pathlib import Path
import pytest


def get_imports_from_file(file_path: Path) -> set[str]:
    """Extract all import statements from a Python file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=str(file_path))
    except SyntaxError:
        return set()

    imports = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split('.')[0])

    return imports


def get_python_files(directory: Path) -> list[Path]:
    """Get all Python files in directory recursively."""
    if not directory.exists():
        return []
    return list(directory.rglob("*.py"))


class TestLayerBoundaries:
    """Test that layer boundaries are respected."""

    @pytest.fixture
    def src_dir(self) -> Path:
        """Get src directory."""
        return Path(__file__).parent.parent.parent / "src"

    def test_domain_does_not_import_infrastructure(self, src_dir: Path):
        """Domain layer must not depend on infrastructure.

        ТЗ-001 punkt 10: Domain is innermost layer.
        """
        domain_dir = src_dir / "domain"
        if not domain_dir.exists():
            pytest.skip("domain directory not found")

        violations = []

        for file in get_python_files(domain_dir):
            content = file.read_text(encoding='utf-8')

            # Check for direct infrastructure imports
            if "from infrastructure" in content or "import infrastructure" in content:
                violations.append(f"{file.relative_to(src_dir)}: imports infrastructure")

            # Check for specific infrastructure modules
            forbidden = [
                "telegram_client", "openai_chat", "aiotdlib",
                "aiohttp", "asyncpg", "redis"
            ]
            for module in forbidden:
                if f"from {module}" in content or f"import {module}" in content:
                    violations.append(
                        f"{file.relative_to(src_dir)}: imports {module} (infrastructure concern)"
                    )

        assert not violations, (
            "Domain layer must not import infrastructure:\n" +
            "\n".join(f"  - {v}" for v in violations)
        )

    def test_domain_does_not_import_application(self, src_dir: Path):
        """Domain layer must not depend on application.

        ТЗ-001 punkt 10: Domain knows nothing about application layer.
        """
        domain_dir = src_dir / "domain"
        if not domain_dir.exists():
            pytest.skip("domain directory not found")

        violations = []

        for file in get_python_files(domain_dir):
            content = file.read_text(encoding='utf-8')

            if "from application" in content or "import application" in content:
                violations.append(f"{file.relative_to(src_dir)}: imports application")

        assert not violations, (
            "Domain layer must not import application:\n" +
            "\n".join(f"  - {v}" for v in violations)
        )

    def test_interfaces_have_no_implementation(self, src_dir: Path):
        """Interface files must only contain Protocol/ABC definitions.

        ТЗ-001 punkt 8: Interfaces define contracts, not implementations.
        """
        interfaces_dir = src_dir / "interfaces"
        if not interfaces_dir.exists():
            pytest.skip("interfaces directory not found")

        violations = []

        for file in get_python_files(interfaces_dir):
            if file.name == "__init__.py":
                continue

            content = file.read_text(encoding='utf-8')

            # Must have Protocol or ABC
            has_protocol_or_abc = "Protocol" in content or "ABC" in content

            # Should NOT have concrete implementations
            forbidden_imports = [
                "asyncio", "aiohttp", "aiotdlib",
                "telegram_client", "openai_chat"
            ]

            has_implementation = any(
                f"import {module}" in content or f"from {module}" in content
                for module in forbidden_imports
            )

            if not has_protocol_or_abc:
                violations.append(
                    f"{file.relative_to(src_dir)}: missing Protocol/ABC"
                )

            if has_implementation:
                violations.append(
                    f"{file.relative_to(src_dir)}: contains implementation imports"
                )

        assert not violations, (
            "Interface files must only define protocols:\n" +
            "\n".join(f"  - {v}" for v in violations)
        )

    def test_application_depends_only_on_interfaces_and_domain(self, src_dir: Path):
        """Application layer should depend on interfaces/domain, not infrastructure.

        ТЗ-001 punkt 10: Application → Domain/Interfaces, not Infrastructure.
        """
        application_dir = src_dir / "application"
        if not application_dir.exists():
            pytest.skip("application directory not found")

        violations = []

        for file in get_python_files(application_dir):
            content = file.read_text(encoding='utf-8')

            # Check for infrastructure imports (should use interfaces instead)
            forbidden = [
                "from infrastructure.telegram_client",
                "from infrastructure.openai_chat",
                "import telegram_client",
                "import openai_chat",
            ]

            for pattern in forbidden:
                if pattern in content:
                    violations.append(
                        f"{file.relative_to(src_dir)}: {pattern} "
                        "(should use interface instead)"
                    )

        assert not violations, (
            "Application layer must depend on interfaces, not concrete infrastructure:\n" +
            "\n".join(f"  - {v}" for v in violations)
        )

    def test_no_circular_imports_between_layers(self, src_dir: Path):
        """No circular dependencies between layers.

        ТЗ-001 punkt 11: Dependency graph must be acyclic.
        """
        layers = ["interfaces", "domain", "application", "infrastructure"]

        # Build dependency graph
        dependencies = {layer: set() for layer in layers}

        for layer in layers:
            layer_dir = src_dir / layer
            if not layer_dir.exists():
                continue

            for file in get_python_files(layer_dir):
                imports = get_imports_from_file(file)

                for imp in imports:
                    for other_layer in layers:
                        if imp == other_layer or imp.startswith(f"{other_layer}."):
                            dependencies[layer].add(other_layer)

        # Check for cycles
        def has_cycle(layer: str, visited: set, stack: list) -> bool:
            visited.add(layer)
            stack.append(layer)

            for dep in dependencies.get(layer, []):
                if dep not in visited:
                    if has_cycle(dep, visited, stack):
                        return True
                elif dep in stack:
                    return True

            stack.pop()
            return False

        for layer in layers:
            visited = set()
            stack = []
            if has_cycle(layer, visited, stack):
                pytest.fail(
                    f"Circular dependency detected starting from {layer}. "
                    f"Dependency chain: {' → '.join(stack)}"
                )
