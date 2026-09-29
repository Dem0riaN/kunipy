"""Upstream routing for multi-backend proxy scenarios.

Enables routing requests to different LLM backends based on:
- Request path (/v1/chat/completions, /v1/embeddings)
- Model name hints
- Static configuration

Phase 5: Open-LLM-VTuber Integration
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...config import EndpointAndModel

logger = logging.getLogger(__name__)


@dataclass
class UpstreamConfig:
    """Configuration for single upstream endpoint.

    Example:
        >>> UpstreamConfig(
        ...     name="chat",
        ...     endpoint=chat_endpoint,
        ...     routes=["/v1/chat/completions"],
        ...     priority=0
        ... )
    """

    name: str  # "chat", "vision", "embeddings"
    endpoint: EndpointAndModel
    routes: list[str] = field(default_factory=list)  # Paths this upstream handles
    priority: int = 0  # For fallback ordering (lower = higher priority)

    def matches_route(self, path: str) -> bool:
        """Check if this upstream handles the given path.

        Args:
            path: Request path (e.g., "/v1/chat/completions")

        Returns:
            True if this upstream handles the path
        """
        if not self.routes:
            return False
        return path in self.routes


class UpstreamRouter:
    """Route requests to configured upstream endpoints.

    Supports:
    - Static routing by request path
    - Fallback to default upstream
    - Priority-based selection when multiple upstreams match

    Example:
        >>> upstreams = [
        ...     UpstreamConfig("chat", chat_endpoint, ["/v1/chat/completions"]),
        ...     UpstreamConfig("vision", vision_endpoint, ["/v1/chat/completions"]),
        ... ]
        >>> router = UpstreamRouter(upstreams, default_upstream)
        >>> upstream = router.get_upstream("/v1/chat/completions")
    """

    def __init__(
        self,
        upstreams: list[UpstreamConfig],
        default: UpstreamConfig,
    ):
        """Initialize upstream router.

        Args:
            upstreams: List of configured upstreams
            default: Fallback upstream when no match found
        """
        self._upstreams = sorted(upstreams, key=lambda u: u.priority)
        self._default = default
        self._route_map = self._build_route_map()

        logger.info(
            f"UpstreamRouter initialized: {len(upstreams)} upstreams, "
            f"default={default.name}"
        )

    def _build_route_map(self) -> dict[str, list[UpstreamConfig]]:
        """Build path → upstreams mapping from configs.

        Returns:
            Dictionary mapping paths to sorted upstream lists
        """
        route_map: dict[str, list[UpstreamConfig]] = {}

        for upstream in self._upstreams:
            for route in upstream.routes:
                if route not in route_map:
                    route_map[route] = []
                route_map[route].append(upstream)

        # Sort by priority within each route
        for upstreams in route_map.values():
            upstreams.sort(key=lambda u: u.priority)

        return route_map

    def get_upstream(
        self,
        path: str,
        model: str | None = None,
    ) -> UpstreamConfig:
        """Resolve upstream for request.

        Resolution order:
        1. Path-based routing from route_map
        2. Priority-based selection if multiple matches
        3. Fallback to default upstream

        Args:
            path: Request path (e.g., "/v1/chat/completions")
            model: Optional model name hint (future: model-based routing)

        Returns:
            UpstreamConfig to use for this request
        """
        # Check route map
        if path in self._route_map:
            candidates = self._route_map[path]
            if candidates:
                selected = candidates[0]  # Highest priority
                logger.debug(
                    f"Route {path} → upstream {selected.name} "
                    f"(priority={selected.priority})"
                )
                return selected

        # Fallback to default
        logger.debug(f"Route {path} → default upstream {self._default.name}")
        return self._default

    def get_all_upstreams(self) -> list[UpstreamConfig]:
        """Get all configured upstreams.

        Returns:
            List of all upstreams including default
        """
        return self._upstreams + [self._default]

    def get_upstream_by_name(self, name: str) -> UpstreamConfig | None:
        """Get upstream by name.

        Args:
            name: Upstream name

        Returns:
            UpstreamConfig if found, None otherwise
        """
        for upstream in self._upstreams:
            if upstream.name == name:
                return upstream

        if self._default.name == name:
            return self._default

        return None

    def get_upstream_count(self) -> int:
        """Get total upstream count.

        Returns:
            Number of configured upstreams (excluding default)
        """
        return len(self._upstreams)
