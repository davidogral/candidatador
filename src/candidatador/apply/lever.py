from __future__ import annotations

from typing import TYPE_CHECKING

from candidatador.apply.base import ApplyContext
from candidatador.apply.browser import (
    BrowserApplier,
    fill_if_present,
    fill_open_questions,
    upload_if_present,
)

if TYPE_CHECKING:
    from playwright.sync_api import Page


class LeverApplier(BrowserApplier):
    name = "lever"
    display_name = "Lever"

    @classmethod
    def supports(cls, url: str) -> bool:
        return "jobs.lever.co" in url

    def application_url(self, ctx: ApplyContext) -> str:
        url = (ctx.job.apply_url or ctx.job.url).rstrip("/")
        return url if url.endswith("/apply") else f"{url}/apply"

    def fill(self, page: Page, ctx: ApplyContext, notes: list[str]) -> None:
        p = ctx.profile.personal
        page.wait_for_selector("input[name='name']", timeout=20_000)
        # Upload first: Lever parses the resume and may prefill fields.
        if not upload_if_present(
            page,
            "input[name='resume']",
            ctx.resume.path if ctx.resume else None,
            ctx.resume_upload_name(),
        ):
            notes.append("currículo não anexado")
        page.wait_for_timeout(1500)
        fill_if_present(page, "input[name='name']", p.full_name)
        fill_if_present(page, "input[name='email']", p.email)
        fill_if_present(page, "input[name='phone']", p.phone)
        fill_if_present(page, "input[name='location']", f"{p.city}, {p.country}".strip(", "))
        fill_if_present(page, "input[name='urls[LinkedIn]']", p.linkedin)
        fill_if_present(page, "input[name='urls[GitHub]']", p.github)
        fill_if_present(page, "input[name='urls[Portfolio]']", p.portfolio)
        if ctx.cover_letter:
            fill_if_present(page, "textarea[name='comments']", ctx.cover_letter)
        fill_open_questions(page, "form", ctx, notes)

    def submit(self, page: Page) -> None:
        page.locator("#btn-submit, button[type='submit']").first.click()
        page.wait_for_load_state("networkidle")
