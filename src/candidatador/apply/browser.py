"""Shared Playwright plumbing for form-based appliers."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from candidatador.apply.base import Applier, ApplyContext, ApplyOutcome
from candidatador.models import ApplicationStatus

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

CAPTCHA_SELECTORS = "iframe[src*='captcha'], iframe[src*='hcaptcha'], .g-recaptcha, .h-captcha"


class BrowserApplier(Applier):
    """Template: open page -> fill() -> review/confirm -> submit()."""

    def fill(self, page: Page, ctx: ApplyContext, notes: list[str]) -> None:
        raise NotImplementedError

    def submit(self, page: Page) -> None:
        raise NotImplementedError

    def application_url(self, ctx: ApplyContext) -> str:
        return ctx.job.apply_url or ctx.job.url

    def apply(self, ctx: ApplyContext) -> ApplyOutcome:
        notes: list[str] = []
        with open_page(ctx) as page:
            page.goto(self.application_url(ctx), wait_until="domcontentloaded")
            self.fill(page, ctx, notes)

            if ctx.dry_run:
                ctx.confirm(
                    "Teste concluído: formulário preenchido e NADA foi enviado. "
                    "Confira no navegador e confirme para fechá-lo."
                )
                return ApplyOutcome(ApplicationStatus.FILLED, notes)

            needs_human = bool(page.locator(CAPTCHA_SELECTORS).count()) or any(
                a.needs_review for a in ctx.answers.log.values()
            )
            if needs_human and ctx.mode == "auto":
                notes.append("modo auto pausado: captcha ou respostas que precisam de revisão")

            if ctx.mode == "review" or needs_human:
                question = "Revise o formulário no navegador. Enviar candidatura agora?"
                if not ctx.confirm(question):
                    return ApplyOutcome(ApplicationStatus.SKIPPED, notes)

            self.submit(page)
            return ApplyOutcome(ApplicationStatus.SUBMITTED, notes)


@contextlib.contextmanager
def open_page(ctx: ApplyContext) -> Iterator[Page]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - optional extra
        raise RuntimeError(
            'Instale o extra: pip install "candidatador[apply]" && playwright install chromium'
        ) from exc

    with sync_playwright() as pw:
        kwargs: dict[str, Any] = {"headless": ctx.headless, "locale": "pt-BR"}
        if ctx.browser_state:
            ctx.browser_state.mkdir(parents=True, exist_ok=True)
            browser_ctx = pw.chromium.launch_persistent_context(str(ctx.browser_state), **kwargs)
        else:
            browser_ctx = pw.chromium.launch(headless=ctx.headless).new_context(locale="pt-BR")
        try:
            page = browser_ctx.pages[0] if browser_ctx.pages else browser_ctx.new_page()
            yield page
        finally:
            browser_ctx.close()


# --------------------------------------------------------------------------- form helpers


def fill_if_present(page: Page, selector: str, value: str) -> bool:
    if not value:
        return False
    field = page.locator(selector).first
    if field.count() and field.is_visible() and not field.input_value():
        field.fill(value)
        return True
    return False


def upload_if_present(page: Page, selector: str, path: str | None) -> bool:
    field = page.locator(selector).first
    if path and field.count():
        field.set_input_files(path)
        return True
    return False


def label_for(page: Page, field: Locator) -> str:
    """Best-effort human label of a form field (question text beats placeholders)."""
    aria = field.get_attribute("aria-label")
    if aria:
        return aria.strip()
    field_id = field.get_attribute("id")
    if field_id:
        label = page.locator(f"label[for='{field_id}']").first
        if label.count():
            return label.inner_text().strip()
    wrapper = field.locator("xpath=ancestor::*[self::label or contains(@class,'question')][1]")
    if wrapper.count():
        text = wrapper.first.inner_text().strip().split("\n")[0]
        if text:
            return text
    return (field.get_attribute("placeholder") or field.get_attribute("name") or "").strip()


def fill_open_questions(
    page: Page, form_selector: str, ctx: ApplyContext, notes: list[str]
) -> None:
    """Answer every visible, still-empty text field / textarea / native select in the form."""
    fields = page.locator(
        f"{form_selector} input[type='text']:visible, {form_selector} textarea:visible, "
        f"{form_selector} select:visible"
    )
    for i in range(fields.count()):
        field = fields.nth(i)
        tag = field.evaluate("el => el.tagName.toLowerCase()")
        question = label_for(page, field)
        if not question:
            continue
        if tag == "select":
            options = [o.strip() for o in field.locator("option").all_inner_texts() if o.strip()]
            if field.input_value():
                continue
            answer = ctx.answers.resolve(question, options)
            if answer:
                with contextlib.suppress(Exception):
                    field.select_option(label=answer.value)
                    continue
            notes.append(f"não respondida: {question}")
            continue
        if field.input_value():
            continue
        answer = ctx.answers.resolve(question)
        if answer:
            field.fill(answer.value)
        else:
            notes.append(f"não respondida: {question}")
