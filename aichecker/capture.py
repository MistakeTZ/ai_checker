"""Render a page the way a visitor sees it — on desktop and on a phone — and measure its DOM."""

from __future__ import annotations

import asyncio
import logging
import math
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import Browser, BrowserContext, Page, Playwright, Route
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout

from .features import FIRST_SCREEN, REST
from .urlguard import check_host

log = logging.getLogger(__name__)

PROBE_JS = Path(__file__).with_name("dom_probe.js").read_text(encoding="utf-8")

# Picks the element that actually scrolls (some sites scroll a wrapper, not the window).
_FIND_SCROLLER_JS = """() => {
  const root = document.scrollingElement || document.documentElement;
  let best = root;
  if (root.scrollHeight <= window.innerHeight + 50) {
    let bestExtra = 0;
    for (const el of document.querySelectorAll('body *')) {
      const cs = getComputedStyle(el);
      if (!/(auto|scroll)/.test(cs.overflowY)) continue;
      const r = el.getBoundingClientRect();
      if (r.height < innerHeight * 0.6 || r.width < innerWidth * 0.6) continue;
      const extra = el.scrollHeight - el.clientHeight;
      if (extra > bestExtra) { best = el; bestExtra = extra; }
    }
  }
  window.__aicScroller = best;
  return Math.max(best.scrollHeight, innerHeight);
}"""
_SCROLL_TO_JS = """y => {
  const s = window.__aicScroller || document.scrollingElement || document.documentElement;
  s.scrollTo({top: y, left: 0, behavior: 'instant'});
  return Math.round(s.scrollTop);
}"""
_HEIGHT_JS = """() => {
  const s = window.__aicScroller || document.scrollingElement || document.documentElement;
  return Math.max(s.scrollHeight, innerHeight);
}"""

# Popups often lock scrolling (overflow: hidden) or cover the page with a full-screen layer.
_UNLOCK_SCROLL_JS = r"""() => {
  for (const el of [document.documentElement, document.body]) {
    if (getComputedStyle(el).overflowY === 'hidden') el.style.setProperty('overflow-y', 'auto', 'important');
  }
  for (const el of document.querySelectorAll('body *')) {
    const cs = getComputedStyle(el);
    if (cs.position !== 'fixed' || !(+cs.zIndex >= 100)) continue;
    const r = el.getBoundingClientRect();
    if (r.width >= innerWidth * 0.9 && r.height >= innerHeight * 0.9) el.style.setProperty('display', 'none', 'important');
  }
  return true;
}"""

# Prefer declining non-essential cookies; accept only if no decline button exists.
_CONSENT_CLICK_JS = r"""() => {
  const KNOWN = ['#onetrust-reject-all-handler', '#CybotCookiebotDialogBodyButtonDecline',
    '#didomi-notice-disagree-button', '.cky-btn-reject', '.fc-cta-do-not-consent',
    '[data-testid="uc-deny-all-button"]', '.cmplz-deny', '#onetrust-accept-btn-handler',
    '#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll', '#didomi-notice-agree-button',
    '.cky-btn-accept', '.fc-cta-consent', '[data-testid="uc-accept-all-button"]', '.cmplz-accept'];
  const REJECT = /^(reject( all)?|decline( all)?|deny( all)?|refuse|disagree|(use )?(only )?(strictly )?necessary( cookies)?( only)?|отклонить( все)?|отказаться|только необходимые|запретить)$/i;
  const ACCEPT = /^(accept( all)?( cookies)?|allow( all)?( cookies)?|i agree|agree|got it|ok|okay|i understand|understood|принять( все)?|согласен|согласна|согласиться|хорошо|понятно|ок|разрешить( все)?)$/i;
  const CONSENT = /cookie|consent|gdpr|куки|cookie-файл|персональн/i;
  const visible = el => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  for (const sel of KNOWN) {
    const el = document.querySelector(sel);
    if (el && visible(el)) { el.click(); return 1; }
  }
  const inConsent = el => {
    for (let p = el, i = 0; p && i < 10; p = p.parentElement, i++) {
      const cs = getComputedStyle(p);
      const floating = cs.position === 'fixed' || cs.position === 'sticky' || p.tagName === 'DIALOG'
        || p.getAttribute('role') === 'dialog';
      if (floating && CONSENT.test((p.innerText || '').slice(0, 1500))) return true;
    }
    return false;
  };
  const label = el => (el.innerText || el.value || el.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
  const buttons = [...document.querySelectorAll('button, a, [role=button], input[type=button], input[type=submit]')]
    .filter(visible).filter(inConsent);
  const target = buttons.find(b => REJECT.test(label(b))) || buttons.find(b => ACCEPT.test(label(b)));
  if (target) { target.click(); return 1; }
  return 0;
}"""
_CONSENT_HIDE_JS = r"""() => {
  const CONSENT = /cookie|consent|gdpr|куки|cookie-файл/i;
  let hidden = 0;
  for (const el of document.querySelectorAll('body *')) {
    const cs = getComputedStyle(el);
    if (cs.position !== 'fixed' && cs.position !== 'sticky') continue;
    const r = el.getBoundingClientRect();
    if (r.width < 200 || r.height < 40) continue;
    if (CONSENT.test((el.innerText || '').slice(0, 800))) { el.style.setProperty('display', 'none', 'important'); hidden++; }
  }
  for (const f of document.querySelectorAll("iframe[id^='sp_message'], iframe[src*='consent'], iframe[title*='onsent']")) {
    f.style.setProperty('display', 'none', 'important'); hidden++;
  }
  return hidden;
}"""

_CHALLENGE = re.compile(
    r"just a moment|attention required|checking your browser|ddos-guard|access denied|"
    r"are you a robot|verify you are human|security check|captcha|доступ ограничен|"
    r"проверка браузера|вы не робот|подтвердите, что вы человек",
    re.I,
)


class CaptureError(Exception):
    """``code``: timeout, blocked_address, load_failed, not_html, http_error, bot_protection."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class DeviceProfile:
    name: str  # "desktop" | "mobile"
    context: dict
    first_screen_scale: str  # "device" renders the first screen at the device pixel ratio
    max_screens: int

    @property
    def viewport(self) -> tuple[int, int]:
        vp = self.context["viewport"]
        return vp["width"], vp["height"]


def desktop_profile(pw: Playwright, max_screens: int) -> DeviceProfile:
    return DeviceProfile(
        name="desktop",
        context={
            "viewport": {"width": 1440, "height": 900},
            "device_scale_factor": 1,
            "is_mobile": False,
            "has_touch": False,
            "user_agent": pw.devices["Desktop Chrome"]["user_agent"],
        },
        first_screen_scale="css",
        max_screens=max_screens,
    )


def mobile_profile(pw: Playwright, device_name: str, max_screens: int) -> DeviceProfile:
    descriptor = dict(pw.devices.get(device_name) or pw.devices["iPhone 15"])
    descriptor.pop("default_browser_type", None)
    descriptor["device_scale_factor"] = 2  # crisp first screen without 3x token cost
    return DeviceProfile(name="mobile", context=descriptor, first_screen_scale="device",
                         max_screens=max_screens)


@dataclass
class Screen:
    index: int
    zone: str
    y: int  # top of the captured slice, CSS px from the top of the page
    height: int  # CSS px
    jpeg: bytes = field(repr=False)


@dataclass
class DeviceCapture:
    device: str
    viewport: tuple[int, int]
    url: str
    final_url: str
    status: int | None
    title: str
    page_height: int
    screens: list[Screen]
    total_screens: int  # screens the full page would need; may exceed len(screens)
    dom: dict = field(repr=False)
    consent_dismissed: bool
    elapsed: float

    @property
    def has_rest(self) -> bool:
        return any(s.zone == REST for s in self.screens)


def plan_positions(page_height: int, vh: int, max_screens: int) -> tuple[list[int], int]:
    """Scroll offsets to capture: every screen, or an even sample down to the footer."""
    last = max(0, page_height - vh)
    if last < vh * 0.08:
        return [0], 1
    total = 1 + math.ceil(last / vh)
    if total <= max_screens:
        positions = [min(i * vh, last) for i in range(total)]
    else:
        picks = max_screens - 1
        if picks <= 1:
            positions = [0, vh][: max_screens]
        else:
            positions = [0] + [round(vh + (last - vh) * j / (picks - 1)) for j in range(picks)]
    return sorted(set(positions)), total


async def install_guard(context: BrowserContext) -> None:
    """Abort every request (redirects and subresources too) that targets a non-public host."""
    verdicts: dict[str, asyncio.Task] = {}

    async def handle(route: Route) -> None:
        parts = urlsplit(route.request.url)
        if parts.scheme not in ("http", "https"):
            await route.continue_()
            return
        host = parts.hostname or ""
        if host not in verdicts:
            verdicts[host] = asyncio.ensure_future(check_host(host))
        try:
            if await verdicts[host] == "ok":
                await route.continue_()
            else:
                log.info("blocked request to non-public host %s", host)
                await route.abort("blockedbyclient")
        except PlaywrightError:
            pass  # page already closed

    await context.route("**/*", handle)


async def _settle(page: Page) -> None:
    for state, timeout in (("load", 12_000), ("networkidle", 5_000)):
        try:
            await page.wait_for_load_state(state, timeout=timeout)
        except PlaywrightTimeout:
            pass
    try:
        await asyncio.wait_for(
            page.evaluate("() => document.fonts ? document.fonts.ready.then(() => true) : true"), 5)
    except (asyncio.TimeoutError, PlaywrightError):
        pass
    await page.wait_for_timeout(1200)  # hero entrance animations


async def _is_challenge(page: Page, title: str, status: int | None) -> bool:
    if _CHALLENGE.search(title or ""):
        return True
    try:
        text = await page.evaluate("() => (document.body && document.body.innerText || '').slice(0, 3000)")
    except PlaywrightError:  # a late JS redirect replaced the document; the next steps see the new page
        await page.wait_for_load_state("load")
        return False
    if len(text) < 600 and _CHALLENGE.search(text):
        return True
    return status in (403, 429, 503) and bool(re.search(r"cloudflare|ray id|ddos|captcha|robot", text, re.I))


async def _dismiss_consent(page: Page) -> bool:
    try:
        clicked = await page.evaluate(_CONSENT_CLICK_JS)
        if clicked:
            await page.wait_for_timeout(700)
        hidden = await page.evaluate(_CONSENT_HIDE_JS)
        return bool(clicked or hidden)
    except PlaywrightError:
        return False  # a consent click navigated the page; carry on with what loaded


async def _preload(page: Page, vh: int, max_px: int) -> int:
    """Scroll down once so lazy images load and scroll-reveal animations fire."""
    deadline = time.monotonic() + 15
    height = await page.evaluate(_FIND_SCROLLER_JS)
    y = 0
    while time.monotonic() < deadline:
        y += int(vh * 0.85)
        if y >= min(height, max_px) - vh * 0.5:
            break
        await page.evaluate(_SCROLL_TO_JS, y)
        await page.wait_for_timeout(180)
        height = await page.evaluate(_HEIGHT_JS)
    await page.evaluate(_SCROLL_TO_JS, min(height, max_px))
    await page.wait_for_timeout(500)
    return min(await page.evaluate(_HEIGHT_JS), max_px)


async def _scroll_to(page: Page, y: int, device: str) -> int:
    """Scroll to ``y``; if the page doesn't get there, let it settle, re-detect the scroller and
    lift popup scroll locks before giving up (a silent failure would drop the rest of the page)."""
    actual = await page.evaluate(_SCROLL_TO_JS, y)
    for fix in ("settle", "unlock"):
        if actual >= y - 2:
            return actual
        if fix == "settle":
            await page.wait_for_timeout(400)
            await page.evaluate(_FIND_SCROLLER_JS)
        else:
            await page.keyboard.press("Escape")
            await page.evaluate(_UNLOCK_SCROLL_JS)
        actual = await page.evaluate(_SCROLL_TO_JS, y)
    if actual < y - 2:
        log.warning("%s: wanted to scroll to %d but reached %d (page height now %d)",
                    device, y, actual, await page.evaluate(_HEIGHT_JS))
    return actual


async def capture_device(browser: Browser, url: str, profile: DeviceProfile, *, locale: str,
                         allow_private: bool) -> DeviceCapture:
    started = time.monotonic()
    vw, vh = profile.viewport
    context = await browser.new_context(
        **profile.context, locale=locale, service_workers="block", accept_downloads=False)
    try:
        if not allow_private:
            await install_guard(context)
        page = await context.new_page()
        page.set_default_timeout(15_000)
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        except PlaywrightTimeout as exc:
            raise CaptureError("timeout", str(exc).splitlines()[0]) from exc
        except PlaywrightError as exc:
            message = str(exc)
            code = "blocked_address" if "ERR_BLOCKED_BY_CLIENT" in message else (
                "not_html" if "Download is starting" in message else "load_failed")
            raise CaptureError(code, message.splitlines()[0]) from exc

        status = response.status if response else None
        content_type = (await response.header_value("content-type") or "") if response else ""
        if content_type and "html" not in content_type.lower():
            raise CaptureError("not_html", content_type)
        await _settle(page)
        try:
            title = await page.title()
        except PlaywrightError:  # navigated again while settling
            await page.wait_for_load_state("load")
            title = await page.title()
        if await _is_challenge(page, title, status):
            raise CaptureError("bot_protection", title)
        if status and status >= 400:
            raise CaptureError("http_error", str(status))
        consent = await _dismiss_consent(page)

        screens = [Screen(0, FIRST_SCREEN, 0, vh,
                          await page.screenshot(type="jpeg", quality=85, scale=profile.first_screen_scale))]
        page_height = await _preload(page, vh, max_px=vh * 40)
        positions, total = plan_positions(page_height, vh, profile.max_screens)
        prev_bottom = vh
        for y in positions[1:]:
            actual = await _scroll_to(page, y, profile.name)
            await page.wait_for_timeout(450)  # in-view animations
            overlap = max(0, prev_bottom - actual)
            if vh - overlap < 40:
                continue
            clip = {"x": 0, "y": overlap, "width": vw, "height": vh - overlap} if overlap else None
            shot = await page.screenshot(type="jpeg", quality=80, scale="css", clip=clip)
            screens.append(Screen(len(screens), REST, actual + overlap, vh - overlap, shot))
            prev_bottom = actual + vh

        await page.evaluate(_SCROLL_TO_JS, 0)
        await page.wait_for_timeout(300)
        probe_opts = {"budgetMs": 3000, "maxTextChars": 9000, "viewportWidth": vw, "viewportHeight": vh}
        dom = await asyncio.wait_for(page.evaluate(PROBE_JS, probe_opts), 20)
        return DeviceCapture(
            device=profile.name, viewport=(vw, vh), url=url, final_url=page.url, status=status,
            title=title, page_height=page_height, screens=screens, total_screens=total, dom=dom,
            consent_dismissed=consent, elapsed=time.monotonic() - started,
        )
    finally:
        await context.close()
