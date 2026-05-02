"""Interactive confirmation/diagnostic prompt builders."""

from __future__ import annotations


class InteractivePromptBuilderMixin:
    def build_suspect_intent_change_message(self, stop_info: dict | None) -> str:
        ctx = self._recovery_context(stop_info)
        suspicion = ctx.suspicion or {}
        old_goal = str(suspicion.get("old_goal") or "")
        new_goal = str(suspicion.get("new_goal") or "")
        reason = ctx.reason or "suspect_intent_relabel_repeat"
        parts = [
            "Модель підозріло змінила поточний intent contract у межах тієї самої лінії роботи.",
            f"Причина: {reason}.",
        ]
        if old_goal:
            parts.append(f"Стара ціль контракту: {old_goal}")
        if new_goal:
            parts.append(f"Нова ціль контракту: {new_goal}")
        parts.extend(
            [
                "Обери один із варіантів:",
                "- Keep original goal: змусити модель триматися попередньої цілі контракту.",
                "- Allow changed goal: дозволити нову ціль один раз.",
                "- Stop and answer from current evidence: зупинити tool use і відповісти з уже зібраного.",
            ]
        )
        return "\n".join(parts)

    def build_intent_overrun_message(self, stop_info: dict | None) -> str:
        ctx = self._recovery_context(stop_info)
        reason = ctx.reason or "intent_step_limit_exceeded"
        return (
            "Поточний intent contract досяг жорсткого ліміту кроків. Далі агент не повинен продовжувати самовільно.\n"
            f"Причина: {reason}.\n"
            "Пріоритет зараз: якнайшвидше чисто завершити роботу з уже наявного evidence.\n"
            "Продовження НЕ означає: знову відкривати exploration або повторювати вже зроблене дослідження.\n"
            "Продовження означає: або чисто завершити відповідь з уже досягнутого стану, або зробити рівно наступний валідний крок, якщо ще бракує конкретної деталі.\n"
            "Обери один із двох варіантів:\n"
            "- Approve more steps: дозволити ще невеликий бюджет кроків для ЦЬОГО самого intent contract.\n"
            "- Stop and answer from current evidence: зупинити tool use і отримати відповідь лише з уже зібраного."
        )

    def build_suspect_intent_change_confirmation_suffix(self) -> str:
        return "\nТак = Allow changed goal. Ні = Keep original goal."

    def build_intent_overrun_confirmation_suffix(self) -> str:
        return "\nТак = Approve more steps. Ні = Stop and answer from current evidence."

