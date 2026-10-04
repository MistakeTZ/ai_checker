"""Telegram HTML for a check result, plus a JSON record of it."""

from __future__ import annotations

from html import escape
from urllib.parse import urlsplit

from .config import Settings
from .features import FIRST_SCREEN, REST, label
from .i18n import t
from .pipeline import DEVICES, CheckResult
from .scoring import Driver, bucket

TELEGRAM_LIMIT = 4096
MIN_TERM = 0.05  # drivers below this weighted logit contribution are noise
ICONS = {"desktop": "🖥", "mobile": "📱"}
# USD per million tokens: input, output, 5-minute cache write, cache read.
PRICES = {
    "claude-opus-5-5": (4.0, 20.0, 5.0, 0.20),
    "claude-opus-5": (5.0, 25.0, 6.25, 0.50),
    "claude-sonnet-5-5": (2.0, 10.0, 2.5, 0.20),
    "claude-haiku-4-5": (1.0, 5.0, 1.25, 0.10),
    "claude-fable-5-1": (10.0, 50.0, 12.5, 0.25),
}


def host_of(url: str) -> str:
    host = urlsplit(url if "://" in url else "https://" + url).hostname or url
    return host.removeprefix("www.")


def bar(score: float) -> str:
    filled = max(0, min(10, round(score / 10)))
    return "▰" * filled + "▱" * (10 - filled)


def error_reason(code: str | None, detail: str, lang: str) -> str:
    return t(lang, f"err_{code or 'unknown'}", detail=escape(detail or "?"))


def render_error(host: str, code: str, detail: str, lang: str) -> str:
    return f"{t(lang, 'error_title', host=escape(host))}\n{error_reason(code, detail, lang)}."


def _fit(text: str) -> str:
    if len(text) <= TELEGRAM_LIMIT:
        return text
    cut = text[: TELEGRAM_LIMIT - 2]
    return cut[: cut.rfind("\n")] + "\n…"


def _driver_line(d: Driver, lang: str) -> str:
    line = f"• <b>{escape(label(d.id, lang))}</b> · {round(d.share * 100)}%"
    if d.kind == "pattern" and d.members:
        line += " — " + escape(" + ".join(label(m, lang) for m in d.members[:3]))
    elif d.evidence:
        line += f" — {escape(d.evidence)}"
    return line


def _primary_summary(result: CheckResult) -> str:
    for device in DEVICES:
        run = result.runs.get(device)
        if run and run.analysis and run.analysis.summary:
            return run.analysis.summary
    return ""


def _page_type(result: CheckResult, lang: str) -> str:
    for device in DEVICES:
        run = result.runs.get(device)
        if run and run.analysis:
            return t(lang, f"page_{run.analysis.page_type}")
    return t(lang, "page_other")


def render_report(result: CheckResult, lang: str, settings: Settings) -> str:
    s = result.score
    fs_pct = round(settings.first_screen_weight * 100)
    lines = [
        f"<b>🤖 {t(lang, 'ai_likeness')}: {round(s.ai)}/100</b> — {t(lang, 'bucket_' + bucket(s.ai))}",
        bar(s.ai),
        f"🧩 {t(lang, 'template_likeness')}: {round(s.template)}/100",
        "",
    ]
    for device in DEVICES:
        name = f"{ICONS[device]} {t(lang, device)}"
        dres = s.devices.get(device)
        if dres is None:
            run = result.runs[device]
            lines.append(t(lang, "device_failed", device=name, reason=error_reason(run.error, run.detail, lang)))
            continue
        line = f"{name} <b>{round(dres.ai)}</b> · {t(lang, 'first_screen')} {round(dres.zones[FIRST_SCREEN].ai)}"
        if REST in dres.zones:
            line += f" · {t(lang, 'below')} {round(dres.zones[REST].ai)}"
        lines.append(line)
    lines.append(f"<i>{t(lang, 'weights_note', fs=fs_pct, rest=100 - fs_pct)}</i>")
    if len(s.devices) == 2:
        gap = s.devices["mobile"].ai - s.devices["desktop"].ai
        if abs(gap) >= 12:
            lines.append(t(lang, "mobile_more" if gap > 0 else "mobile_less"))

    lines += ["", f"<b>{t(lang, 'why_ai' if s.ai >= 40 else 'why_ai_minor')}</b>"]
    ai_drivers = [d for d in s.ai_drivers if d.term >= MIN_TERM][:5]
    lines += [_driver_line(d, lang) for d in ai_drivers] or [t(lang, "no_ai")]

    human_drivers = [d for d in s.human_drivers if d.term >= MIN_TERM][:3]
    if human_drivers:
        effect = t(lang, "human_effect", n=max(1, round(s.human_effect)))
        lines += ["", f"<b>{t(lang, 'why_human')}</b> ({effect})"]
        lines += [_driver_line(d, lang) for d in human_drivers]

    summary = _primary_summary(result)
    if summary:
        lines += ["", f"💬 <i>{escape(summary)}</i>"]
    fp = result.fingerprints
    if fp.get("ai_builders"):
        lines += ["", t(lang, "built_ai", names=escape(", ".join(fp["ai_builders"])))]
    elif fp.get("site_builders"):
        lines += ["", t(lang, "built_site", names=escape(", ".join(fp["site_builders"])))]
    link = f'<a href="{escape(result.final_url, quote=True)}">{escape(host_of(result.final_url))}</a>'
    lines += ["", f"🌐 {link} · {_page_type(result, lang)} · {round(result.elapsed)} {t(lang, 'seconds')}",
              "", t(lang, "rate_prompt")]
    return _fit("\n".join(lines))


def _k(n: int) -> str:
    return f"{n / 1000:.1f}K" if n >= 1000 else str(n)


def estimate_cost(result: CheckResult) -> float | None:
    total = 0.0
    for run in result.runs.values():
        if not run.analysis:
            continue
        prices = PRICES.get(run.analysis.model)
        if prices is None:
            return None
        u = run.analysis.usage
        total += (u["input_tokens"] * prices[0] + u["output_tokens"] * prices[1]
                  + u["cache_creation_input_tokens"] * prices[2] + u["cache_read_input_tokens"] * prices[3]) / 1e6
    return total


def render_details(result: CheckResult, lang: str, settings: Settings) -> str:
    s = result.score
    fs_pct = round(settings.first_screen_weight * 100)
    dw = s.device_weights
    site_mix = " + ".join(f"{round(w * 100)}%·{ICONS[d]}" for d, w in dw.items())
    lines = [
        f"{t(lang, 'details_title')} · {escape(host_of(result.final_url))}",
        "",
        "<code>zone = σ(B + K·Σ w·m·s·p + Σ v·I − Hmax·H) × 100</code>",
        f"<code>device = {fs_pct}%·first + {100 - fs_pct}%·rest; site = {site_mix}</code>",
        "",
    ]
    for device in DEVICES:
        dres = s.devices.get(device)
        if dres is None:
            continue
        blend = " + ".join(f"{dres.zone_weights[z]:.1f}×{round(dres.zones[z].ai)}" for z in dres.zones)
        lines.append(f"{ICONS[device]} <b>{t(lang, device)} {round(dres.ai)}</b> = {blend}")
        for zone, zres in dres.zones.items():
            zone_name = t(lang, "first_screen" if zone == FIRST_SCREEN else "below")
            lines.append(" ▸ " + t(lang, "zone_line", zone=zone_name[:1].upper() + zone_name[1:],
                                   score=round(zres.ai), sig=f"+{zres.signal_sum:.2f}",
                                   pat=f"+{zres.pattern_sum:.2f}", hum=f"{zres.human_sum:.2f}"))
            patterns = sorted(zres.pattern_values.items(), key=lambda kv: -kv[1])
            patterns = [f"{escape(label(pid, lang))} {v:.2f}" for pid, v in patterns if v >= 0.1][:4]
            if patterns:
                lines.append(f"    {t(lang, 'patterns')}: " + ", ".join(patterns))
            signals = sorted(zres.signal_terms.items(), key=lambda kv: -kv[1])[:5]
            if signals:
                lines.append(f"    {t(lang, 'signals')}: "
                             + ", ".join(f"{escape(label(sid, lang))} +{v:.2f}" for sid, v in signals))
        lines.append("")

    lines.append(f"🧩 {t(lang, 'template_likeness')}: "
                 + " · ".join(f"{ICONS[d]} {round(r.template)}" for d, r in s.devices.items()))
    screens = [f"{ICONS[d]} {len(r.capture.screens)} {t(lang, 'of')} {r.capture.total_screens}"
               for d, r in result.runs.items() if r.capture]
    if screens:
        lines.append(t(lang, "screens", items=" · ".join(screens)))
    if result.fingerprints.get("stack"):
        lines.append(t(lang, "stack", stack=escape(", ".join(result.fingerprints["stack"]))))
    usage = result.usage
    if usage:
        cost = estimate_cost(result)
        inp = usage["input_tokens"] + usage["cache_creation_input_tokens"] + usage["cache_read_input_tokens"]
        lines.append(t(lang, "usage", model=escape(", ".join(result.models)), inp=_k(inp),
                       cached=_k(usage["cache_read_input_tokens"]), out=_k(usage["output_tokens"]),
                       cost=f" · ≈ ${cost:.2f}" if cost is not None else ""))
    for device in DEVICES:
        run = result.runs.get(device)
        if run and run.analysis and run.analysis.summary:
            lines.append(f"💬 {ICONS[device]} <i>{escape(run.analysis.summary)}</i>")
    return _fit("\n".join(lines))


def album_caption(result: CheckResult, device: str, lang: str) -> str:
    dres = result.score.devices.get(device)
    score = round(dres.zones[FIRST_SCREEN].ai) if dres else "—"
    return t(lang, "album_caption", device=f"{ICONS[device]} {t(lang, device)}", score=score)


def to_record(result: CheckResult) -> dict:
    """Everything needed to audit a score or refit the weights later (FORMULA.md §18)."""
    s = result.score
    devices = {}
    for device, run in result.runs.items():
        entry: dict = {"error": run.error, "detail": run.detail or None}
        if run.capture:
            entry.update(page_height=run.capture.page_height, screens=len(run.capture.screens),
                         total_screens=run.capture.total_screens, title=run.capture.title,
                         capture_s=round(run.capture.elapsed, 1))
        if run.analysis:
            entry.update(page_type=run.analysis.page_type, summary=run.analysis.summary,
                         model=run.analysis.model, usage=run.analysis.usage,
                         analysis_s=round(run.analysis.elapsed, 1), observations=run.analysis.raw)
        dres = s.devices.get(device)
        if dres:
            entry.update(
                ai_likeness=round(dres.ai, 1), template_likeness=round(dres.template, 1),
                zone_weights=dres.zone_weights,
                zones={z: {"ai_likeness": round(r.ai, 1), "template_likeness": round(r.template, 1),
                           "z_ai": round(r.z_ai, 3), "z_template": round(r.z_template, 3),
                           "signal_terms": {k: round(v, 4) for k, v in r.signal_terms.items()},
                           "patterns": {k: round(v, 3) for k, v in r.pattern_values.items()},
                           "human_evidence": round(r.human_evidence, 3)}
                       for z, r in dres.zones.items()},
            )
        devices[device] = entry
    return {
        "id": result.id,
        "url": result.url,
        "final_url": result.final_url,
        "created_at": result.created_at,
        "lang": result.lang,
        "elapsed_s": round(result.elapsed, 1),
        "ai_likeness": round(s.ai, 1),
        "template_likeness": round(s.template, 1),
        "bucket": bucket(s.ai),
        "device_weights": s.device_weights,
        "human_effect": round(s.human_effect, 1),
        "drivers": [{"id": d.id, "kind": d.kind, "share": round(d.share, 3), "evidence": d.evidence}
                    for d in s.ai_drivers + s.human_drivers if d.term >= MIN_TERM],
        "fingerprints": result.fingerprints,
        "devices": devices,
    }
