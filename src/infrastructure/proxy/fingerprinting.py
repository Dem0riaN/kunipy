"""JSON fingerprinting utilities.

Реализация json_fingerprint.h из оригинального Kuni C++.
Создаёт стабильные идентификаторы для message arrays.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


class MessageFingerprint:
    """Creates stable fingerprints for message arrays.

    Основано на json_fingerprint.h из Kuni C++:
    - Удаляет структурные символы ({,},[,],(,)) для стабильности
    - Позволяет определить продолжение сессии через startswith()
    - Hash для управляемого размера

    Используется SessionManager для tracking сессий.
    """

    @staticmethod
    def generate(data: list[dict[str, Any]]) -> str:
        """Generate stable fingerprint for data.

        Args:
            data: List of message dictionaries

        Returns:
            Stable fingerprint string (16 chars hex)
        """
        # Serialize to stable JSON
        serialized = json.dumps(data, sort_keys=True, ensure_ascii=False)

        # Remove structural characters for stability
        stable = serialized.replace("{", "").replace("}", "")
        stable = stable.replace("[", "").replace("]", "")
        stable = stable.replace("(", "").replace(")", "")
        stable = stable.replace(" ", "").replace("\n", "")

        # Hash for manageable size
        return hashlib.sha256(stable.encode()).hexdigest()[:16]

    @staticmethod
    def is_continuation(current: str, previous: str) -> bool:
        """Check if current fingerprint is continuation of previous.

        Args:
            current: Current fingerprint
            previous: Previous fingerprint

        Returns:
            True if current continues previous session
        """
        return current.startswith(previous)
