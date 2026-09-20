"""Dependency Injection module.

Provides central dependency container and factory functions.
"""

from .container import Dependencies, create_dependencies

__all__ = ["Dependencies", "create_dependencies"]
