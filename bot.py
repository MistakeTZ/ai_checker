"""Telegram bot: send a link, get an AI-likeness report for the desktop and mobile versions.

    python bot.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from collections import OrderedDict, defaultdict, deque
from html import escape

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramRetryAfter
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    BotCommand,
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
    User,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from aichecker import report
from aichecker.config import Settings, load_settings
from aichecker.i18n import pick_lang, t
from aichecker.pipeline import DEVICES, Checker, CheckError, CheckResult
from aichecker.storage import RATINGS, RESULTS, Storage
from aichecker.urlguard import UrlError, extract_url

log = logging.getLogger("aichecker.bot")

RATING_BUCKETS = ((0, 20), (20, 40), (40, 60), (60, 80), (80, 100))
KEEP_RESULTS = 300  # recent results kept in memory for the inline buttons


class ReportAction(CallbackData, prefix="r"):
    action: str  # details | summary | json | rate
    rid: str
    value: int = 0


def url_from_message(message: Message) -> str | None:
    text = message.text or message.caption or ""
    for entity in message.entities or message.caption_entities or []:
        if entity.type == "text_link" and entity.url:
            return entity.url
        if entity.type == "url":
            return entity.extract_from(text)
    return extract_url(text)


class ProgressView:
    """One status message per check, edited as desktop and mobile move through their stages."""

    def __init__(self, message: Message, host: str, lang: str) -> None:
        self.message = message
        self.host = host
        self.lang = lang
        self.stages = {device: "wait" for device in DEVICES}
        self.queued = 0
        self._shown = message.html_text
        self._pending: asyncio.Task | None = None

    def render(self) -> str:
        lines = [t(self.lang, "progress_title", host=escape(self.host))]
        if self.queued and all(stage == "wait" for stage in self.stages.values()):
            lines.append(t(self.lang, "queued", n=self.queued))
        for device, stage in self.stages.items():
            lines.append(f"{report.ICONS[device]} {t(self.lang, device)}: {t(self.lang, 'stage_' + stage)}")
        return "\n".join(lines)

    async def update(self, device: str, stage: str) -> None:
        self.stages[device] = stage
        if self._pending is None or self._pending.done():
            self._pending = asyncio.create_task(self._flush())

    async def _flush(self) -> None:
        await asyncio.sleep(0.7)  # coalesce desktop + mobile updates into one edit
        text = self.render()
        if text == self._shown:
            return
        try:
            await self.message.edit_text(text)
            self._shown = text
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
        except TelegramBadRequest:
            pass

    async def finish(self, text: str | None = None) -> None:
        if self._pending and not self._pending.done():
            self._pending.cancel()
        try:
            if text is None:
                await self.message.delete()
            else:
                await self.message.edit_text(text)
        except TelegramBadRequest:
            pass


class BotApp:
    def __init__(self, settings: Settings, checker: Checker, storage: Storage) -> None:
        self.settings = settings
        self.checker = checker
        self.storage = storage
        self.results: OrderedDict[str, CheckResult] = OrderedDict()
        self.ratings: dict[tuple[str, int], int] = {}
        self.detail_views: set[tuple[int, int]] = set()  # (chat_id, message_id) showing details
        self.active_users: set[int] = set()
        self.history: dict[int, deque[float]] = defaultdict(deque)
        self.lang_override: dict[int, str] = {}
        self.router = Router()
        self.router.message.register(self.on_start, CommandStart())
        self.router.message.register(self.on_help, Command("help"))
        self.router.message.register(self.on_lang, Command("lang"))
        self.router.message.register(self.on_check_command, Command("check"))
        self.router.message.register(self.on_text, F.chat.type == "private", F.text | F.caption)
        self.router.callback_query.register(self.on_action, ReportAction.filter())

    def lang_for(self, user: User | None) -> str:
        if user is None:
            return "en"
        return self.lang_override.get(user.id) or pick_lang(user.language_code)

    # ── commands ──────────────────────────────────────────────────────────────
    async def on_start(self, message: Message) -> None:
        await message.answer(t(self.lang_for(message.from_user), "start"))

    async def on_help(self, message: Message) -> None:
        fs = round(self.settings.first_screen_weight * 100)
        await message.answer(t(self.lang_for(message.from_user), "help",
                               mobile=escape(self.settings.mobile_device), fs=fs, rest=100 - fs))

    async def on_lang(self, message: Message) -> None:
        if message.from_user is None:
            return
        new = "en" if self.lang_for(message.from_user) == "ru" else "ru"
        self.lang_override[message.from_user.id] = new
        await message.answer(t(new, "lang_set"))

    async def on_check_command(self, message: Message, command: CommandObject) -> None:
        url = extract_url(command.args or "")
        if url is None and message.reply_to_message:
            url = url_from_message(message.reply_to_message)
        await self.run_check(message, url)

    async def on_text(self, message: Message) -> None:
        await self.run_check(message, url_from_message(message))

    # ── checks ────────────────────────────────────────────────────────────────
    def _rate_limit_wait(self, user_id: int) -> float:
        limit = self.settings.checks_per_hour
        if not limit:
            return 0.0
        now, recent = time.time(), self.history[user_id]
        while recent and now - recent[0] > 3600:
            recent.popleft()
        return 3600 - (now - recent[0]) if len(recent) >= limit else 0.0

    async def run_check(self, message: Message, raw_url: str | None) -> None:
        user = message.from_user
        if user is None:
            return
        lang = self.lang_for(user)
        if not raw_url:
            await message.answer(t(lang, "send_url"))
            return
        if self.settings.allowed_users and user.id not in self.settings.allowed_users:
            await message.answer(t(lang, "not_allowed", user_id=user.id))
            return
        if user.id in self.active_users:
            await message.answer(t(lang, "busy"))
            return
        wait = self._rate_limit_wait(user.id)
        if wait:
            await message.answer(t(lang, "rate_limited", limit=self.settings.checks_per_hour,
                                   minutes=max(1, math.ceil(wait / 60))))
            return
        self.history[user.id].append(time.time())
        self.active_users.add(user.id)
        try:
            await self._check_and_reply(message, raw_url, lang)
        finally:
            self.active_users.discard(user.id)

    async def _check_and_reply(self, message: Message, raw_url: str, lang: str) -> None:
        host = report.host_of(raw_url)
        busy = self.checker.running + self.checker.waiting
        status = await message.answer(t(lang, "progress_title", host=escape(host)))
        view = ProgressView(status, host, lang)
        if busy >= self.settings.max_concurrent_checks:
            view.queued = busy - self.settings.max_concurrent_checks + 1
        await view.update("desktop", "wait")
        try:
            result = await self.checker.check(raw_url, lang, view.update)
        except UrlError as exc:
            if message.from_user and self.history[message.from_user.id]:
                self.history[message.from_user.id].pop()  # a bad link doesn't use up the hourly quota
            await view.finish(t(lang, f"url_{exc.code}"))
            return
        except CheckError as exc:
            await view.finish(report.render_error(host, exc.code, exc.detail, lang))
            return
        except Exception:
            log.exception("check failed for %s", raw_url)
            await view.finish(report.render_error(host, "unknown", "", lang))
            return

        self._remember(result)
        user_id = message.from_user.id if message.from_user else None
        await self.storage.append(RESULTS, {**report.to_record(result), "user_id": user_id})

        media = [InputMediaPhoto(media=BufferedInputFile(run.capture.screens[0].jpeg, f"{device}.jpg"),
                                 caption=report.album_caption(result, device, lang))
                 for device, run in result.runs.items() if run.capture and run.capture.screens]
        try:
            if len(media) > 1:
                await message.answer_media_group(media)
            elif media:
                await message.answer_photo(media[0].media, caption=media[0].caption)
        except TelegramAPIError:
            log.warning("could not send screenshots for %s", result.final_url, exc_info=True)
        await message.answer(report.render_report(result, lang, self.settings),
                             reply_markup=self._keyboard(result.id, lang, details=False, user_id=user_id))
        await view.finish()

    def _remember(self, result: CheckResult) -> None:
        self.results[result.id] = result
        while len(self.results) > KEEP_RESULTS:
            self.results.popitem(last=False)

    def _keyboard(self, rid: str, lang: str, details: bool, user_id: int | None) -> InlineKeyboardMarkup:
        kb = InlineKeyboardBuilder()
        chosen = self.ratings.get((rid, user_id)) if user_id is not None else None
        for i, (lo, hi) in enumerate(RATING_BUCKETS):
            kb.button(text=f"{'✓ ' if chosen == i else ''}{lo}–{hi}",
                      callback_data=ReportAction(action="rate", rid=rid, value=i))
        kb.button(text=t(lang, "btn_summary" if details else "btn_details"),
                  callback_data=ReportAction(action="summary" if details else "details", rid=rid))
        kb.button(text=t(lang, "btn_json"), callback_data=ReportAction(action="json", rid=rid))
        kb.adjust(5, 2)
        return kb.as_markup()

    # ── inline buttons ────────────────────────────────────────────────────────
    async def on_action(self, query: CallbackQuery, callback_data: ReportAction) -> None:
        lang = self.lang_for(query.from_user)
        result = self.results.get(callback_data.rid)
        message = query.message if isinstance(query.message, Message) else None
        if result is None or message is None:
            await query.answer(t(lang, "expired"), show_alert=True)
            return
        uid, rid = query.from_user.id, callback_data.rid
        action = callback_data.action
        if action in ("details", "summary"):
            details = action == "details"
            view_key = (message.chat.id, message.message_id)
            (self.detail_views.add if details else self.detail_views.discard)(view_key)
            text = (report.render_details if details else report.render_report)(result, lang, self.settings)
            try:
                await message.edit_text(text, reply_markup=self._keyboard(rid, lang, details, uid))
            except TelegramBadRequest:
                pass
            await query.answer()
        elif action == "json":
            body = json.dumps(report.to_record(result), ensure_ascii=False, indent=2).encode()
            name = f"ai-check-{report.host_of(result.final_url)}-{rid}.json"
            await message.answer_document(BufferedInputFile(body, name))
            await query.answer()
        elif action == "rate" and 0 <= callback_data.value < len(RATING_BUCKETS):
            lo, hi = RATING_BUCKETS[callback_data.value]
            self.ratings[(rid, uid)] = callback_data.value
            await self.storage.append(RATINGS, {
                "result_id": rid, "user_id": uid, "rated_at": time.time(), "url": result.final_url,
                "human_rating": (lo + hi) / 2, "range": [lo, hi],
                "ai_likeness": round(result.score.ai, 1), "template_likeness": round(result.score.template, 1),
            })
            await query.answer(t(lang, "rated", range=f"{lo}–{hi}"))
            details = (message.chat.id, message.message_id) in self.detail_views
            try:
                await message.edit_reply_markup(reply_markup=self._keyboard(rid, lang, details, uid))
            except TelegramBadRequest:
                pass
        else:
            await query.answer()


async def main() -> None:
    settings = load_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    if not settings.telegram_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set. Create a bot with @BotFather and add the token to .env")
    if not settings.anthropic_api_key:
        log.warning("ANTHROPIC_API_KEY is not set; relying on other Anthropic credentials")

    checker = Checker(settings)
    await checker.start()
    app = BotApp(settings, checker, Storage(settings.data_dir))
    bot = Bot(settings.telegram_token,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True))
    dispatcher = Dispatcher()
    dispatcher.include_router(app.router)
    for lang, code in (("en", None), ("ru", "ru")):
        commands = [BotCommand(command="check", description="Check a website" if lang == "en" else "Проверить сайт"),
                    BotCommand(command="help", description="How it works" if lang == "en" else "Как это работает"),
                    BotCommand(command="lang", description="Русский / English")]
        await bot.set_my_commands(commands, language_code=code)
    log.info("bot started: model=%s effort=%s first_screen_weight=%.2f",
             settings.model, settings.effort, settings.first_screen_weight)
    try:
        await dispatcher.start_polling(bot)
    finally:
        await checker.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
