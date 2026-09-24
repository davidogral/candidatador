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


class GreenhouseApplier(BrowserApplier):
    name = "greenhouse"
    display_name = "Greenhouse"

    @classmethod
    def supports(cls, url: str) -> bool:
        return "greenhouse.io" in url

    def fill(self, page: Page, ctx: ApplyContext, notes: list[str]) -> None:
        p = ctx.profile.personal
        page.wait_for_selector("#first_name", timeout=20_000)
        fill_if_present(page, "#first_name", p.first_name)
        fill_if_present(page, "#last_name", p.last_name)
        fill_if_present(page, "#email", p.email)
        fill_if_present(page, "#phone", p.phone)
        if not upload_if_present(
            page,
            "input#resume, input[type='file'][id*='resume']",
            ctx.resume.path if ctx.resume else None,
            ctx.resume_upload_name(),
        ):
            notes.append("currículo não anexado")
        if ctx.cover_letter:
            fill_if_present(page, "textarea#cover_letter_text", ctx.cover_letter)
        fill_open_questions(page, "form", ctx, notes)

    def submit(self, page: Page) -> None:
        page.locator("button[type='submit'], input[type='submit']").first.click()
        page.wait_for_load_state("networkidle")
