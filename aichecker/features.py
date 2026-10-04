"""Signal catalog for the AI-likeness model described in FORMULA.md.

Three kinds of evidence:

* ``Signal``      – atomic AI / template signals (FORMULA.md §3, §13, §15).
* ``HumanSignal`` – evidence of a real business or deliberate craft (§10–11).
* ``Pattern``     – compound "interaction" features built from signals (§6–7, §12).

Claude only *measures* signals (presence / intensity / coverage / typicality);
every number below is applied by ``scoring.py``. ``weight`` is the knob meant to
be refit from human ratings later (§18); everything starts at 1.0.
"""

from __future__ import annotations

from dataclasses import dataclass

VISUAL = "visual"
STRUCTURE = "structure"
CONTENT = "content"

FIRST_SCREEN = "first_screen"
REST = "rest"
ZONES = (FIRST_SCREEN, REST)


@dataclass(frozen=True)
class Signal:
    id: str
    group: str
    en: str
    ru: str
    look_for: str
    # AI-specificity of an unusual take vs. the textbook AI version (§5):
    # s = s_min + (s_max - s_min) * typicality.
    specificity: tuple[float, float]
    impact: float  # how strongly a visitor registers it (§1)
    template: float  # how much it says "generic template" regardless of AI (§18)
    weight: float = 1.0


@dataclass(frozen=True)
class HumanSignal:
    id: str
    en: str
    ru: str
    look_for: str
    strength: float  # h_k in §9 / §11


@dataclass(frozen=True)
class Pattern:
    id: str
    en: str
    ru: str
    zones: tuple[str, ...]
    # (any-of signal ids, weight) – the strongest of the alternatives counts.
    members: tuple[tuple[tuple[str, ...], float], ...]
    threshold: float  # weighted share of members at which the pattern is half "on"
    ai_weight: float  # v_j
    template_weight: float  # u_j
    steepness: float = 8.0


def _s(id, group, en, ru, look_for, spec, impact, template, weight=1.0) -> Signal:
    return Signal(id, group, en, ru, look_for, spec, impact, template, weight)


SIGNALS: tuple[Signal, ...] = (
    # ── Visual style ────────────────────────────────────────────────────────
    _s("gradient_usage", VISUAL, "Decorative gradients", "Декоративные градиенты",
       "Color gradients on backgrounds, buttons, cards, borders or icons. Textbook AI: "
       "purple→blue, indigo→violet, pink→orange, cyan→purple. Lime→teal, muted duotones "
       "or clearly brand-specific gradients are low typicality.",
       (0.10, 0.70), 0.60, 0.30),
    _s("gradient_text", VISUAL, "Gradient text", "Градиентный текст",
       "Headline words filled with a gradient (background-clip: text). Textbook AI: a key "
       "phrase of the hero headline in a purple/blue gradient.",
       (0.25, 0.60), 0.55, 0.30),
    _s("glow_effects", VISUAL, "Glows and blurred color orbs", "Свечение и размытые цветные пятна",
       "Neon halos, colored glow shadows, glowing rings around a portrait or button, blurred "
       "gradient orbs/blobs, aurora or mesh backgrounds, spotlight beams. Textbook AI: "
       "violet/blue blurred blobs behind the hero.",
       (0.30, 0.75), 0.60, 0.30),
    _s("glassmorphism", VISUAL, "Glassmorphism", "Глассморфизм",
       "Frosted translucent panels with backdrop blur and thin light borders (cards, "
       "navbars, badges).",
       (0.30, 0.60), 0.50, 0.35),
    _s("dark_neon_theme", VISUAL, "Dark theme with neon accents", "Тёмная тема с неоновыми акцентами",
       "Near-black or deep-navy page with saturated neon accents and glowing highlights "
       "(the 'dev-tool dark mode' look).",
       (0.20, 0.55), 0.50, 0.40),
    _s("warm_editorial_palette", VISUAL, "Warm 'editorial' palette", "Тёплая «журнальная» палитра",
       "Cream/off-white/beige paper-like background with muted warm accents (terracotta, "
       "olive, burnt orange) and a calm 'editorial minimal' feel — a current default of AI "
       "design generators.",
       (0.15, 0.55), 0.45, 0.35),
    _s("serif_italic_accent", VISUAL, "Italic serif accent words", "Курсивные акцентные слова",
       "Display headlines where one word or phrase is set in an italic (often serif) face "
       "for emphasis, e.g. 'Design that *feels* human'.",
       (0.30, 0.70), 0.55, 0.30),
    _s("mono_labels", VISUAL, "Monospace labels", "Моноширинные подписи",
       "Small monospace labels, eyebrows or metadata ('// FEATURES', '[01] PROCESS', "
       "'v2.0 — NOW LIVE') used as decoration outside of code.",
       (0.35, 0.65), 0.40, 0.35),
    _s("numbered_sections", VISUAL, "Numbered section labels", "Нумерация секций 01/02/03",
       "'01 / 02 / 03' numbering of sections, steps or features used as a decorative device.",
       (0.30, 0.65), 0.45, 0.50),
    _s("grid_dot_background", VISUAL, "Grid, dot, starfield or grain backgrounds",
       "Фоны с сеткой, точками, звёздами или зерном",
       "Faint grid lines, dot matrices, starfields, particles or constellation lines, or noise "
       "grain behind content, often faded out with a radial mask.",
       (0.30, 0.60), 0.35, 0.35),
    _s("pill_badge", VISUAL, "Pill announcement badge", "Бейдж-«таблетка» с анонсом",
       "Small pill-shaped chips such as '✨ New: …', 'Introducing v2 →', 'Now in beta', "
       "'Backed by Y Combinator', typically above the headline.",
       (0.40, 0.75), 0.55, 0.45),
    _s("pill_buttons", VISUAL, "Pill-shaped buttons", "Кнопки-«таблетки»",
       "Fully rounded pill-shaped buttons and CTAs.",
       (0.15, 0.40), 0.35, 0.40),
    _s("rounded_cards", VISUAL, "Uniform rounded cards", "Одинаковые скруглённые карточки",
       "Content boxed into cards with the same 12–24px radius and a soft shadow or 1px "
       "border everywhere.",
       (0.20, 0.45), 0.40, 0.60),
    _s("bento_grid", VISUAL, "Bento grid", "Бенто-сетка",
       "A bento-box grid of feature tiles of mixed sizes, each with a mini illustration or "
       "UI fragment.",
       (0.30, 0.60), 0.50, 0.50),
    _s("icon_tiles", VISUAL, "Icons in tinted tiles", "Иконки в цветных плашках",
       "Generic line icons (Lucide/Heroicons style) inside tinted rounded squares or circles, "
       "one atop every feature card.",
       (0.45, 0.80), 0.55, 0.65),
    _s("sparkle_ai_icons", VISUAL, "Sparkles and 'AI' iconography", "Искорки ✨ и «AI»-иконки",
       "✨ sparkles, magic wands, stars, brains, robots or 'AI' glyphs used as decoration, or "
       "a floating AI-assistant / chatbot button with a robot or sparkle icon.",
       (0.45, 0.80), 0.55, 0.25),
    _s("emoji_icons", VISUAL, "Emoji used as icons", "Эмодзи вместо иконок",
       "Emojis (🚀 ⚡ 🎯 ✅) used as feature icons, bullets or heading decorations.",
       (0.45, 0.75), 0.50, 0.45),
    _s("ai_imagery", VISUAL, "AI-generated imagery", "Сгенерированные нейросетью изображения",
       "Photos or illustrations that look AI-generated: glossy plastic skin, malformed "
       "hands/text/objects, impossible details, over-smoothed lighting, the 'Midjourney look'. "
       "Real product screenshots and genuine photos are NOT this.",
       (0.70, 0.95), 0.90, 0.20),
    _s("abstract_3d", VISUAL, "Abstract 3D renders", "Абстрактный 3D",
       "Glossy spheres, chrome blobs, floating low-poly rocks, wireframe spheres, geometric "
       "shapes or isometric 3D illustrations with no specific meaning.",
       (0.30, 0.65), 0.50, 0.35),
    _s("fake_ui_mockup", VISUAL, "Fake dashboard mockups", "Фейковые макеты дашбордов",
       "Product UI/dashboard mockups with placeholder charts, made-up metrics or floating "
       "stat cards that don't show a real product.",
       (0.40, 0.75), 0.60, 0.45),
    _s("stock_imagery", VISUAL, "Generic stock photos", "Типовые стоковые фото",
       "Stock photos unrelated to the specific business: smiling team at a laptop, handshake, "
       "skyline.",
       (0.10, 0.30), 0.40, 0.70),
    _s("default_typography", VISUAL, "Default UI typography", "Шрифт «по умолчанию»",
       "One default UI sans (Inter, Geist, system-ui, Poppins, Plus Jakarta Sans, DM Sans) "
       "everywhere and no typographic personality. Typicality = how default the choice is.",
       (0.10, 0.45), 0.35, 0.55),
    _s("oversized_headline", VISUAL, "Oversized headline", "Огромный заголовок",
       "A very large, bold, tightly leaded display headline that dominates the screen.",
       (0.10, 0.30), 0.40, 0.45),
    _s("centered_symmetry", VISUAL, "Centered symmetric layout", "Всё по центру и симметрично",
       "Centered hero and section headers, evenly spaced equal columns, mirror symmetry "
       "everywhere.",
       (0.15, 0.40), 0.35, 0.55),
    _s("motion_gimmicks", VISUAL, "Shimmer, beams and marquees", "Шиммер, «лучи» и бегущие строки",
       "Shimmer or animated gradient borders, light beams, spotlight cards, infinite logo or "
       "testimonial marquees (in still frames: gradient borders, beam lines, cropped marquee "
       "rows).",
       (0.30, 0.60), 0.40, 0.30),
    _s("floating_nav", VISUAL, "Floating pill navbar", "Плавающее меню-«таблетка»",
       "A floating, rounded, often blurred navigation bar detached from the top edge.",
       (0.30, 0.55), 0.35, 0.40),
    # ── Structure ───────────────────────────────────────────────────────────
    _s("eyebrow", STRUCTURE, "Eyebrow labels", "Надзаголовки (eyebrow)",
       "A small uppercase, colored or letter-spaced label above a heading ('FEATURES', "
       "'WHY US').",
       (0.35, 0.55), 0.35, 0.50),
    _s("eyebrow_heading_formula", STRUCTURE, "Repeated eyebrow + heading formula",
       "Повторяющаяся формула «надзаголовок + заголовок»",
       "Nearly every section opens with the same stack: eyebrow or short accent underline bar "
       "→ big heading → grey subheading → content.",
       (0.80, 0.92), 0.90, 0.85),
    _s("uniform_section_rhythm", STRUCTURE, "Uniform section rhythm", "Однообразный ритм секций",
       "Sections share one template — same spacing, alignment and structure — stacked like "
       "interchangeable blocks.",
       (0.50, 0.75), 0.60, 0.90),
    _s("stock_section_sequence", STRUCTURE, "Stock section sequence of the genre",
       "Типовой набор секций жанра",
       "The page is its genre's default section list with nothing of its own: SaaS (features → "
       "how it works → testimonials → pricing → FAQ → CTA); portfolio (about → skills grid → "
       "experience timeline → project cards with 'Live demo' / 'GitHub' buttons → contact form); "
       "agency (services → process → work → testimonials → contact); restaurant or shop (about "
       "→ highlights → reviews → booking).",
       (0.40, 0.70), 0.60, 0.90),
    _s("identical_card_grids", STRUCTURE, "Identical card grids", "Сетки одинаковых карточек",
       "Grids of identical cards: 3, 4 or 6 columns of icon + title + two-line text.",
       (0.40, 0.70), 0.55, 0.85),
    _s("skill_chips", STRUCTURE, "Tech / skill chips", "Плашки технологий и навыков",
       "Rows of small chips or tiles naming technologies, skills or features, each with a tiny "
       "icon (Next.js · TypeScript · Node.js), 'Tech stack' strips, skill grids with logos or "
       "progress bars.",
       (0.30, 0.65), 0.50, 0.70),
    _s("repeated_cta", STRUCTURE, "Repeated identical CTA", "Одинаковые повторяющиеся CTA",
       "The same call-to-action label repeated across the page ('Get started' ×5). Use the "
       "DOM CTA counts.",
       (0.55, 0.75), 0.75, 0.60),
    _s("dual_cta", STRUCTURE, "Primary + ghost CTA pair", "Пара кнопок «основная + призрачная»",
       "A primary button next to an outlined/ghost secondary one ('Get started' / 'Learn "
       "more', 'Start free' / 'Book a demo').",
       (0.20, 0.45), 0.35, 0.60),
    _s("stats_strip", STRUCTURE, "Round-number stats strip", "Полоса «круглых» цифр",
       "A row of round-number stats ('10K+ users · 99.9% uptime · 24/7 support · 4.9★') "
       "without sources.",
       (0.40, 0.70), 0.50, 0.65),
    _s("logo_cloud", STRUCTURE, "'Trusted by' logo cloud", "Блок логотипов «Нам доверяют»",
       "A strip of client/partner logos. Textbook AI: generic or fake grayscale wordmarks "
       "(Acme, Globex) or famous logos with no evidence of a relationship.",
       (0.15, 0.85), 0.45, 0.55),
    _s("generic_testimonials", STRUCTURE, "Generic testimonials", "Безликие отзывы",
       "Testimonials with generic praise and unverifiable identity: first name + job title, "
       "initials avatars, five stars, no company, date or source.",
       (0.50, 0.85), 0.65, 0.60),
    _s("pricing_tiers", STRUCTURE, "Three-tier pricing", "Три тарифа с «Популярным»",
       "Three pricing cards with a highlighted 'Most popular' middle plan and checkmark lists.",
       (0.20, 0.45), 0.35, 0.75),
    _s("how_it_works", STRUCTURE, "'How it works' steps", "Блок «Как это работает»",
       "A 3–4 step sequence (1 → 2 → 3) with icons and one-line explanations.",
       (0.30, 0.55), 0.40, 0.70),
    _s("faq_accordion", STRUCTURE, "Generic FAQ accordion", "Типовой FAQ-аккордеон",
       "An accordion of obvious questions ('Is there a free trial?', 'Can I cancel anytime?').",
       (0.15, 0.40), 0.25, 0.60),
    _s("closing_cta_banner", STRUCTURE, "Closing CTA banner", "Финальный CTA-баннер",
       "A full-width closing banner ('Ready to transform your workflow?'), often on a gradient.",
       (0.35, 0.60), 0.45, 0.70),
    _s("boilerplate_footer", STRUCTURE, "Boilerplate footer", "Шаблонный футер",
       "Generic footer columns (Product / Company / Resources / Legal), '© 2025 Company. All "
       "rights reserved.', 'Built with ❤️', placeholder social icons, newsletter field.",
       (0.20, 0.45), 0.25, 0.75),
    # ── Content ─────────────────────────────────────────────────────────────
    _s("ai_buzzwords", CONTENT, "AI marketing buzzwords", "AI-канцелярит и баззворды",
       "seamless, unlock, elevate, empower, supercharge, revolutionize, effortless, "
       "cutting-edge, next-generation, harness, 'in seconds', 'all-in-one'; portfolio clichés: "
       "passionate, pixel-perfect, scalable, elegant solutions, 'bring your vision to life' "
       "(RU: бесшовный, раскройте потенциал, революционный, инновационный, «на новый уровень», "
       "«в один клик», «воплощаю идеи в жизнь»).",
       (0.50, 0.85), 0.70, 0.50),
    _s("headline_formula", CONTENT, "Formulaic headline or tagline", "Шаблонный заголовок или слоган",
       "The genre's stock opening line. SaaS: 'Transform your X with Y', 'X, reimagined', 'The "
       "future of X is here', 'Build faster. Ship smarter.'; portfolio: 'Hi, I'm {Name} — "
       "Full-Stack Developer', 'Turning ideas into meaningful digital experiences', 'Crafting "
       "digital experiences that…'; business: 'Where {X} meets {Y}', 'Your trusted partner in…'. "
       "A textbook match is presence 1 and typicality 1.",
       (0.55, 0.85), 0.70, 0.55),
    _s("vague_claims", CONTENT, "Vague interchangeable claims", "Размытые взаимозаменяемые обещания",
       "Claims that fit any product or person: 'Boost productivity', 'Save time', 'Built for "
       "teams', 'Secure by design', value chips like 'Clean Code · Performance · Scalability' — "
       "with no specifics.",
       (0.45, 0.70), 0.55, 0.75),
    _s("triplet_rhythm", CONTENT, "Rule-of-three rhythm", "Ритм «трёх слов»",
       "Staccato triplets ('Fast. Secure. Scalable.'), 'Not just X — it's Y', em-dash-heavy, "
       "overly balanced phrasing.",
       (0.55, 0.85), 0.55, 0.40),
    _s("placeholder_leftovers", CONTENT, "Placeholder leftovers", "Остатки заглушек",
       "Lorem ipsum, 'Your Company', john@example.com, (555) numbers, 'Feature One', dummy "
       "items, broken template text.",
       (0.45, 0.80), 0.80, 0.85),
    _s("hype_claims", CONTENT, "Hype claims", "Хайповые обещания",
       "'AI-powered' on everything, '10x faster', 'the world's first', '#1 platform' and "
       "similar unbacked superlatives. Typicality is low when AI genuinely is the product.",
       (0.30, 0.60), 0.45, 0.40),
)

HUMAN_SIGNALS: tuple[HumanSignal, ...] = (
    HumanSignal("real_photography", "Real photography", "Настоящие фотографии",
                "Authentic photos of the actual business, products, work, people or places in "
                "context — natural imperfections, consistent real setting. Not stock, not AI. A "
                "single cut-out portrait of a portfolio's owner is weak (presence ≤ 0.3).", 0.65),
    HumanSignal("named_team", "Named real people", "Реальные люди с именами",
                "Several named people with genuine photos and specific bios. A portfolio "
                "owner's own name and photo don't count.", 0.40),
    HumanSignal("local_specifics", "Local specifics", "Локальная конкретика",
                "For a place-based business: street address with a map, opening hours, "
                "directions, neighborhood references. A city name alone is weak.", 0.45),
    HumanSignal("legal_details", "Legal and company details", "Юридические реквизиты",
                "Company registration or tax IDs (INN/OGRN, VAT), legal entity name, registered "
                "address. Plain email / phone / city are weak (presence ≤ 0.3): every template "
                "has a contact block.", 0.30),
    HumanSignal("concrete_offer", "Concrete offer details", "Конкретика предложения",
                "Real prices, SKUs, specs, menus, schedules, delivery terms — operational detail "
                "a template wouldn't have. A CV job entry is not this.", 0.35),
    HumanSignal("verifiable_reviews", "Verifiable reviews", "Проверяемые отзывы",
                "Reviews with full names, photos, dates or sources (Google/Yandex/Trustpilot "
                "widgets), or details that ring true.", 0.45),
    HumanSignal("case_studies", "Specific cases and portfolio", "Конкретные кейсы и портфолио",
                "Write-ups with named clients, concrete numbers, process artifacts, before/after "
                "work. Project cards with a stack list and 'Live demo' / 'GitHub' buttons are the "
                "template default — weak.", 0.40),
    HumanSignal("distinct_voice", "Distinct voice and insider language", "Свой голос и профессиональный язык",
                "Domain jargon, idiosyncratic tone, opinions, humor, specific product or process "
                "names a generator wouldn't invent.", 0.45),
    HumanSignal("custom_layout", "Custom, irregular layout", "Нестандартная вёрстка",
                "Art-directed or editorial layout that breaks template patterns: asymmetry, custom "
                "grids, unusual navigation, deliberate 'mess'.", 0.60),
    HumanSignal("handmade_visuals", "Handmade or original visuals", "Авторская графика",
                "Custom illustrations, hand-drawn elements, handwriting, original brand artwork, "
                "real product renders or real UI screenshots of the product being sold. Project "
                "thumbnails in a portfolio grid are weak.", 0.50),
    HumanSignal("brand_identity", "Distinctive brand identity", "Узнаваемый фирменный стиль",
                "A coherent, distinctive system: custom logo or wordmark, unusual palette, "
                "characterful type pairing applied consistently.", 0.50),
    HumanSignal("living_content", "Signs of a living business", "Признаки живого бизнеса",
                "Dated news or blog posts, events, changelogs, social feeds, awards with years, "
                "history ('since 1998').", 0.40),
)

PATTERNS: tuple[Pattern, ...] = (
    Pattern(
        "ai_hero", "AI hero pattern", "AI-паттерн первого экрана", (FIRST_SCREEN,),
        (
            (("eyebrow", "pill_badge", "mono_labels", "skill_chips"), 1.3),
            (("oversized_headline",), 0.8),
            (("headline_formula", "ai_buzzwords", "vague_claims"), 1.6),
            (("dual_cta", "pill_buttons"), 1.1),
            (("centered_symmetry",), 0.5),
            (("gradient_usage", "glow_effects", "grid_dot_background", "gradient_text",
              "serif_italic_accent", "dark_neon_theme"), 1.2),
            (("fake_ui_mockup", "abstract_3d", "ai_imagery", "sparkle_ai_icons"), 0.8),
        ),
        threshold=0.40, ai_weight=1.4, template_weight=0.9,
    ),
    Pattern(
        "ai_section_system", "AI section system", "AI-система секций", (REST,),
        (
            (("eyebrow_heading_formula", "eyebrow"), 1.6),
            (("uniform_section_rhythm",), 1.3),
            (("identical_card_grids", "bento_grid"), 1.2),
            (("repeated_cta",), 1.0),
            (("closing_cta_banner",), 0.8),
            (("how_it_works", "numbered_sections"), 0.7),
            (("icon_tiles", "skill_chips"), 0.9),
            (("stock_section_sequence",), 1.2),
        ),
        threshold=0.42, ai_weight=1.3, template_weight=1.4,
    ),
    Pattern(
        "saas_card_system", "SaaS card system", "SaaS-система карточек", ZONES,
        (
            (("rounded_cards",), 1.0),
            (("icon_tiles",), 1.3),
            (("identical_card_grids",), 1.1),
            (("bento_grid",), 0.8),
            (("glassmorphism",), 0.6),
            (("fake_ui_mockup", "skill_chips"), 0.6),
        ),
        threshold=0.40, ai_weight=0.7, template_weight=1.1,
    ),
    Pattern(
        "ai_visual_system", "AI visual system", "AI-визуальная система", ZONES,
        (
            (("gradient_usage",), 1.2),
            (("glow_effects",), 1.2),
            (("gradient_text",), 0.8),
            (("glassmorphism",), 0.8),
            (("dark_neon_theme",), 0.7),
            (("sparkle_ai_icons",), 0.9),
            (("grid_dot_background",), 0.6),
            (("abstract_3d", "ai_imagery"), 0.8),
            (("pill_badge", "pill_buttons"), 0.7),
            (("oversized_headline",), 0.4),
        ),
        threshold=0.38, ai_weight=1.1, template_weight=0.4,
    ),
    Pattern(
        "editorial_ai_system", "'Tasteful' AI default", "«Вкусный» AI-шаблон", ZONES,
        (
            (("warm_editorial_palette",), 1.2),
            (("serif_italic_accent",), 1.3),
            (("mono_labels",), 1.0),
            (("numbered_sections",), 1.0),
            (("pill_buttons",), 0.6),
            (("grid_dot_background",), 0.4),
            (("eyebrow",), 0.5),
        ),
        threshold=0.40, ai_weight=1.0, template_weight=0.5,
    ),
    Pattern(
        "synthetic_social_proof", "Synthetic social proof", "Синтетическое социальное доказательство", ZONES,
        (
            (("generic_testimonials",), 1.4),
            (("stats_strip",), 1.0),
            (("logo_cloud",), 0.9),
            (("hype_claims",), 0.5),
            (("placeholder_leftovers",), 0.6),
        ),
        threshold=0.38, ai_weight=0.9, template_weight=1.0,
    ),
    Pattern(
        "generic_copy_voice", "Generic LLM copywriting", "Типичный LLM-копирайтинг", ZONES,
        (
            (("ai_buzzwords",), 1.3),
            (("headline_formula",), 1.1),
            (("vague_claims",), 1.0),
            (("triplet_rhythm",), 1.1),
            (("hype_claims",), 0.5),
        ),
        threshold=0.38, ai_weight=1.2, template_weight=0.9,
    ),
)

SIGNAL_BY_ID = {s.id: s for s in SIGNALS}
HUMAN_BY_ID = {h.id: h for h in HUMAN_SIGNALS}
PATTERN_BY_ID = {p.id: p for p in PATTERNS}


def label(item_id: str, lang: str) -> str:
    """Localized display name for any signal, human signal or pattern id."""
    item = SIGNAL_BY_ID.get(item_id) or HUMAN_BY_ID.get(item_id) or PATTERN_BY_ID.get(item_id)
    if item is None:
        return item_id
    return item.ru if lang == "ru" else item.en


def _validate() -> None:
    ids = [s.id for s in SIGNALS] + [h.id for h in HUMAN_SIGNALS] + [p.id for p in PATTERNS]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ValueError(f"duplicate catalog ids: {sorted(duplicates)}")
    for s in SIGNALS:
        lo, hi = s.specificity
        if not (0 <= lo <= hi <= 1 and 0 <= s.impact <= 1 and 0 <= s.template <= 1):
            raise ValueError(f"bad parameters for signal {s.id}")
    for p in PATTERNS:
        for alternatives, _ in p.members:
            unknown = [i for i in alternatives if i not in SIGNAL_BY_ID]
            if unknown:
                raise ValueError(f"pattern {p.id} references unknown signals {unknown}")


_validate()
