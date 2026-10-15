"""What a pipeline flow says outside its steps: the greeting and first question, lines to pre-warm, the preview."""

from __future__ import annotations

from app.flows.context import CallContext
from app.voice.languages import normalize_language, phrase


class PipelineLinesMixin:
    # ---- greeting --------------------------------------------------------------------------------
    def greeting(self, ctx: CallContext, language: str) -> str:
        if not ctx.inbound:
            return super().greeting(ctx, language)
        lang = normalize_language(language)
        key = "greeting_chat" if ctx.chat else "greeting"
        bound = self.cp.bound.get("greet")
        edited = bool(bound and (bound.lines.get(lang) or {}).get(key))
        custom = str(ctx.merchant_value("custom_greeting", "") or "").strip()
        if custom and not edited:
            return custom  # the legacy single-greeting setting
        if bound is None:
            return self.inbound_greeting(ctx, lang)
        return bound.text(key, lang, business=ctx.merchant_value("business_name", ""))

    def opening_question(self, ctx: CallContext, language: str) -> str:
        bound = self.cp.bound.get("greet")
        if ctx.inbound and bound is not None and bound.enabled:
            return bound.text("opening_question", language, business=ctx.merchant_value("business_name", ""))
        return super().opening_question(ctx, language)

    # ---- cache warming / preview -------------------------------------------------------------------
    def prefetch_lines(self, ctx: CallContext, language: str) -> list[str]:
        lines = super().prefetch_lines(ctx, language)
        for bound in self.cp.sequence():
            lines += bound.skill.prefetch(bound, ctx, language)
        lines.append(phrase("amend_question", language))
        farewell = self.farewell(ctx, language)
        if farewell:
            lines.append(farewell)
        return [line for line in dict.fromkeys(lines) if line]

    def preview_steps(self, ctx: CallContext, language: str) -> list[str]:
        lang = normalize_language(language)
        steps = [f"{'শুভেচ্ছা' if lang == 'bn' else 'Greeting'}: \"{self.opening(ctx, lang)}\""]
        for key, skills in self.cp.branches.items():
            branch = self.blueprint.branches[key]
            label = branch.label.get(lang) or branch.label.get("en") or key
            names = [b.skill.label.get(lang) or b.skill.label.get("en") or b.key for b in skills if b.skill.kind != "effect"]
            steps.append(f"{label}: {' → '.join(names) or '—'}")
        return steps




__all__ = ["PipelineLinesMixin"]
