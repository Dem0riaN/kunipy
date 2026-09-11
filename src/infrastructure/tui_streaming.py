"""TUI streaming printer for LLM responses.

Pretty prints reasoning, content, and tool calls to console
with color coding, matching the original C++ kuni behavior.
"""

import sys
import time
from typing import Any


class TuiStreamingPrinter:
    """Pretty TUI printer for streaming LLM responses.

    Prints reasoning in dark grey, content in white, tool calls in yellow -
    incrementally as chunks arrive, like Claude's terminal output.

    Usage:
        printer = TuiStreamingPrinter()
        printer.update(response)  # call each time response changes
        printer.finish()          # call once streaming is done
    """

    # ANSI color codes
    RESET = "\033[0m"
    GREY = "\033[90m"  # dark grey -- reasoning
    WHITE = "\033[97m"  # bright white -- content
    YELLOW = "\033[33m"  # yellow -- tool call args
    CYAN = "\033[36m"  # cyan -- tool call name
    DIM = "\033[2m"  # dim -- separators

    def __init__(self):
        """Initialize printer and print starting message."""
        print(f"{self.GREY}▸ Thinking...{self.RESET}", flush=True)
        self._start_time = time.monotonic()

        self._printed_reasoning_content = 0
        self._printed_reasoning = 0
        self._printed_content = 0
        self._in_reasoning = False
        self._thinking_time_printed = False
        self._tool_call_state: dict[int, dict] = {}

    def update(self, response: dict[str, Any] | Any) -> None:
        """Update display with new response chunk.

        Args:
            response: LLM response dictionary with choices or ChatResponse object
        """
        # Handle both dict and ChatResponse object
        if hasattr(response, 'choices'):
            choices = response.choices
        elif isinstance(response, dict):
            choices = response.get("choices", [])
        else:
            return

        if not choices:
            return

        msg = choices[0].get("message", {})

        # --- reasoning_content (DeepSeek style) ---
        reasoning_content = msg.get("reasoning_content") or ""
        if len(reasoning_content) > self._printed_reasoning_content:
            if self._printed_reasoning_content == 0:
                self._print_thinking_time()
                print(f"{self.GREY}▸ reasoning{self.RESET}", flush=True)
                self._in_reasoning = True

            print(f"{self.GREY}", end="", flush=True)
            self._print_delta(reasoning_content, self._printed_reasoning_content)
            print(f"{self.RESET}", end="", flush=True)
            self._printed_reasoning_content = len(reasoning_content)

        # --- reasoning (standard field) ---
        reasoning = msg.get("reasoning") or ""
        if len(reasoning) > self._printed_reasoning:
            if self._printed_reasoning == 0 and not self._in_reasoning:
                self._print_thinking_time()
                print(f"{self.GREY}▸ reasoning{self.RESET}", flush=True)
                self._in_reasoning = True

            print(f"{self.GREY}", end="", flush=True)
            self._print_delta(reasoning, self._printed_reasoning)
            print(f"{self.RESET}", end="", flush=True)
            self._printed_reasoning = len(reasoning)

        # --- content ---
        content = msg.get("content") or ""
        if len(content) > self._printed_content:
            if self._printed_content == 0:
                if not self._in_reasoning:
                    self._print_thinking_time()
                if self._in_reasoning:
                    # separator between reasoning and answer
                    print(f"\n{self.DIM}{'─' * 40}{self.RESET}", flush=True)
                    self._in_reasoning = False

            print(f"{self.WHITE}", end="", flush=True)
            self._print_delta(content, self._printed_content)
            print(f"{self.RESET}", end="", flush=True)
            self._printed_content = len(content)

        # --- tool calls ---
        tool_calls = msg.get("tool_calls", [])
        for tc in tool_calls:
            idx = tc.get("index", 0)
            if idx not in self._tool_call_state:
                self._tool_call_state[idx] = {
                    "header_printed": False,
                    "printed_args": 0
                }

            state = self._tool_call_state[idx]
            function = tc.get("function", {})
            name = function.get("name", "")

            # print header once name is known
            if not state["header_printed"] and name:
                self._print_thinking_time()
                print(f"\n{self.CYAN}⚙️ {name}{self.RESET}{self.YELLOW}(", end="", flush=True)
                state["header_printed"] = True

            if state["header_printed"]:
                args = function.get("arguments", "")
                if len(args) > state["printed_args"]:
                    print(f"{self.YELLOW}", end="", flush=True)
                    print(args[state["printed_args"]:], end="", flush=True)
                    print(f"{self.RESET}", end="", flush=True)
                    state["printed_args"] = len(args)

        sys.stdout.flush()

    def finish(self) -> None:
        """Finish printing and clean up."""
        # close any open tool call parens
        for state in self._tool_call_state.values():
            if state["header_printed"]:
                print(f"{self.YELLOW}){self.RESET}", flush=True)

        if (self._printed_content > 0 or
            self._printed_reasoning > 0 or
            self._printed_reasoning_content > 0 or
            self._tool_call_state):
            print(flush=True)

        print(f"{self.RESET}", end="", flush=True)
        sys.stdout.flush()

    def _print_thinking_time(self) -> None:
        """Print elapsed thinking time once."""
        if self._thinking_time_printed:
            return
        self._thinking_time_printed = True

        elapsed_ms = int((time.monotonic() - self._start_time) * 1000)
        print(f"{self.DIM}  ({elapsed_ms}ms){self.RESET}", flush=True)

    def _print_delta(self, text: str, printed: int) -> None:
        """Print only the new suffix of text starting from printed position.

        Args:
            text: Full text
            printed: Already printed length
        """
        if len(text) > printed:
            print(text[printed:], end="", flush=True)
