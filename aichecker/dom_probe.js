// Measures AI-design signals in the live DOM. Evaluated by Playwright as
// page.evaluate(PROBE, opts) with the page scrolled to the top.
// Zones: an element belongs to the first screen when its top is above the fold.
(opts) => {
  const started = performance.now();
  const budgetMs = (opts && opts.budgetMs) || 3000;
  const maxTextChars = (opts && opts.maxTextChars) || 9000;
  // The emulated viewport, not innerWidth/innerHeight: on a phone a non-responsive page
  // zooms out and inflates both, which would move the fold.
  const vw = (opts && opts.viewportWidth) || document.documentElement.clientWidth || window.innerWidth;
  const vh = (opts && opts.viewportHeight) || window.innerHeight;
  const scrollY = window.scrollY;
  const doc = document.documentElement;
  const body = document.body || doc;
  const scroller = window.__aicScroller || document.scrollingElement || doc;

  const SKIP = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "META", "LINK", "HEAD", "TITLE",
    "BR", "WBR", "OPTION", "SOURCE", "TRACK", "PARAM"]);
  const MONO = /mono|courier|consolas|menlo|monaco|jetbrains|fira code|source code|space grotesk mono|ibm plex mono|space mono|roboto mono|geist mono|sf mono|ubuntu mono|dm mono|commit mono|berkeley/i;
  const SERIF = /(?<!sans[- ])serif|playfair|instrument serif|fraunces|lora|merriweather|garamond|georgia|times|dm serif|newsreader|cormorant|baskerville|tiempos|gt sectra|caslon|crimson|spectral|young serif|gloock|bodoni|didot|ogg|canela|reckless/i;

  // ── helpers ────────────────────────────────────────────────────────────────
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 1;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  const colorCache = new Map();
  const toRGBA = (str) => {
    if (!str || str === "transparent" || str === "none") return { r: 0, g: 0, b: 0, a: 0 };
    if (colorCache.has(str)) return colorCache.get(str);
    let out = null;
    const m = str.match(/^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)$/);
    if (m) {
      const a = m[4] === undefined ? 1 : m[4].endsWith("%") ? parseFloat(m[4]) / 100 : parseFloat(m[4]);
      out = { r: +m[1], g: +m[2], b: +m[3], a };
    } else if (ctx) {
      // oklch(), lab(), color(display-p3 …) and friends: let the browser convert to sRGB.
      try {
        ctx.clearRect(0, 0, 1, 1);
        ctx.fillStyle = "#000";
        ctx.fillStyle = str;
        ctx.fillRect(0, 0, 1, 1);
        const d = ctx.getImageData(0, 0, 1, 1).data;
        out = { r: d[0], g: d[1], b: d[2], a: d[3] / 255 };
      } catch (e) {
        out = null;
      }
    }
    colorCache.set(str, out);
    return out;
  };
  const COLOR_FN = /(?:rgba?|hsla?|oklch|oklab|lab|lch|hwb|color)\([^()]*\)/g;
  const hsl = ({ r, g, b }) => {
    r /= 255; g /= 255; b /= 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    const l = (max + min) / 2;
    let h = 0, s = 0;
    if (max !== min) {
      const d = max - min;
      s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
      if (max === r) h = (g - b) / d + (g < b ? 6 : 0);
      else if (max === g) h = (b - r) / d + 2;
      else h = (r - g) / d + 4;
      h *= 60;
    }
    return { h, s, l };
  };
  const hex = ({ r, g, b }) => "#" + [r, g, b].map((v) => Math.round(v).toString(16).padStart(2, "0")).join("");
  const radiusPx = (value, w, h) => {
    if (!value) return 0;
    const first = value.split(" ")[0];
    if (first.endsWith("%")) return (parseFloat(first) / 100) * Math.min(w, h);
    return parseFloat(first) || 0;
  };
  const ownText = (el) => {
    let t = "";
    for (const n of el.childNodes) if (n.nodeType === 3) t += n.nodeValue;
    return t.replace(/\s+/g, " ").trim();
  };
  const textOf = (el, max = 120) => {
    const t = (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim();
    return t.length > max ? t.slice(0, max) + "…" : t;
  };
  const isFirst = (top) => top < vh * 0.97;
  const counter = () => ({ total: 0, first_screen: 0, rest: 0 });
  const bump = (c, top) => { c.total++; c[isFirst(top) ? "first_screen" : "rest"]++; };
  const pushEx = (arr, v, n = 6) => { if (v && arr.length < n && !arr.includes(v)) arr.push(v); };
  const visibleBg = (cs) => { const c = toRGBA(cs.backgroundColor); return c && c.a >= 0.06; };
  const hasBorder = (cs) => (parseFloat(cs.borderTopWidth) || 0) >= 1 && cs.borderTopStyle !== "none"
    && (toRGBA(cs.borderTopColor) || { a: 0 }).a >= 0.1;

  // ── collect visible elements ──────────────────────────────────────────────
  const all = body.getElementsByTagName("*");
  const items = [];
  let truncated = false;
  const limit = Math.min(all.length, 9000);
  for (let i = 0; i < limit; i++) {
    const el = all[i];
    if (SKIP.has(el.tagName)) continue;
    if (el instanceof SVGElement && el.tagName.toLowerCase() !== "svg") continue;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;
    const cs = getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden" || parseFloat(cs.opacity) < 0.05) continue;
    items.push({ el, r, cs, top: r.top + scrollY });
    if ((i & 127) === 0 && performance.now() - started > budgetMs) { truncated = true; break; }
  }

  // ── per-element detectors ─────────────────────────────────────────────────
  const gradientText = counter(), gradients = counter(), backdropBlur = counter(), glows = counter(),
    blurBlobs = counter(), pillButtons = counter(), pillBadges = counter(), cards = counter(),
    monoLabels = counter(), numbered = counter(), iconTiles = counter();
  const gradientTextExamples = [], pillExamples = [], monoExamples = [], numberedExamples = [];
  const gradientColors = new Map(), cardRadii = new Map(), cardParents = new Map(), fontUse = new Map();
  const ctaMap = new Map();
  const pillSet = new Set(), ctaSet = new Set();
  let svgIcons = 0, lucide = 0, fontIcons = 0, tailwindish = 0;
  const TW = /^(?:[a-z0-9-]+:)*-?(?:p[trblxy]?|m[trblxy]?|text|bg|rounded|flex|grid|gap|w|h|items|justify|font|leading|tracking|border|shadow|space-[xy]|max-w|min-h)-[\w[\]/.%#-]+$/;

  for (const it of items) {
    const { el, r, cs, top } = it;
    const tag = el.tagName;
    const w = r.width, h = r.height, area = w * h;
    const bg = cs.backgroundImage || "none";

    const cls = typeof el.className === "string" ? el.className : (el.getAttribute("class") || "");
    if (cls && cls.length > 20) {
      let n = 0;
      for (const token of cls.split(/\s+/)) if (TW.test(token) && ++n >= 3) break;
      if (n >= 3) tailwindish++;
    }

    if (bg.includes("gradient(")) {
      const saturated = (bg.match(COLOR_FN) || []).map(toRGBA).filter((c) => {
        if (!c || c.a < 0.2) return false;
        const { s, l } = hsl(c);
        return s >= 0.35 && l >= 0.15 && l <= 0.88;
      });
      const clip = cs.webkitBackgroundClip || cs.backgroundClip;
      if (clip === "text") {
        bump(gradientText, top);
        pushEx(gradientTextExamples, textOf(el, 60), 5);
      } else if (area >= 1600 && saturated.length) {
        bump(gradients, top);
        for (const c of saturated) gradientColors.set(hex(c), (gradientColors.get(hex(c)) || 0) + 1);
      }
    }

    const bdf = cs.backdropFilter || cs.webkitBackdropFilter;
    if (bdf && bdf !== "none" && bdf.includes("blur")) bump(backdropBlur, top);

    if (cs.filter && cs.filter.includes("blur(")) {
      const m = cs.filter.match(/blur\(([\d.]+)px\)/);
      if (m && +m[1] >= 24 && area >= 6400) bump(blurBlobs, top);
    }

    const shadows = [cs.boxShadow, cs.textShadow].filter((s) => s && s !== "none");
    let glow = false;
    for (const value of shadows) {
      for (const part of value.split(/,(?![^(]*\))/)) {
        if (part.includes("inset")) continue;
        const color = (part.match(COLOR_FN) || [])[0];
        const lengths = part.replace(COLOR_FN, "").match(/-?[\d.]+px/g) || [];
        const blurPx = lengths.length >= 3 ? parseFloat(lengths[2]) : 0;
        const c = color && toRGBA(color);
        if (c && c.a >= 0.15 && blurPx >= (value === cs.textShadow ? 8 : 16) && hsl(c).s >= 0.45) { glow = true; break; }
      }
      if (glow) break;
    }
    if (glow) bump(glows, top);

    const buttonish = tag === "BUTTON" || tag === "A" || el.getAttribute("role") === "button"
      || (tag === "INPUT" && /^(submit|button)$/i.test(el.type || ""));
    if (h >= 16 && h <= 80 && w >= h * 1.3 && w <= 560) {
      const boxed = visibleBg(cs) || hasBorder(cs) || bg.includes("gradient(");
      if (boxed) {
        const text = tag === "INPUT" ? (el.value || "").trim() : textOf(el, 80);
        const pill = radiusPx(cs.borderTopLeftRadius, w, h) >= h / 2 - 1.5;
        if (pill && text.length >= 1 && text.length <= 60) {
          if (!pillSet.has(el.parentElement)) {
            if (buttonish) bump(pillButtons, top);
            else { bump(pillBadges, top); pushEx(pillExamples, text); }
          }
          pillSet.add(el);
        }
        if (buttonish && h >= 28 && w >= 56 && text.length >= 2 && text.length <= 40 && !ctaSet.has(el.parentElement)) {
          ctaSet.add(el);
          const key = text.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
          if (key) {
            const entry = ctaMap.get(key) || { text, count: 0, first_screen: 0, rest: 0 };
            entry.count++;
            entry[isFirst(top) ? "first_screen" : "rest"]++;
            ctaMap.set(key, entry);
          }
        }
      }
    }

    if (["DIV", "ARTICLE", "LI", "A", "SECTION", "ASIDE", "FIGURE"].includes(tag) && w >= 140 && h >= 90 && w <= vw * 0.94) {
      const rad = radiusPx(cs.borderTopLeftRadius, w, h);
      if (rad >= 8 && (visibleBg(cs) || hasBorder(cs) || (cs.boxShadow && cs.boxShadow !== "none"))
          && (el.textContent || "").trim().length >= 12) {
        bump(cards, top);
        const rounded = Math.round(rad);
        cardRadii.set(rounded, (cardRadii.get(rounded) || 0) + 1);
        const parent = el.parentElement;
        if (parent) {
          if (!cardParents.has(parent)) cardParents.set(parent, []);
          cardParents.get(parent).push({ w, h, top });
        }
      }
    }

    if (tag.toLowerCase() === "svg" && w >= 10 && w <= 72 && h >= 10 && h <= 72) {
      svgIcons++;
      if (/\blucide\b|\blucide-/.test(cls)) lucide++;
      let p = el.parentElement;
      for (let k = 0; k < 2 && p; k++, p = p.parentElement) {
        const pr = p.getBoundingClientRect();
        if (pr.width >= 26 && pr.width <= 88 && Math.abs(pr.width - pr.height) <= 8) {
          const pcs = getComputedStyle(p);
          if ((visibleBg(pcs) || (pcs.backgroundImage || "").includes("gradient("))
              && radiusPx(pcs.borderTopLeftRadius, pr.width, pr.height) >= 6) { bump(iconTiles, top); break; }
        }
      }
    }
    if ((tag === "I" || tag === "SPAN") && /\b(fa[srlbd]?|fa-[\w-]+|material-icons[\w-]*|material-symbols[\w-]*|bi-[\w-]+|ti-[\w-]+)\b/.test(cls)) fontIcons++;

    const own = ownText(el);
    if (own.length >= 2) {
      const family = (cs.fontFamily.split(",")[0] || "").replace(/["']/g, "").trim();
      fontUse.set(family, (fontUse.get(family) || 0) + own.length);
      if (MONO.test(cs.fontFamily) && own.length <= 48 && !el.closest("pre, code, kbd, samp, textarea")) {
        bump(monoLabels, top);
        pushEx(monoExamples, own.slice(0, 48));
      }
      if (/^[[(]?0\d[\])]?(?:\s*[./·—–:-]\s*(?:0\d)?)?$/.test(own)) {
        bump(numbered, top);
        pushEx(numberedExamples, own);
      }
    }
  }

  // ── headings, eyebrows, italic accents ────────────────────────────────────
  const headingSet = new Set();
  const headings = [];
  for (const it of items) {
    const fsPx = parseFloat(it.cs.fontSize);
    const isTag = /^H[1-3]$/.test(it.el.tagName);
    if (!isTag && !(fsPx >= 34 && ownText(it.el).length >= 3)) continue;
    if (it.r.width < 80) continue;
    let nested = false;
    for (let p = it.el.parentElement, k = 0; p && k < 4; p = p.parentElement, k++) if (headingSet.has(p)) nested = true;
    if (nested) continue;
    headingSet.add(it.el);
    headings.push(it);
  }

  const eyebrows = counter(), eyebrowExamples = [];
  const italicAccents = counter(), italicExamples = [];
  let serifHeadings = 0;
  const prevVisible = (node) => {
    for (let p = node.previousElementSibling; p; p = p.previousElementSibling) {
      const rr = p.getBoundingClientRect();
      if (rr.height > 0 && (p.innerText || "").trim()) return p;
    }
    return null;
  };
  for (const hd of headings) {
    const hfs = parseFloat(hd.cs.fontSize);
    if (SERIF.test(hd.cs.fontFamily)) serifHeadings++;
    let accent = null;
    for (const child of hd.el.querySelectorAll("em, i, span, strong, b, mark")) {
      const ccs = getComputedStyle(child);
      const t = textOf(child, 40);
      if (!t) continue;
      if (ccs.fontStyle === "italic" || (ccs.fontFamily !== hd.cs.fontFamily && SERIF.test(ccs.fontFamily))) { accent = t; break; }
    }
    if (accent) { bump(italicAccents, hd.top); pushEx(italicExamples, accent); }

    let cand = prevVisible(hd.el);
    if (!cand && hd.el.parentElement && hd.el.parentElement !== body) cand = prevVisible(hd.el.parentElement);
    if (!cand) continue;
    const t = textOf(cand, 80);
    if (t.length < 2 || t.length > 60 || t.split(" ").length > 7) continue;
    let inner = cand;
    while (inner.children.length === 1 && textOf(inner.children[0], 80) === t) inner = inner.children[0];
    const ics = getComputedStyle(inner);
    const efs = parseFloat(ics.fontSize);
    if (!(efs <= Math.min(18, hfs * 0.6))) continue;
    const upper = ics.textTransform === "uppercase" || (t === t.toUpperCase() && /\p{L}/u.test(t));
    const spaced = parseFloat(ics.letterSpacing) >= 0.5;
    const boxed = visibleBg(getComputedStyle(cand)) || visibleBg(ics);
    const colored = ics.color !== hd.cs.color;
    if (upper || spaced || boxed || MONO.test(ics.fontFamily) || colored) {
      bump(eyebrows, hd.top);
      pushEx(eyebrowExamples, t, 8);
    }
  }
  const firstScreenHeadings = headings.filter((hd) => isFirst(hd.top));
  const hero = firstScreenHeadings.sort((a, b) => parseFloat(b.cs.fontSize) - parseFloat(a.cs.fontSize))[0];

  // ── sections ──────────────────────────────────────────────────────────────
  let sections = items.filter(({ el, r }) => el.tagName === "SECTION" && r.height >= 120 && r.width >= vw * 0.6).map((it) => it.el);
  sections = sections.filter((s) => !sections.some((o) => o !== s && o.contains(s)));
  if (sections.length < 3) {
    let node = document.querySelector("main") || body;
    for (let depth = 0; depth < 7 && node; depth++) {
      const kids = Array.from(node.children).filter((k) => {
        const rr = k.getBoundingClientRect();
        return rr.height >= 120 && rr.width >= vw * 0.6;
      });
      if (kids.length >= 3) { sections = kids; break; }
      node = kids.length === 1 ? kids[0] : null;
    }
  }
  const sectionTops = sections.map((s) => s.getBoundingClientRect().top + scrollY);

  // ── card grids ────────────────────────────────────────────────────────────
  let uniformGrids = 0, mixedGrids = 0, cardsInGrids = 0;
  for (const list of cardParents.values()) {
    if (list.length < 3) continue;
    const widths = list.map((c) => c.w);
    const ratio = Math.max(...widths) / Math.max(1, Math.min(...widths));
    if (ratio <= 1.2) { uniformGrids++; cardsInGrids += list.length; }
    else if (list.length >= 4 && ratio >= 1.4) mixedGrids++;
  }

  // ── background tone of the first screen ───────────────────────────────────
  const samples = [];
  for (const [fx, fy] of [[0.08, 0.5], [0.5, 0.92], [0.92, 0.3], [0.3, 0.15], [0.7, 0.7]]) {
    const stack = document.elementsFromPoint(vw * fx, vh * fy);
    for (const el of stack) {
      const c = toRGBA(getComputedStyle(el).backgroundColor);
      if (c && c.a >= 0.9) { samples.push(c); break; }
    }
  }
  const bodyBg = toRGBA(getComputedStyle(body).backgroundColor);
  const htmlBg = toRGBA(getComputedStyle(doc).backgroundColor);
  const fallback = bodyBg && bodyBg.a >= 0.9 ? bodyBg : htmlBg && htmlBg.a >= 0.9 ? htmlBg : { r: 255, g: 255, b: 255, a: 1 };
  const bgs = samples.length ? samples : [fallback];
  const bgCounts = new Map();
  for (const c of bgs) bgCounts.set(hex(c), (bgCounts.get(hex(c)) || 0) + 1);
  const dominant = [...bgCounts.entries()].sort((a, b) => b[1] - a[1])[0][0];
  const dom = toRGBA(dominant);
  const tone = hsl(dom);

  // ── images, media, links ──────────────────────────────────────────────────
  let images = 0, largeImages = 0, svgImages = 0, backgroundImages = 0, videos = 0, canvases = 0;
  const imageHosts = new Map();
  let lovableUploads = false;
  for (const { el, r, cs } of items) {
    if (el.tagName === "IMG" && r.width >= 80 && r.height >= 60) {
      images++;
      if (r.width >= 240 && r.height >= 160) largeImages++;
      const src = el.currentSrc || el.src || "";
      if (/\.svg(\?|$)/i.test(src) || src.startsWith("data:image/svg")) svgImages++;
      if (src.includes("/lovable-uploads/")) lovableUploads = true;
      try {
        const host = new URL(src, location.href).hostname;
        if (host && host !== location.hostname) imageHosts.set(host, (imageHosts.get(host) || 0) + 1);
      } catch (e) { /* data: URLs */ }
    } else if ((cs.backgroundImage || "").includes("url(") && r.width * r.height >= 40000) backgroundImages++;
    if (el.tagName === "VIDEO" && r.width * r.height >= 20000) videos++;
    if (el.tagName === "CANVAS" && r.width * r.height >= 40000) canvases++;
  }
  const anchors = Array.from(document.querySelectorAll("a[href]"));
  const hrefs = anchors.map((a) => (a.getAttribute("href") || "").trim());
  const SOCIAL = /(?:^|\.)(instagram\.com|facebook\.com|vk\.com|t\.me|telegram\.me|x\.com|twitter\.com|linkedin\.com|youtube\.com|tiktok\.com|github\.com|dribbble\.com|behance\.net|pinterest\.com|threads\.net|ok\.ru|dzen\.ru|wa\.me|whatsapp\.com|discord\.gg|discord\.com|rutube\.ru)$/i;
  const socials = new Set();
  for (const a of anchors) {
    try {
      const host = new URL(a.href).hostname.replace(/^www\./, "");
      const m = host.match(SOCIAL);
      if (m) socials.add(m[1].toLowerCase());
    } catch (e) { /* ignore */ }
  }
  const maps = !!document.querySelector('iframe[src*="google.com/maps"], iframe[src*="maps.google"], iframe[src*="yandex.ru/map-widget"], iframe[src*="yandex.com/map-widget"], iframe[src*="api-maps.yandex"], iframe[src*="2gis"], iframe[src*="openstreetmap"], [class*="ymaps"], .leaflet-container, .mapboxgl-map, .gm-style');

  // ── text ──────────────────────────────────────────────────────────────────
  const rawText = (body.innerText || "").replace(/[ \t ]+/g, " ").replace(/\n\s*\n+/g, "\n").trim();
  const words = rawText ? rawText.split(/\s+/).length : 0;
  let text = rawText;
  if (text.length > maxTextChars) {
    text = text.slice(0, Math.round(maxTextChars * 0.8)) + "\n…[middle of the page omitted]…\n" + text.slice(-Math.round(maxTextChars * 0.2));
  }
  const emojiList = rawText.match(/\p{Emoji_Presentation}|\p{Extended_Pictographic}️/gu) || [];

  // ── builder / stack fingerprints (reported, never scored) ─────────────────
  const outer = doc.outerHTML;
  const html = outer.length > 1500000 ? outer.slice(0, 1500000) : outer;
  const host = location.hostname;
  const generator = ((document.querySelector('meta[name="generator"]') || {}).content || "").slice(0, 80);
  const has = (re) => re.test(html);
  const aiBuilders = [], siteBuilders = [], stack = [];
  if (/\.lovable\.app$/.test(host) || lovableUploads || has(/data-lov-id|lovable-tagger|gptengineer\.js|cdn\.gpteng\.co|Edit with Lovable/i)) aiBuilders.push("Lovable");
  if (/\.bolt\.host$/.test(host) || has(/bolt\.new|Made (?:with|in) Bolt/i)) aiBuilders.push("Bolt");
  if (has(/\bv0\.(?:dev|app)\b|Built with v0/i) || /\bv0\b/i.test(generator)) aiBuilders.push("v0");
  if (/\.base44\.app$/.test(host) || has(/base44\.(?:com|app)/i)) aiBuilders.push("Base44");
  if (/\.replit\.app$|\.repl\.co$/.test(host) || has(/replit\.com\/badge/i)) aiBuilders.push("Replit");
  if (/\.manus\.space$/.test(host) || has(/manus\.space|manus\.im/i)) aiBuilders.push("Manus");
  if (has(/readdy\.(?:ai|site)/i)) aiBuilders.push("Readdy");
  if (has(/durable\.co\b|ondurable/i)) aiBuilders.push("Durable");
  if (has(/10web\.(?:io|site|me)/i)) aiBuilders.push("10Web");
  if (/\.same\.(?:new|app)$/.test(host) || has(/same\.new/i)) aiBuilders.push("Same");
  if (/\.framer\.(?:website|app|ai|media)$/.test(host) || has(/framerusercontent\.com|data-framer-name/i)) siteBuilders.push("Framer");
  if (has(/data-wf-site|data-wf-page|\.webflow\.io|website-files\.com/i)) siteBuilders.push("Webflow");
  if (has(/wixstatic\.com|static\.parastorage\.com/i)) siteBuilders.push("Wix");
  if (has(/tildacdn\.|data-tilda-|t-records/i)) siteBuilders.push("Tilda");
  if (has(/wp-content\/|wp-includes\//i) || /wordpress/i.test(generator)) siteBuilders.push("WordPress");
  if (has(/static1\.squarespace\.com|squarespace-cdn\.com/i)) siteBuilders.push("Squarespace");
  if (has(/cdn\.shopify\.com|Shopify\.theme/i)) siteBuilders.push("Shopify");
  if (has(/zyrosite\.com|userapp\.zyrosite/i)) siteBuilders.push("Hostinger Builder");
  if (has(/\/_next\/static\//)) stack.push("Next.js");
  if (has(/\/_nuxt\//)) stack.push("Nuxt");
  if (has(/\/assets\/index-[\w-]{6,}\.(?:js|css)/)) stack.push("Vite");
  if (tailwindish >= 30) stack.push("Tailwind CSS");
  if (has(/text-muted-foreground|ring-offset-background|bg-primary\/90|data-slot="(?:button|card|badge)"/)) stack.push("shadcn/ui");
  if (lucide > 0) stack.push("Lucide icons");

  const topEntries = (map, n) => [...map.entries()].sort((a, b) => b[1] - a[1]).slice(0, n);
  const ctas = [...ctaMap.values()].sort((a, b) => b.count - a.count);
  return {
    viewport: { width: vw, height: vh },
    page_height: Math.max(scroller.scrollHeight || 0, doc.scrollHeight, vh),
    title: document.title.slice(0, 200),
    lang: doc.lang || "",
    meta_description: ((document.querySelector('meta[name="description"]') || {}).content || "").slice(0, 300),
    sections: { count: sections.length, below_fold: sectionTops.filter((t) => !isFirst(t)).length },
    hero_headline: hero ? {
      text: textOf(hero.el, 140),
      font_px: Math.round(parseFloat(hero.cs.fontSize)),
      width_share: +(hero.r.width / vw).toFixed(2),
    } : null,
    headings: headings.slice(0, 14).map((hd) => ({
      tag: hd.el.tagName.toLowerCase(),
      text: textOf(hd.el, 90),
      font_px: Math.round(parseFloat(hd.cs.fontSize)),
      zone: isFirst(hd.top) ? "first_screen" : "rest",
    })),
    eyebrows: { ...eyebrows, examples: eyebrowExamples },
    italic_accents_in_headings: { ...italicAccents, examples: italicExamples },
    serif_headings: serifHeadings,
    gradient_text: { ...gradientText, examples: gradientTextExamples },
    color_gradients: { ...gradients, colors: topEntries(gradientColors, 8).map(([c]) => c) },
    backdrop_blur: backdropBlur,
    colored_glows: glows,
    blurred_blobs: blurBlobs,
    pill_buttons: pillButtons,
    pill_badges: { ...pillBadges, examples: pillExamples },
    cards: { ...cards, common_radius_px: topEntries(cardRadii, 2).map(([r]) => r), uniform_grids: uniformGrids, cards_in_uniform_grids: cardsInGrids, mixed_size_grids: mixedGrids },
    ctas: { total: ctas.reduce((s, c) => s + c.count, 0), unique: ctas.length, top: ctas.slice(0, 6) },
    icons: { svg: svgIcons, lucide, font_icons: fontIcons, in_tinted_tiles: iconTiles },
    emoji: { count: emojiList.length, examples: [...new Set(emojiList)].slice(0, 12) },
    mono_labels: { ...monoLabels, examples: monoExamples },
    numbered_labels: { ...numbered, examples: numberedExamples },
    fonts: topEntries(fontUse, 4).map(([f, chars]) => ({ family: f, chars })),
    background: {
      color: dominant,
      lightness: +tone.l.toFixed(2),
      dark: tone.l < 0.25,
      warm_off_white: tone.l >= 0.86 && tone.l < 0.985 && tone.h >= 20 && tone.h <= 65 && tone.s >= 0.2,
    },
    images: { count: images, large: largeImages, svg: svgImages, css_backgrounds: backgroundImages, videos, canvases, hosts: topEntries(imageHosts, 6).map(([h, n]) => ({ host: h, count: n })) },
    links: {
      total: hrefs.length,
      placeholder_hash: hrefs.filter((h) => h === "#" || h === "").length,
      tel: hrefs.filter((h) => h.startsWith("tel:")).length,
      mailto: hrefs.filter((h) => h.startsWith("mailto:")).length,
      social: [...socials].sort(),
      map_embed: maps,
    },
    forms: { forms: document.forms.length, email_inputs: document.querySelectorAll('input[type="email"]').length },
    words,
    text,
    fingerprints: { ai_builders: aiBuilders, site_builders: siteBuilders, stack, generator },
    probe_ms: Math.round(performance.now() - started),
    truncated,
  };
}
