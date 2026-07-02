"""
Manages chat history for the Claude API conversation.
Keeps the last N turns to provide context without exceeding token limits.
"""

from dataclasses import dataclass, field
from typing import Literal

MAX_HISTORY_TURNS = 10  # keep last 10 user+assistant pairs


@dataclass
class Message:
    role: Literal["user", "assistant"]
    content: str


@dataclass
class ConversationHistory:
    messages: list[Message] = field(default_factory=list)

    def add_user(self, text: str):
        self.messages.append(Message(role="user", content=text))
        self._trim()

    def add_assistant(self, text: str):
        self.messages.append(Message(role="assistant", content=text))
        self._trim()

    def _trim(self):
        # keep most recent MAX_HISTORY_TURNS pairs (2 messages per turn)
        max_messages = MAX_HISTORY_TURNS * 2
        if len(self.messages) > max_messages:
            self.messages = self.messages[-max_messages:]

    def to_api_format(self) -> list[dict]:
        """Convert to Anthropic API messages format."""
        return [{"role": m.role, "content": m.content} for m in self.messages]

    def clear(self):
        self.messages.clear()

    def __len__(self):
        return len(self.messages)
