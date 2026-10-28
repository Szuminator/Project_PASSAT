"""Wspólne typy wiadomości i odpowiedzi, niezależne od dostawcy AI."""

from dataclasses import dataclass
from typing import Literal


MessageRole = Literal["user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    role: MessageRole
    content: str


@dataclass(frozen=True)
class AssistantReply:
    text: str
    provider_name: str
    is_offline: bool
    warning: str | None = None
    is_local_rule: bool = False
