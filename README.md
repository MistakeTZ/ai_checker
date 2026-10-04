# AI Site Checker — Telegram bot

Send the bot a link; it answers how AI-generated the site **looks** to a visitor, scored 0–100 for the
desktop and the mobile version, with the reasons.

1. **Playwright** opens the page in a desktop (1440×900) and a phone (iPhone 17, 402×681) browser,
   declines the cookie banner, captures the first screen, then scrolls and captures the rest.
   A DOM probe measures what screenshots can't (repeated CTA labels, gradient text, blur, eyebrows,
   pills, icon tiles, fonts, background tone…).
2. **Claude** (`claude-opus-5-5`, vision) acts as the measuring instrument: for 48 AI signals and 12 human
   signals it reports presence / intensity / coverage / typicality, separately for the first screen and
   the rest of the page.
3. **The formula from `FORMULA.md`** (deterministic, in `aichecker/scoring.py`) turns those observations
   into scores. The first screen weighs more than the rest of the page.

```
🤖 AI-likeness: 96/100 — strongly AI-generated
▰▰▰▰▰▰▰▰▰▰
🧩 Template-likeness: 94/100

🖥 Desktop 97 · first screen 96 · below 100
📱 Mobile 94 · first screen 90 · below 100
First screen counts 60%, the rest of the page 40%.

Why it looks AI-made
• Generic LLM copywriting · 15% — Formulaic headline + AI marketing buzzwords + Vague claims
• AI visual system · 12% — Oversized headline + Decorative gradients + Glows and blurred color orbs
• AI hero pattern · 12% — Centered symmetric layout + Formulaic headline + Glows …
• Formulaic headline · 4% — 'Transform your workflow with AI-powered magic'
```

Below the report: an album with both first screens, buttons for **Details** (every term of the formula),
**JSON** (the full record) and a 0–100 **rating** row that collects human judgments for calibration.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium      # on a Linux server: playwright install --with-deps chromium
cp .env.example .env                       # then fill in ANTHROPIC_API_KEY and TELEGRAM_BOT_TOKEN
python bot.py
```

Get the Telegram token from [@BotFather](https://t.me/BotFather) (`/newbot`).

Check a site from the terminal (same pipeline, no Telegram):

```bash
python check.py example.com --lang ru --json result.json --shots shots/
```

Tests (no network or API calls — a local fixture page and a fake Telegram session):

```bash
pip install -r requirements-dev.txt && pytest
```

## How the score works

Every zone (first screen, rest of page) of every render is scored on its own:

```
p   = presence · √(intensity · sat(coverage))          sat(c) = (1 − e^(−3c)) / (1 − e^(−3))
s   = s_min + (s_max − s_min) · typicality
I_j = normalized sigmoid over the members of pattern j
H   = 1 − exp(−Σ h_k · e_k)
z   = B + K · Σ w·m·s·p + Σ v_j·I_j − H_max · H
AI  = 100 · σ(z)
```

```
device score = 0.6 · first screen + 0.4 · rest        (FIRST_SCREEN_WEIGHT)
site score   = 0.5 · desktop + 0.5 · mobile           (DESKTOP_WEIGHT)
```

How `FORMULA.md` maps to the code:

| FORMULA.md | Implementation |
|---|---|
| §1, §13, §15 — signals with presence, specificity, impact, weight | `features.py`: `Signal(specificity, impact, template, weight)` |
| §3, §16, §17 — float presence; presence / intensity / coverage | Claude reports all three per zone; `p = presence·√(intensity·sat(coverage))` |
| §4 — normalize by sections, saturate | coverage is the share of sections; `sat()` is the 1 − e^(−kx) curve |
| §5 — contextual specificity (purple vs lime gradient) | `typicality` moves specificity between `s_min` and `s_max`; patterns still pick up a lime gradient inside an AI system |
| §6, §7, §12 — non-linear interaction patterns | 7 patterns: AI hero, AI section system, SaaS cards, AI visual system, "tasteful" AI default, synthetic social proof, LLM copywriting |
| §8 — 0–100 and the five labels | `σ(z)·100`; `bucket()` |
| §9 — the formula | `scoring.score_zone()` |
| §10, §11 — human signals, non-linear | 12 human signals; `H = 1 − exp(−Σ h·e)`, capped at `H_max`, so one owner photo can't rescue an AI site |
| §18 — two models | AI-likeness (uses AI-specificity) and Template-likeness (uses template relevance) |
| §18 — learn weights from ratings | rating buttons → `data/ratings.jsonl`; observations → `data/results.jsonl` |

The catalog judges every genre against its own stock template, not just SaaS landings: "Hi, I'm {Name} —
Full-Stack Developer" heroes, "Turning ideas into meaningful digital experiences" taglines, tech-stack
chips, starfield backgrounds, AI-chat buttons and the about → skills → projects → contact skeleton of an
AI-built portfolio count just like "Transform your workflow with AI" does on a SaaS page. Content every
site of its genre has (a portfolio owner's photo, email, project cards) is only weak human evidence.

The calibration constants (`B`, `K`, `H_max`, …) live in `scoring.Params`. Two test files pin them:
`tests/test_scoring.py` with synthetic archetypes and FORMULA.md's own examples ("78 → 58 with three human
signals"), and `tests/test_real_observations.py` with real Claude observations of five sites (an
AI-builder portfolio ≥ 75, a textbook AI landing ≥ 85, linear.app ≤ 35, joshwcomeau.com ≤ 25,
paulgraham.com ≤ 20). Retune and you immediately see what breaks.

### Builder fingerprints

The probe also spots AI builders in the page code (Lovable, Bolt, v0, Base44, Replit, Manus, Readdy,
Durable, 10Web, Same) and regular ones (Framer, Webflow, Wix, Tilda, WordPress, …). They are shown in
the report but deliberately **not** scored: the score is about how the design looks, as in FORMULA.md.

## Configuration

All settings live in `.env` (see `.env.example`). Values in `.env` win over variables inherited from the
shell — Claude Code, for one, exports `CLAUDE_EFFORT`, which would otherwise change the bot's effort.

| Variable | Default | |
|---|---|---|
| `CLAUDE_MODEL` | `claude-opus-5-5` | |
| `CLAUDE_EFFORT` | `low` | higher levels think much longer for the same observations; see below |
| `CLAUDE_FALLBACKS` | `true` | server-side retry on another model if a safety classifier declines |
| `FIRST_SCREEN_WEIGHT` | `0.6` | 0.5 = no first-screen preference |
| `DESKTOP_WEIGHT` | `0.5` | |
| `MAX_SCREENS_DESKTOP` / `MAX_SCREENS_MOBILE` | `8` / `12` | the main cost knob; long pages are sampled down to the footer |
| `MOBILE_DEVICE` | `iPhone 17` | any Playwright device descriptor |
| `MAX_CONCURRENT_CHECKS` | `2` | further checks wait in a queue |
| `CHECKS_PER_USER_PER_HOUR` | `10` | `0` = unlimited |
| `ALLOWED_USERS` | empty | comma-separated Telegram user IDs; empty = open to everyone |
| `MAX_CHECKS_PER_DAY` | `0` | checks per user per day (server time, survives restarts); `0` = unlimited |
| `REQUIRED_CHANNEL` | empty | e.g. `@mychannel`: only subscribers can run checks. The bot must be an **admin** of the channel |
| `REQUIRED_CHANNEL_URL` | empty | invite link for a private channel (when `REQUIRED_CHANNEL` is a `-100…` ID) |
| `ALLOW_PRIVATE_URLS` | `false` | only for testing local sites |

## Cost and speed

Both devices per check:

| model, effort | time per check | output tokens | cost per check |
|---|---|---|---|
| `claude-sonnet-5-5`, `low` | 11–59 s | 1–6K | $0.03–0.12 |
| `claude-opus-5-5`, `low` | ~35 s | ~6K | ~$0.18 |
| `claude-opus-5-5`, `max` | ~3.5 min | ~52K | ~$1.15 |

Sonnet: five real sites, from plain to textbook AI. Opus: the textbook AI fixture page, where `low` and
`max` gave the same score (96 vs 97) and the same observations (90%+ of signals in common), so `low` is
the default — higher effort mostly buys deliberation, not different measurements. The system prompt
(~5K tokens) is prompt-cached, so repeat checks read it at a fraction of the price.

## Calibrating the weights

FORMULA.md (§18) recommends learning the weights from people's ratings instead of hand-tuning forever.
Every check is appended to `data/results.jsonl` (all observations and formula terms) and every tap on
the rating row to `data/ratings.jsonl`. Join them on `result_id`/`id`, and with a few hundred ratings
you can fit `weight` per signal and `ai_weight` per pattern (e.g. logistic regression on the zone terms).

## Security

- **SSRF**: links are resolved and private, loopback, link-local and metadata addresses are refused, and
  every request the browser makes (redirects, subresources) passes the same check. Chromium resolves
  DNS itself, so DNS rebinding is not fully covered — don't run the bot next to sensitive internal services.
- **Prompt injection**: page text and screenshots are treated as data; Claude is told to ignore anything
  on the page that addresses it, and structured output limits what it can return.
- **Secrets** come from `.env` (git-ignored) and are kept out of logs and tracebacks.
- Bot-protection pages (Cloudflare, captchas) are reported as such; the checker does not try to bypass them.

## Layout

```
bot.py                 Telegram bot (aiogram 3)
check.py               command-line runner
aichecker/
  features.py          signal / human-signal / pattern catalog with all parameters
  scoring.py           FORMULA.md as code
  capture.py           Playwright: desktop + mobile renders, consent banners, SSRF guard
  dom_probe.js         in-page measurements and builder fingerprints
  analyzer.py          Claude prompt, JSON schema, call
  pipeline.py          capture → analyze → score, per device in parallel
  report.py, i18n.py   Telegram messages (English / Russian)
  urlguard.py          URL parsing and private-network checks
  storage.py           JSONL logs
tests/                 formula calibration, probe on a fixture page, report HTML, bot flow
```
