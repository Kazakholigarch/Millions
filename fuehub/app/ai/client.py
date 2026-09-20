from __future__ import annotations

from abc import ABC, abstractmethod

from app.ai.faq import build_grounding_context, compose_faq_reply


class AIClient(ABC):
    @abstractmethod
    def draft(
        self, *, clinic, lead, language: str, conversation_text: str, topics: set[str], available_slots: list
    ) -> str:
        """Return drafted reply text. `conversation_text` has already been
        PII-redacted by the caller (app/ai/draft.py) -- implementations
        must not be handed lead.contact_* fields. `available_slots` are
        real AvailabilitySlot rows so a consultation question can be
        answered with concrete bookable times."""


class FakeAIClient(AIClient):
    """Deterministic, fully offline, template-based drafter. This is the
    default provider (FUEHUB_AI_PROVIDER=fake) so the whole app runs and
    is testable with zero external credentials or network access."""

    def draft(self, *, clinic, lead, language, conversation_text, topics, available_slots) -> str:
        return compose_faq_reply(
            language=language,
            clinic=clinic,
            topics=topics,
            has_photos=lead.has_photos,
            available_slots=available_slots,
        )


class AnthropicAIClient(AIClient):
    """Real drafting via the Claude API. Selected with
    FUEHUB_AI_PROVIDER=anthropic + ANTHROPIC_API_KEY set."""

    _SYSTEM_TEMPLATE = (
        "You are a front-desk assistant for a hair transplant clinic, replying to a prospective "
        "patient's enquiry in {language}. Keep the reply warm, concise (under 120 words), and "
        "grounded only in the clinic facts given below -- never invent numbers, dates, or "
        "policies that aren't there.\n\n"
        "You MAY answer questions in these categories only: rough cost ranges by estimated graft "
        "count, the difference between FUE and DHI, what the international-patient package "
        "includes, how many days a patient typically needs to stay, and what the free "
        "consultation involves.\n\n"
        "You must NOT: assess this specific person's hair loss pattern, give a candidacy or "
        "medical opinion, discuss medication interactions or health conditions, or comment on "
        "the clinical content of any photo they sent -- a human clinician handles all of that. "
        "If they sent photos, just acknowledge them and say a specialist will personally review "
        "them.\n\nClinic facts (JSON):\n{facts}"
    )

    def __init__(self, api_key: str, model: str):
        import anthropic  # imported lazily so the package is only required when actually used

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def draft(self, *, clinic, lead, language, conversation_text, topics, available_slots) -> str:
        facts = build_grounding_context(clinic)
        if available_slots:
            from app.ai.faq import format_slot_options

            facts += "\n\nReal open consultation slots you may offer (do not invent others):\n"
            facts += format_slot_options(available_slots, clinic.timezone)
        system_prompt = self._SYSTEM_TEMPLATE.format(language=language, facts=facts)
        response = self._client.messages.create(
            model=self._model,
            max_tokens=400,
            system=system_prompt,
            messages=[{"role": "user", "content": conversation_text or "(no message text)"}],
        )
        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )
        return text.strip()


def get_ai_client(config) -> AIClient:
    provider = getattr(config, "AI_PROVIDER", "fake")
    api_key = getattr(config, "ANTHROPIC_API_KEY", "")
    if provider == "anthropic" and api_key:
        return AnthropicAIClient(api_key, getattr(config, "ANTHROPIC_MODEL", "claude-sonnet-5"))
    return FakeAIClient()
