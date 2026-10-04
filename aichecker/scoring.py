"""FORMULA.md implemented as a deterministic scoring engine.

Per zone (first screen / rest of page) of each device render:

    p   = presence · √(intensity · sat(coverage))                        §4, §17
    s   = s_min + (s_max − s_min) · typicality                           §5
    I_j = normalized sigmoid over the members of pattern j               §6–7
    H   = 1 − exp(−Σ h_k · e_k)                                          §11
    z   = B + K · Σ wᵢ·mᵢ·sᵢ·pᵢ + Σ vⱼ·Iⱼ − H_max · H                      §9
    AI  = 100 · σ(z)                                                     §8

The template-likeness model (§18, "two models") is the same expression with
each signal's ``template`` relevance in place of AI-specificity.

Zone scores are blended with the first screen weighted higher (default 60/40),
then desktop and mobile are blended (default 50/50).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .features import (
    FIRST_SCREEN,
    HUMAN_SIGNALS,
    PATTERNS,
    REST,
    SIGNALS,
    Pattern,
)


@dataclass(frozen=True)
class Params:
    ai_bias: float = -1.6  # B — a page with no evidence lands at ~17 ("very human")
    ai_scale: float = 0.55  # K
    ai_human_cap: float = 1.4  # H_max — human evidence can remove at most this much logit
    template_bias: float = -1.3
    template_scale: float = 1.0
    template_human_cap: float = 1.0
    coverage_k: float = 3.0  # steepness of the coverage saturation curve


PARAMS = Params()


@dataclass(frozen=True)
class Obs:
    """One observed signal in one zone, as measured by the analyzer."""

    presence: float = 0.0
    intensity: float = 0.0
    coverage: float = 0.0
    typicality: float = 1.0
    evidence: str = ""


@dataclass
class ZoneObs:
    signals: dict[str, Obs] = field(default_factory=dict)
    human: dict[str, Obs] = field(default_factory=dict)


@dataclass
class DeviceObs:
    zones: dict[str, ZoneObs]  # FIRST_SCREEN is required, REST is optional


@dataclass
class ZoneResult:
    ai: float
    template: float
    z_ai: float
    z_template: float
    signal_terms: dict[str, float]  # K · w·m·s·p per signal (AI model)
    pattern_values: dict[str, float]  # I_j
    pattern_terms: dict[str, float]  # v_j · I_j
    human_terms: dict[str, float]  # share of the human reduction per signal (logits)
    human_evidence: float  # H
    evidence: dict[str, str]
    pattern_members: dict[str, list[str]]  # strongest members, for explanations

    @property
    def signal_sum(self) -> float:
        return sum(self.signal_terms.values())

    @property
    def pattern_sum(self) -> float:
        return sum(self.pattern_terms.values())

    @property
    def human_sum(self) -> float:
        return sum(self.human_terms.values())


@dataclass
class DeviceResult:
    ai: float
    template: float
    zones: dict[str, ZoneResult]
    zone_weights: dict[str, float]


@dataclass(frozen=True)
class Driver:
    id: str
    kind: str  # "signal" | "pattern" | "human"
    share: float  # share of all AI (or all human) evidence, 0..1
    term: float  # weighted logit contribution, used to drop negligible items
    evidence: str
    members: tuple[str, ...] = ()


@dataclass
class SiteResult:
    ai: float
    template: float
    devices: dict[str, DeviceResult]
    device_weights: dict[str, float]
    ai_drivers: list[Driver]
    human_drivers: list[Driver]
    human_effect: float  # points the human evidence removes from the AI score


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    if x != x:  # NaN
        return lo
    return max(lo, min(hi, x))


def saturate(coverage: float, k: float = PARAMS.coverage_k) -> float:
    """Concave 0→0, 1→1 curve: the first occurrences count most (§4)."""
    return (1.0 - math.exp(-k * coverage)) / (1.0 - math.exp(-k))


def effective_presence(o: Obs, k: float = PARAMS.coverage_k) -> float:
    """§17: presence scaled by how strong and how widespread the signal is."""
    if o.presence <= 0:
        return 0.0
    return clamp(o.presence) * math.sqrt(clamp(o.intensity) * saturate(clamp(o.coverage), k))


def pattern_value(pattern: Pattern, p: dict[str, float]) -> float:
    """§7: sigmoid(Σ wᵢxᵢ + bias), rescaled so that no members → 0 and all members → 1."""
    total = sum(w for _, w in pattern.members)
    x = sum(w * max(p.get(i, 0.0) for i in ids) for ids, w in pattern.members) / total
    k, t = pattern.steepness, pattern.threshold
    lo, hi = sigmoid(-k * t), sigmoid(k * (1.0 - t))
    return clamp((sigmoid(k * (x - t)) - lo) / (hi - lo))


def score_zone(zone: str, obs: ZoneObs, params: Params = PARAMS,
               exclude: frozenset[str] = frozenset()) -> ZoneResult:
    p: dict[str, float] = {}
    signal_terms: dict[str, float] = {}
    evidence: dict[str, str] = {}
    e_ai = e_tpl = 0.0
    for sig in SIGNALS:
        o = obs.signals.get(sig.id)
        if o is None or sig.id in exclude:
            continue
        pi = effective_presence(o, params.coverage_k)
        if pi <= 0:
            continue
        lo, hi = sig.specificity
        spec = lo + (hi - lo) * clamp(o.typicality)
        p[sig.id] = pi
        signal_terms[sig.id] = params.ai_scale * sig.weight * sig.impact * spec * pi
        e_ai += sig.weight * sig.impact * spec * pi
        e_tpl += sig.weight * sig.impact * sig.template * pi
        evidence[sig.id] = o.evidence

    pattern_values: dict[str, float] = {}
    pattern_terms: dict[str, float] = {}
    pattern_members: dict[str, list[str]] = {}
    tpl_patterns = 0.0
    for pat in PATTERNS:
        if zone not in pat.zones or pat.id in exclude:
            continue
        value = pattern_value(pat, p)
        if value <= 0:
            continue
        pattern_values[pat.id] = value
        pattern_terms[pat.id] = pat.ai_weight * value
        tpl_patterns += pat.template_weight * value
        strongest = sorted(
            ((max(ids, key=lambda i: p.get(i, 0.0)), max(p.get(i, 0.0) for i in ids))
             for ids, _ in pat.members),
            key=lambda item: -item[1],
        )
        pattern_members[pat.id] = [sid for sid, v in strongest if v > 0.25][:4]

    # §11: independent human signals add up with diminishing returns.
    raw_human: dict[str, float] = {}
    for hs in HUMAN_SIGNALS:
        o = obs.human.get(hs.id)
        if o is None or hs.id in exclude:
            continue
        e = effective_presence(o, params.coverage_k)
        if e > 0:
            raw_human[hs.id] = hs.strength * e
            evidence[hs.id] = o.evidence
    total_human = sum(raw_human.values())
    h = 1.0 - math.exp(-total_human)
    ai_reduction = params.ai_human_cap * h
    human_terms = {k: ai_reduction * v / total_human for k, v in raw_human.items()} if total_human else {}

    z_ai = params.ai_bias + params.ai_scale * e_ai + sum(pattern_terms.values()) - ai_reduction
    z_tpl = (params.template_bias + params.template_scale * e_tpl + tpl_patterns
             - params.template_human_cap * h)
    return ZoneResult(
        ai=100.0 * sigmoid(z_ai),
        template=100.0 * sigmoid(z_tpl),
        z_ai=z_ai,
        z_template=z_tpl,
        signal_terms=signal_terms,
        pattern_values=pattern_values,
        pattern_terms=pattern_terms,
        human_terms=human_terms,
        human_evidence=h,
        evidence=evidence,
        pattern_members=pattern_members,
    )


def _weights(present: list[str], preferred: str, preferred_weight: float) -> dict[str, float]:
    if len(present) == 1:
        return {present[0]: 1.0}
    return {k: (preferred_weight if k == preferred else 1.0 - preferred_weight) for k in present}


def score_device(obs: DeviceObs, first_screen_weight: float = 0.6, params: Params = PARAMS,
                 exclude: frozenset[str] = frozenset()) -> DeviceResult:
    if FIRST_SCREEN not in obs.zones:
        raise ValueError("a device render needs at least the first screen")
    zones = {z: score_zone(z, zo, params, exclude) for z, zo in obs.zones.items()
             if z in (FIRST_SCREEN, REST)}
    weights = _weights(list(zones), FIRST_SCREEN, first_screen_weight)
    return DeviceResult(
        ai=sum(weights[z] * r.ai for z, r in zones.items()),
        template=sum(weights[z] * r.template for z, r in zones.items()),
        zones=zones,
        zone_weights=weights,
    )


def _blend(devices: dict[str, DeviceObs], first_screen_weight: float, desktop_weight: float,
           params: Params, exclude: frozenset[str]) -> tuple[dict[str, DeviceResult], dict[str, float]]:
    results = {d: score_device(o, first_screen_weight, params, exclude) for d, o in devices.items()}
    return results, _weights(list(results), "desktop", desktop_weight)


def score_site(devices: dict[str, DeviceObs], first_screen_weight: float = 0.6,
               desktop_weight: float = 0.5, params: Params = PARAMS) -> SiteResult:
    if not devices:
        raise ValueError("no device renders to score")
    results, dev_w = _blend(devices, first_screen_weight, desktop_weight, params, frozenset())
    ai = sum(dev_w[d] * r.ai for d, r in results.items())
    template = sum(dev_w[d] * r.template for d, r in results.items())

    # Explanations: each item's share of the weighted evidence. Shares stay
    # meaningful even when the sigmoid is saturated, unlike point deltas.
    totals: dict[tuple[str, str], float] = {}
    best: dict[tuple[str, str], tuple[float, str, tuple[str, ...]]] = {}

    def add(kind: str, item: str, value: float, evidence: str, members: tuple[str, ...] = ()) -> None:
        key = (kind, item)
        totals[key] = totals.get(key, 0.0) + value
        if value > best.get(key, (-1.0, "", ()))[0]:
            best[key] = (value, evidence, members)

    for d, dres in results.items():
        for z, zres in dres.zones.items():
            w = dev_w[d] * dres.zone_weights[z]
            for sid, term in zres.signal_terms.items():
                add("signal", sid, w * term, zres.evidence.get(sid, ""))
            for pid, term in zres.pattern_terms.items():
                add("pattern", pid, w * term, "", tuple(zres.pattern_members.get(pid, ())))
            for hid, term in zres.human_terms.items():
                add("human", hid, w * term, zres.evidence.get(hid, ""))

    def drivers(kinds: tuple[str, ...]) -> list[Driver]:
        items = [(k, v) for k, v in totals.items() if k[0] in kinds and v > 0]
        total = sum(v for _, v in items)
        out = [Driver(id=item, kind=kind, share=v / total, term=v, evidence=best[(kind, item)][1],
                      members=best[(kind, item)][2])
               for (kind, item), v in items]
        return sorted(out, key=lambda drv: -drv.share)

    human_ids = frozenset(h.id for h in HUMAN_SIGNALS)
    no_human, _ = _blend(devices, first_screen_weight, desktop_weight, params, human_ids)
    ai_without_human = sum(dev_w[d] * r.ai for d, r in no_human.items())

    return SiteResult(
        ai=ai,
        template=template,
        devices=results,
        device_weights=dev_w,
        ai_drivers=drivers(("signal", "pattern")),
        human_drivers=drivers(("human",)),
        human_effect=ai_without_human - ai,
    )


BUCKETS = ((20, "very_human"), (40, "mostly_human"), (60, "mixed"), (80, "ai_like"),
           (101, "strongly_ai"))


def bucket(score: float) -> str:
    """§8: 0–20 very human … 80–100 strongly AI-generated."""
    for upper, key in BUCKETS:
        if score < upper:
            return key
    return BUCKETS[-1][1]
