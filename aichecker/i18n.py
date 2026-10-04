"""User-facing strings (Telegram HTML). Russian for ru/uk/be/kk Telegram users, English otherwise."""

from __future__ import annotations

RU_LANGS = {"ru", "uk", "be", "kk"}


def pick_lang(language_code: str | None) -> str:
    return "ru" if (language_code or "").split("-")[0].lower() in RU_LANGS else "en"


STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "start": (
            "👋 <b>AI Site Checker</b>\n\n"
            "Send me a link and I'll tell you how AI-generated the site <i>looks</i> to a visitor.\n\n"
            "I open it in a desktop and a mobile browser, take screenshots while scrolling, "
            "and Claude measures 48 AI signals, 12 human signals and 7 typical AI patterns. "
            "A fixed formula turns that into a 0–100 score. The first screen weighs more than the rest of the page.\n\n"
            "Try: <code>example.com</code>"
        ),
        "help": (
            "<b>How it works</b>\n"
            "1. Desktop (1440×900) and mobile ({mobile}) renders, screenshot by screenshot.\n"
            "2. Claude reports each signal's presence, intensity, coverage and typicality, separately for the first screen and for the rest.\n"
            "3. Zone score = σ(B + Σ w·m·s·p + Σ patterns − human evidence) × 100.\n"
            "4. Device = {fs}% first screen + {rest}% the rest; site = average of desktop and mobile.\n\n"
            "<b>AI-likeness</b> — how AI-generated the design feels.\n"
            "<b>Template-likeness</b> — how generic it is, whoever made it.\n\n"
            "0–20 very human · 20–40 mostly human · 40–60 mixed · 60–80 AI-like · 80–100 strongly AI\n\n"
            "Commands: /check &lt;url&gt; · /lang · /help"
        ),
        "send_url": "Send me a website link, e.g. <code>example.com</code>",
        "url_invalid": "That doesn't look like a website address.",
        "url_scheme": "Only http:// and https:// links can be checked.",
        "url_private": "I can't open local or private network addresses.",
        "url_unresolvable": "I couldn't find that domain. Check the spelling?",
        "busy": "⏳ Your previous check is still running — one at a time, please.",
        "rate_limited": "Hourly limit reached ({limit} checks). Try again in {minutes} min.",
        "not_allowed": "This bot is private. Your Telegram ID: <code>{user_id}</code>",
        "lang_set": "Language: English 🇬🇧",
        "progress_title": "⏳ Checking <b>{host}</b>",
        "queued": "🕐 In queue ({n} ahead)…",
        "stage_wait": "waiting",
        "stage_capture": "opening and scrolling…",
        "stage_analyze": "Claude is looking…",
        "stage_done": "done ✓",
        "stage_failed": "failed ✗",
        "error_title": "😕 Couldn't check <b>{host}</b>",
        "ai_likeness": "AI-likeness",
        "template_likeness": "Template-likeness",
        "desktop": "Desktop",
        "mobile": "Mobile",
        "first_screen": "first screen",
        "below": "below",
        "weights_note": "First screen counts {fs}%, the rest of the page {rest}%.",
        "why_ai": "Why it looks AI-made",
        "why_ai_minor": "Minor AI-ish details",
        "why_human": "What looks human",
        "human_effect": "lowers the score by {n}",
        "no_ai": "No notable AI signals.",
        "mobile_more": "📱 The mobile version looks noticeably more AI-made than desktop.",
        "mobile_less": "📱 The mobile version looks noticeably less AI-made than desktop.",
        "device_failed": "⚠️ {device}: not analyzed — {reason}",
        "built_ai": "🔎 Built with <b>{names}</b> — an AI site builder (found in the page code)",
        "built_site": "🔎 Built with {names}",
        "rate_prompt": "How AI-made does it look to <i>you</i>? Your rating helps calibrate the weights.",
        "rated": "Thanks! Saved {range}.",
        "btn_details": "🔍 Details",
        "btn_summary": "⬅️ Summary",
        "btn_json": "📄 JSON",
        "expired": "This result has expired — send the link again.",
        "details_title": "🔍 <b>How the score was built</b>",
        "zone_line": "{zone} <b>{score}</b> · signals {sig} · patterns {pat} · human −{hum}",
        "patterns": "Patterns",
        "signals": "Signals",
        "screens": "📸 Screens analyzed: {items}",
        "of": "of",
        "stack": "🧱 Stack: {stack}",
        "usage": "🤖 {model} · in {inp} (cached {cached}) · out {out}{cost}",
        "album_caption": "{device} · first screen · {score}",
        "seconds": "s",
        "bucket_very_human": "very human",
        "bucket_mostly_human": "mostly human",
        "bucket_mixed": "mixed",
        "bucket_ai_like": "AI-like",
        "bucket_strongly_ai": "strongly AI-generated",
        "page_saas_or_app": "SaaS / app",
        "page_ai_product": "AI product",
        "page_agency_or_portfolio": "agency / portfolio",
        "page_local_business": "local business",
        "page_ecommerce": "online store",
        "page_personal": "personal site",
        "page_media_or_blog": "media / blog",
        "page_corporate": "corporate",
        "page_event_or_course": "event / course",
        "page_nonprofit_or_public": "non-profit / public",
        "page_other": "website",
        "err_timeout": "the page took too long to load",
        "err_blocked_address": "it redirects to a private network address",
        "err_load_failed": "the page failed to load",
        "err_not_html": "the link isn't a web page",
        "err_http_error": "the server answered with an error (HTTP {detail})",
        "err_bot_protection": "the site blocks automated browsers (bot protection / captcha)",
        "err_analysis_refusal": "Claude declined to analyze this page",
        "err_analysis_truncated": "the analysis was cut off",
        "err_analysis_invalid_json": "the analysis came back malformed",
        "err_analysis_timeout": "the analysis took too long",
        "err_api_auth": "the Anthropic API key is invalid or lacks access",
        "err_api_rate_limit": "the Anthropic API rate limit was hit — try again in a minute",
        "err_api_bad_request": "the Anthropic API rejected the request",
        "err_api_credits": "the Anthropic account is out of credits — top up in console.anthropic.com → Plans &amp; Billing",
        "err_api_error": "the Anthropic API had an error — try again later",
        "err_api_connection": "couldn't reach the Anthropic API",
        "err_unknown": "something went wrong",
    },
    "ru": {
        "start": (
            "👋 <b>AI Site Checker</b>\n\n"
            "Пришлите ссылку — я скажу, насколько сайт <i>выглядит</i> сгенерированным нейросетью.\n\n"
            "Я открываю его в десктопном и мобильном браузере, делаю скриншоты по мере прокрутки, "
            "а Claude измеряет 48 AI-признаков, 12 «человеческих» признаков и 7 типичных AI-паттернов. "
            "Фиксированная формула превращает это в оценку 0–100. Первый экран весит больше остальной страницы.\n\n"
            "Попробуйте: <code>example.com</code>"
        ),
        "help": (
            "<b>Как это работает</b>\n"
            "1. Рендер на десктопе (1440×900) и мобильном ({mobile}), экран за экраном.\n"
            "2. Claude оценивает для каждого признака присутствие, интенсивность, охват и типичность — отдельно для первого экрана и для остальной страницы.\n"
            "3. Оценка зоны = σ(B + Σ w·m·s·p + Σ паттернов − человеческие сигналы) × 100.\n"
            "4. Устройство = {fs}% первый экран + {rest}% остальное; сайт = среднее десктопа и мобильного.\n\n"
            "<b>AI-похожесть</b> — насколько дизайн ощущается сгенерированным.\n"
            "<b>Шаблонность</b> — насколько он типовой, кто бы его ни делал.\n\n"
            "0–20 явно человеческий · 20–40 скорее человеческий · 40–60 смешанный · 60–80 похож на AI · 80–100 явно AI\n\n"
            "Команды: /check &lt;ссылка&gt; · /lang · /help"
        ),
        "send_url": "Пришлите ссылку на сайт, например <code>example.com</code>",
        "url_invalid": "Это не похоже на адрес сайта.",
        "url_scheme": "Проверяю только ссылки http:// и https://.",
        "url_private": "Локальные и внутренние адреса открывать нельзя.",
        "url_unresolvable": "Не нашёл такой домен. Проверьте написание?",
        "busy": "⏳ Предыдущая проверка ещё идёт — по одной, пожалуйста.",
        "rate_limited": "Лимит {limit} проверок в час исчерпан. Попробуйте через {minutes} мин.",
        "not_allowed": "Это закрытый бот. Ваш Telegram ID: <code>{user_id}</code>",
        "lang_set": "Язык: русский 🇷🇺",
        "progress_title": "⏳ Проверяю <b>{host}</b>",
        "queued": "🕐 В очереди (впереди {n})…",
        "stage_wait": "ожидание",
        "stage_capture": "открываю и листаю…",
        "stage_analyze": "Claude смотрит…",
        "stage_done": "готово ✓",
        "stage_failed": "ошибка ✗",
        "error_title": "😕 Не удалось проверить <b>{host}</b>",
        "ai_likeness": "AI-похожесть",
        "template_likeness": "Шаблонность",
        "desktop": "Десктоп",
        "mobile": "Мобильный",
        "first_screen": "первый экран",
        "below": "ниже",
        "weights_note": "Первый экран — {fs}%, остальная страница — {rest}%.",
        "why_ai": "Почему похоже на AI",
        "why_ai_minor": "Мелкие AI-шные детали",
        "why_human": "Что выглядит по-человечески",
        "human_effect": "снижает оценку на {n}",
        "no_ai": "Заметных AI-признаков нет.",
        "mobile_more": "📱 Мобильная версия заметно больше похожа на AI, чем десктоп.",
        "mobile_less": "📱 Мобильная версия заметно меньше похожа на AI, чем десктоп.",
        "device_failed": "⚠️ {device}: не проанализирован — {reason}",
        "built_ai": "🔎 Сделан на <b>{names}</b> — это AI-конструктор сайтов (найдено в коде страницы)",
        "built_site": "🔎 Сделан на {names}",
        "rate_prompt": "А насколько AI-шным сайт кажется <i>вам</i>? Ваша оценка помогает калибровать веса.",
        "rated": "Спасибо! Записал {range}.",
        "btn_details": "🔍 Подробнее",
        "btn_summary": "⬅️ Кратко",
        "btn_json": "📄 JSON",
        "expired": "Результат устарел — пришлите ссылку ещё раз.",
        "details_title": "🔍 <b>Как посчитана оценка</b>",
        "zone_line": "{zone} <b>{score}</b> · признаки {sig} · паттерны {pat} · человек −{hum}",
        "patterns": "Паттерны",
        "signals": "Признаки",
        "screens": "📸 Проанализировано экранов: {items}",
        "of": "из",
        "stack": "🧱 Стек: {stack}",
        "usage": "🤖 {model} · вход {inp} (из кэша {cached}) · выход {out}{cost}",
        "album_caption": "{device} · первый экран · {score}",
        "seconds": "с",
        "bucket_very_human": "явно человеческий",
        "bucket_mostly_human": "скорее человеческий",
        "bucket_mixed": "смешанный",
        "bucket_ai_like": "похож на AI",
        "bucket_strongly_ai": "явно AI-сгенерированный",
        "page_saas_or_app": "SaaS / приложение",
        "page_ai_product": "AI-продукт",
        "page_agency_or_portfolio": "агентство / портфолио",
        "page_local_business": "локальный бизнес",
        "page_ecommerce": "интернет-магазин",
        "page_personal": "личный сайт",
        "page_media_or_blog": "медиа / блог",
        "page_corporate": "корпоративный",
        "page_event_or_course": "мероприятие / курс",
        "page_nonprofit_or_public": "НКО / госсектор",
        "page_other": "сайт",
        "err_timeout": "страница слишком долго грузилась",
        "err_blocked_address": "сайт перенаправляет на внутренний адрес",
        "err_load_failed": "страница не загрузилась",
        "err_not_html": "по ссылке не веб-страница",
        "err_http_error": "сервер ответил ошибкой (HTTP {detail})",
        "err_bot_protection": "сайт блокирует автоматические браузеры (защита от ботов / капча)",
        "err_analysis_refusal": "Claude отказался анализировать эту страницу",
        "err_analysis_truncated": "анализ оборвался",
        "err_analysis_invalid_json": "анализ вернулся в неверном формате",
        "err_analysis_timeout": "анализ занял слишком много времени",
        "err_api_auth": "ключ Anthropic API неверный или без доступа",
        "err_api_rate_limit": "упёрлись в лимит Anthropic API — попробуйте через минуту",
        "err_api_bad_request": "Anthropic API отклонил запрос",
        "err_api_credits": "на аккаунте Anthropic закончились кредиты — пополните в console.anthropic.com → Plans &amp; Billing",
        "err_api_error": "ошибка на стороне Anthropic API — попробуйте позже",
        "err_api_connection": "нет связи с Anthropic API",
        "err_unknown": "что-то пошло не так",
    },
}


def t(lang: str, key: str, **kwargs) -> str:
    table = STRINGS.get(lang, STRINGS["en"])
    text = table.get(key) or STRINGS["en"].get(key) or key
    return text.format(**kwargs) if kwargs else text
