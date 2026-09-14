"""Prompt loading system for Kuni character.

Loads and manages prompt files from the prompts/ directory, following the
original C++ Kuni architecture where prompts are modular and hot-reloadable.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _strip_front_matter(text: str) -> str:
    """Remove YAML front matter (---...---) from the beginning of a prompt file."""
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        # Find the closing ---
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join(lines[i + 1 :]).strip()
    return text.strip()


def _substitute_prompt_vars(text: str, config=None) -> str:
    """Replace ${CHARACTER_NAME}, ${PAPIK_NAME}, ${CHARACTER_NICKNAME} placeholders
    with actual config values.

    Uses simple string replacement (not Template) to avoid errors on
    arbitrary $-prefixed text in prompt files.
    """
    if config is None:
        return text
    text = text.replace("${CHARACTER_NAME}", config.character_name)
    text = text.replace("${CHARACTER_NICKNAME}", config.character_nickname or config.character_name)
    text = text.replace("${PAPIK_NAME}", config.papik_name or "your owner")
    return text


def load_prompt(prompt_name: str, prompts_dir: str = "prompts", config=None) -> str:
    """Load a single prompt file from prompts/ directory.

    Args:
        prompt_name: Name of the prompt file (e.g., "system", "anti_repeat")
        prompts_dir: Directory containing prompt files
        config: Config instance for variable substitution (${CHARACTER_NAME} etc.)

    Returns:
        Prompt text with front matter stripped and variables substituted,
        empty string if file doesn't exist
    """
    prompt_path = Path(prompts_dir) / f"{prompt_name}.md"

    if not prompt_path.exists():
        logger.warning(f"Prompt file not found: {prompt_path}")
        return ""

    try:
        text = prompt_path.read_text(encoding="utf-8")
        text = _strip_front_matter(text)
        return _substitute_prompt_vars(text, config)
    except Exception as e:
        logger.error(f"Failed to load prompt {prompt_path}: {e}")
        return ""


def load_system_prompt(prompts_dir: str = "prompts", config=None) -> str:
    """Load the main system.md prompt that describes Kuni's workflow.

    This is the universal system prompt that applies to all characters.
    Character-specific traits come from character_base.md.
    """
    return load_prompt("system", prompts_dir, config=config)


def load_anti_repeat_prompt(prompts_dir: str = "prompts", config=None) -> str:
    """Load the anti_repeat.md prompt shown when LLM sends repeated messages."""
    return load_prompt("anti_repeat", prompts_dir, config=config)


def load_messages_epilogue(prompts_dir: str = "prompts", config=None) -> str:
    """Load messages_epilogue.md - critical instructions inserted with each message batch.

    This prompt is kept small but contains essential anti-prompt-injection and
    quality guidelines.
    """
    return load_prompt("messages_epilogue", prompts_dir, config=config)


def build_full_system_prompt(
    character_persona: str,
    working_memory: str = "",
    diary_context: str = "",
    prompts_dir: str = "prompts",
    config=None,
) -> str:
    """Build the complete system prompt combining all components.

    Structure (following original Kuni):
    1. Main system.md - workflow and instructions
    2. Character persona (character_base.md + appearance)
    3. Working memory (things to remember)
    4. Diary context (related memories)

    Args:
        character_persona: Combined character_base + appearance text
        working_memory: Current working memory/short-term context
        diary_context: Relevant memories from diary
        prompts_dir: Directory containing prompt files
        config: Config for ${CHARACTER_NAME} substitution in system.md

    Returns:
        Full system prompt ready for LLM
    """
    parts = []

    # 1. Main system instructions (universal)
    system_prompt = load_system_prompt(prompts_dir, config=config)
    if system_prompt:
        parts.append(system_prompt)

    # 2. Character persona (character-specific)
    if character_persona.strip():
        parts.append(character_persona)

    # 3. Working memory
    if working_memory.strip():
        parts.append(f"\n<things_to_remember>\n{working_memory.strip()}\n</things_to_remember>")

    # 4. Diary context
    if diary_context.strip():
        parts.append(f"\n<related_memories>\n{diary_context.strip()}\n</related_memories>")

    return "\n\n".join(parts)


def build_messages_with_epilogue(
    messages: list,
    prompts_dir: str = "prompts",
    config=None,
) -> list:
    """Add messages_epilogue.md to the message list.

    The epilogue contains critical instructions that should be reinforced
    with each batch of messages (anti-prompt-injection, quality guidelines).

    Args:
        messages: List of Message objects or dicts
        prompts_dir: Directory containing prompt files
        config: Config for variable substitution in epilogue

    Returns:
        Messages with epilogue appended as user message if epilogue exists
    """
    # Convert Message objects to dicts first
    result = [msg.to_dict() if hasattr(msg, 'to_dict') else msg for msg in messages]

    epilogue = load_messages_epilogue(prompts_dir, config=config)
    if not epilogue:
        return result

    # Append epilogue as a USER message (not system) to avoid
    # "System message must be at the beginning" error from some providers
    result.append({
        "role": "user",
        "content": epilogue
    })

    return result
