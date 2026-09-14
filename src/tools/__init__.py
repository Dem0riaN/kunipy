"""Tools package for kunipy utilities."""

import os
import sys

_cached_tools_module = None


def _get_tools_module():
    """Lazy load tools.py module to avoid circular dependency."""
    global _cached_tools_module
    if _cached_tools_module is None:
        import importlib.util

        # Get absolute path to src/tools.py (sibling of tools/ directory)
        src_dir = os.path.dirname(__file__)
        tools_py_path = os.path.join(src_dir, '..', 'tools.py')
        tools_py_path = os.path.abspath(tools_py_path)

        if not os.path.exists(tools_py_path):
            raise AttributeError(f"Could not find tools.py at {tools_py_path}")

        # Load tools.py as a separate module
        spec = importlib.util.spec_from_file_location('src.tools_impl', tools_py_path)
        if spec is None or spec.loader is None:
            raise AttributeError("Could not load tools.py module")

        tools_mod = importlib.util.module_from_spec(spec)
        sys.modules['src.tools_impl'] = tools_mod
        spec.loader.exec_module(tools_mod)
        _cached_tools_module = tools_mod

    return _cached_tools_module


# Lazy import to avoid circular dependency
def __getattr__(name):
    tools_mod = _get_tools_module()
    if hasattr(tools_mod, name):
        return getattr(tools_mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["OpenAITools", "Tool", "ToolContext", "create_default_tools"]
