"""One check: validate the URL → render desktop + mobile → Claude measures → formula scores."""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import anthropic
from playwright.async_api import Browser, Playwright, async_playwright
from playwright.async_api import Error as PlaywrightError

from .analyzer import Analysis, AnalysisError, Analyzer
from .capture import CaptureError, DeviceCapture, capture_device, desktop_profile, mobile_profile
from .config import Settings
from .scoring import DeviceObs, SiteResult, score_site
from .urlguard import validate_url

log = logging.getLogger(__name__)

DEVICES = ("desktop", "mobile")
# (device, stage) where stage is "capture", "analyze", "done" or "failed".
Progress = Callable[[str, str], Awaitable[None]]


class CheckError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass
class DeviceRun:
    device: str
    capture: DeviceCapture | None = None
    analysis: Analysis | None = None
    error: str | None = None
    detail: str = ""


@dataclass
class CheckResult:
    id: str
    url: str
    final_url: str
    lang: str
    created_at: float
    elapsed: float
    runs: dict[str, DeviceRun]
    score: SiteResult
    fingerprints: dict[str, list[str]] = field(default_factory=dict)

    @property
    def usage(self) -> dict[str, int]:
        total: dict[str, int] = {}
        for run in self.runs.values():
            for key, value in (run.analysis.usage if run.analysis else {}).items():
                total[key] = total.get(key, 0) + value
        return total

    @property
    def models(self) -> list[str]:
        return sorted({r.analysis.model for r in self.runs.values() if r.analysis})


class Checker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key or None,
            max_retries=3,
            timeout=anthropic.Timeout(settings.analysis_timeout, connect=15.0),
        )
        self.analyzer = Analyzer(self.client, settings.model, settings.effort, settings.fallbacks)
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._browser_lock = asyncio.Lock()
        self._slots = asyncio.Semaphore(settings.max_concurrent_checks)
        self.running = 0
        self.waiting = 0

    async def start(self) -> None:
        self._pw = await async_playwright().start()
        await self._browser_instance()

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
        if self._pw is not None:
            await self._pw.stop()
        await self.client.close()

    async def _browser_instance(self) -> Browser:
        async with self._browser_lock:
            if self._browser is None or not self._browser.is_connected():
                assert self._pw is not None, "call start() first"
                self._browser = await self._pw.chromium.launch(
                    headless=True, args=["--disable-dev-shm-usage"])
            return self._browser

    async def check(self, raw_url: str, lang: str = "en", progress: Progress | None = None) -> CheckResult:
        """Raises ``UrlError`` for bad links and ``CheckError`` when no device could be analyzed."""
        url = await validate_url(raw_url, allow_private=self.settings.allow_private_urls)
        self.waiting += 1
        try:
            await self._slots.acquire()
        finally:
            self.waiting -= 1
        self.running += 1
        try:
            return await self._check(url, lang, progress)
        finally:
            self.running -= 1
            self._slots.release()

    async def _check(self, url: str, lang: str, progress: Progress | None) -> CheckResult:
        started, created = time.monotonic(), time.time()
        browser = await self._browser_instance()
        assert self._pw is not None
        s = self.settings
        profiles = (desktop_profile(self._pw, s.max_screens_desktop),
                    mobile_profile(self._pw, s.mobile_device, s.max_screens_mobile))
        runs = await asyncio.gather(*(self._run_device(browser, url, p, lang, progress) for p in profiles))
        by_device = {r.device: r for r in runs}

        analysed = {d: r for d, r in by_device.items() if r.analysis is not None}
        if not analysed:
            first = by_device["desktop"] if by_device["desktop"].error else runs[0]
            raise CheckError(first.error or "unknown", first.detail)
        score = score_site({d: DeviceObs(zones=r.analysis.zones) for d, r in analysed.items()},
                           first_screen_weight=s.first_screen_weight, desktop_weight=s.desktop_weight)

        fingerprints: dict[str, list[str]] = {}
        for run in runs:
            for key, values in ((run.capture.dom.get("fingerprints") or {}) if run.capture else {}).items():
                if isinstance(values, list):
                    fingerprints[key] = sorted(set(fingerprints.get(key, [])) | set(values))
        final_url = next((r.capture.final_url for r in runs if r.capture), url)
        return CheckResult(
            id=secrets.token_hex(4), url=url, final_url=final_url, lang=lang, created_at=created,
            elapsed=time.monotonic() - started, runs=by_device, score=score, fingerprints=fingerprints,
        )

    async def _run_device(self, browser: Browser, url: str, profile, lang: str,
                          progress: Progress | None) -> DeviceRun:
        run = DeviceRun(profile.name)

        async def notify(stage: str) -> None:
            if progress is not None:
                try:
                    await progress(profile.name, stage)
                except Exception:  # progress is cosmetic; never fail a check over it
                    log.debug("progress callback failed", exc_info=True)

        stage = "capture"
        try:
            await notify("capture")
            run.capture = await asyncio.wait_for(
                capture_device(browser, url, profile, locale=self.settings.browser_locale,
                               allow_private=self.settings.allow_private_urls),
                timeout=self.settings.capture_timeout)
            stage = "analyze"
            await notify("analyze")
            run.analysis = await asyncio.wait_for(self.analyzer.analyze(run.capture, lang),
                                                  timeout=self.settings.analysis_timeout)
            await notify("done")
            return run
        except asyncio.TimeoutError:
            run.error = "timeout" if stage == "capture" else "analysis_timeout"
        except CaptureError as exc:
            run.error, run.detail = exc.code, exc.detail
        except AnalysisError as exc:
            run.error, run.detail = f"analysis_{exc.code}", exc.detail
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            run.error, run.detail = "api_auth", exc.message
        except anthropic.RateLimitError as exc:
            run.error, run.detail = "api_rate_limit", exc.message
        except anthropic.BadRequestError as exc:
            credits = "credit balance" in exc.message.lower()
            run.error, run.detail = ("api_credits" if credits else "api_bad_request"), exc.message
        except anthropic.APIStatusError as exc:
            run.error, run.detail = "api_error", f"{exc.status_code} {exc.message}"
        except anthropic.APIConnectionError as exc:
            run.error, run.detail = "api_connection", str(exc)
        except PlaywrightError as exc:
            run.error, run.detail = "load_failed", str(exc).splitlines()[0]
        log.warning("%s %s failed at %s: %s %s", profile.name, url, stage, run.error, run.detail)
        await notify("failed")
        return run
