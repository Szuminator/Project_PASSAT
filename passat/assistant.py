"""Koordynuje historię, osobowość Passata i wybranego dostawcę AI."""

from passat.models import AssistantReply, ChatMessage
from passat.prompts import SYSTEM_INSTRUCTION
from passat.providers.base import AIProviderError, BaseAIProvider
from passat.providers.factory import ProviderSelection
from passat.providers.offline import OfflineProvider


class PassatAssistant:
    """Obsługuje jedną rozmowę i przechowuje jej ostatnie wiadomości w pamięci."""

    MAX_HISTORY_MESSAGES = 20

    def __init__(self, selection: ProviderSelection):
        self.provider: BaseAIProvider = selection.provider
        self.provider_name = selection.provider_name
        self.is_offline = selection.is_offline
        self.startup_notice = selection.notice
        self.history: list[ChatMessage] = []

    def handle_message(self, message: str) -> AssistantReply:
        clean_message = message.strip()
        if not clean_message:
            raise ValueError("Wiadomość nie może być pusta.")

        previous_history = tuple(self.history)
        local_provider = OfflineProvider()
        if local_provider.can_answer_locally(clean_message):
            reply = local_provider.generate_reply(
                clean_message, previous_history, SYSTEM_INSTRUCTION
            )
            used_provider = local_provider.name
            is_offline = True
            warning = None
        else:
            return self._handle_with_configured_provider(clean_message, previous_history)

        self.history.extend(
            (
                ChatMessage("user", clean_message),
                ChatMessage("assistant", reply),
            )
        )
        self.history = self.history[-self.MAX_HISTORY_MESSAGES :]
        return AssistantReply(reply, used_provider, is_offline, warning)

    def _handle_with_configured_provider(
        self, clean_message: str, previous_history: tuple[ChatMessage, ...]
    ) -> AssistantReply:
        try:
            reply = self.provider.generate_reply(
                clean_message, previous_history, SYSTEM_INSTRUCTION
            )
            used_provider = self.provider_name
            is_offline = self.is_offline
            warning = None
        except AIProviderError as error:
            if self.is_offline:
                raise
            # Po ograniczonych próbach dostawcy, pojedynczy fallback offline.
            fallback = OfflineProvider()
            reply = fallback.generate_reply(
                clean_message, previous_history, SYSTEM_INSTRUCTION
            )
            used_provider = fallback.name
            is_offline = True
            warning = f"{error} Przełączono na tryb awaryjny offline."

        self.history.extend(
            (
                ChatMessage("user", clean_message),
                ChatMessage("assistant", reply),
            )
        )
        self.history = self.history[-self.MAX_HISTORY_MESSAGES :]
        return AssistantReply(reply, used_provider, is_offline, warning)
