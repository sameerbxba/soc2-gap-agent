"""Where model turns come from.

Two providers, one interface. LiveProvider calls the Messages API. Replay
returns turns recorded earlier from a file.

Replay exists for two reasons. The honest one is that it lets the project run
end to end with no API key and no cost. The useful one is that it makes the
loop deterministic, which is what lets the guardrails be unit tested at all: a
control you can only exercise against a non-deterministic model is a control
you cannot actually test.
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_MODEL = "claude-sonnet-4-5"


class ProviderError(Exception):
    pass


class LiveProvider:
    """Calls the Anthropic Messages API."""

    name = "live"

    def __init__(self, model: str = DEFAULT_MODEL, api_key: str | None = None):
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise ProviderError(
                "the anthropic package is not installed. "
                "pip install -r requirements.txt, or run with --replay."
            ) from exc

        import os

        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ProviderError(
                "ANTHROPIC_API_KEY is not set. Put it in .env, or run with "
                "--replay to use the recorded session."
            )
        self.model = model
        self.client = anthropic.Anthropic(api_key=key)
        self.recorded: list[dict] = []

    def create(self, system: str, messages: list[dict], tools: list[dict]) -> dict:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=system,
            tools=tools,
            messages=messages,
        )
        turn = {
            "stop_reason": response.stop_reason,
            "content": [block.model_dump() for block in response.content],
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        }
        self.recorded.append(turn)
        return turn

    def save_recording(self, path: str | Path) -> Path:
        """Write this run's turns out so it can be replayed later."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"model": self.model, "turns": self.recorded}, indent=2),
            encoding="utf-8",
        )
        return path


class ReplayProvider:
    """Returns pre-recorded turns in order."""

    name = "replay"

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.exists():
            raise ProviderError(f"no recorded session at {self.path}")
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.model = data.get("model", "recorded")
        self.turns = data["turns"]
        self.index = 0

    def create(self, system: str, messages: list[dict], tools: list[dict]) -> dict:
        if self.index >= len(self.turns):
            raise ProviderError(
                "the recorded session ran out of turns. The loop asked for more "
                "model output than was recorded, which usually means a guardrail "
                "rejected a call that was accepted when the session was recorded."
            )
        turn = self.turns[self.index]
        self.index += 1
        turn.setdefault("usage", {"input_tokens": 0, "output_tokens": 0})
        return turn
