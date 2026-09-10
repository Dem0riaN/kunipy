"""Tools package for kunipy utilities."""

# Lazy import to avoid circular dependency
def __getattr__(name):
    if name == "create_default_tools":
        import sys
        # Import parent module's tools.py directly
        tools_module = sys.modules.get('src.tools')
        if tools_module is None or not hasattr(tools_module, 'create_default_tools'):
            # Import the tools.py file (not the package)
            from importlib import import_module
            parent = import_module('src')
            import importlib.util
            spec = importlib.util.find_spec('tools', parent.__path__)
            if spec and spec.origin:
                tools_mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(tools_mod)
                return tools_mod.create_default_tools
        return getattr(tools_module, 'create_default_tools')
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["create_default_tools"]
