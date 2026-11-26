"""Rule-based planner: plain-English question -> (tool, args). Used when no LLM
is configured, and as the fallback when the LLM's plan fails validation."""

from __future__ import annotations

import re

_Q = r"[\s?.!]*$"
MEDIA = {"comic": "Comics", "comics": "Comics", "film": "Film", "movie": "Film", "films": "Film", "movies": "Film",
         "tv": "Television", "television": "Television", "animated": "Animation", "animation": "Animation",
         "game": "Games", "games": "Games", "video game": "Games", "video games": "Games", "prose": "Prose",
         "novel": "Prose", "novels": "Prose"}
KINDS = {"dimension": "dimension", "dimensions": "dimension", "realm": "realm", "realms": "realm",
         "temporary": "temporary", "trn": "temporary", "numbered": "numbered", "official": "numbered"}

RULES: list[tuple[re.Pattern, callable]] = []


def rule(pattern):
    def deco(fn):
        RULES.append((re.compile(pattern, re.I), fn))
        return fn
    return deco


def _strip(s: str) -> str:
    return re.sub(r"^(the|a|an)\s+", "", s.strip(" ?.!,\"'"), flags=re.I)


def _team(s: str) -> str:
    s = re.sub(r"\s+(members?|team)$", "", _strip(s), flags=re.I)
    return {"x-man": "X-Men", "avenger": "Avengers", "defender": "Defenders"}.get(s.lower().rstrip("s"), s)


@rule(r"^(?:who|which characters?)\s+(?:has|have|had)?\s*(?:ever\s+)?(?:fought|battled|faced|opposed)\s+both\s+(.+?)\s+and\s+(.+?)" + _Q)
def _fought_both(m):
    return "fought_both", {"a": _strip(m.group(1)), "b": _strip(m.group(2))}


@rule(r"^which\s+(.+?)\s+(?:have|has)\s+(?:also\s+)?been\s+(?:an?\s+|members?\s+of\s+(?:the\s+)?)?(.+?)" + _Q)
def _overlap(m):
    return "team_overlap", {"team_a": _team(m.group(1)), "team_b": _team(m.group(2))}


@rule(r"^(?:who|which characters?)\s+(?:has|have)\s+been\s+(?:in|members? of)\s+both\s+(?:the\s+)?(.+?)\s+and\s+(?:the\s+)?(.+?)" + _Q)
def _overlap2(m):
    return "team_overlap", {"team_a": _team(m.group(1)), "team_b": _team(m.group(2))}


@rule(r"^(?:show|list|give|find)?\s*(?:me\s+)?(?:every|all|the)?\s*variants?\s+of\s+(.+?)" + _Q)
def _variants(m):
    return "variants", {"name": _strip(m.group(1))}


@rule(r"^when\s+did\s+(.+?)\s+(?:first\s+appear|debut|make\s+(?:their|his|her|its)\s+(?:first\s+appearance|debut))" + _Q)
def _first(m):
    return "first_appearance", {"name": _strip(m.group(1))}


@rule(r"^(?:what\s+(?:is|was)\s+)?(?:the\s+)?first\s+appearance\s+of\s+(.+?)" + _Q)
def _first2(m):
    return "first_appearance", {"name": _strip(m.group(1))}


@rule(r"^how\s+many\s+(?:(\w+(?:\s+game)?)\s+)?(realities|universes|dimensions|realms|entries)(?:\s+(?:are\s+there|exist))?(?:\s+in\s+(\w+))?" + _Q)
def _count(m):
    word = (m.group(1) or "").lower()
    args = {}
    if word in MEDIA:
        args["medium"] = MEDIA[word]
    if word in KINDS:
        args["kind"] = KINDS[word]
    if m.group(2).lower() in ("dimensions", "realms"):
        args["kind"] = KINDS[m.group(2).lower()]
    return "count_realities", args


@rule(r"^how\s+many\s+(\w+)\s+(?:realities|universes)" + _Q)
def _count2(m):
    w = m.group(1).lower()
    return "count_realities", {"medium": MEDIA[w]} if w in MEDIA else {"kind": KINDS.get(w)} if w in KINDS else {}


@rule(r"^(?:who\s+(?:are|were|is)\s+)?(?:the\s+)?(current\s+|former\s+)?members\s+of\s+(.+?)" + _Q)
def _members(m):
    status = (m.group(1) or "").strip() or "all"
    return "team_members", {"team": _team(m.group(2)), "status": status}


@rule(r"^who\s+(?:is|are|were|was)\s+(.+?)'s\s+(parents?|father|mother|children|sons?|daughters?|siblings?|brothers?|sisters?|spouses?|wife|husband|relatives?|family|clones?)" + _Q)
def _relatives(m):
    rel = m.group(2).lower()
    return "relatives", {"name": _strip(m.group(1)), "relation": None if rel == "family" else rel}


@rule(r"^who\s+(?:created|made|invented)\s+(.+?)" + _Q)
def _creators(m):
    return "creators_of", {"name": _strip(m.group(1))}


@rule(r"^(?:what|which)\s+characters?\s+(?:did|has|have)\s+(.+?)\s+(?:create|co-create)d?" + _Q)
def _created(m):
    return "created_by", {"creator": _strip(m.group(1))}


@rule(r"^(?:which\s+)?characters?\s+created\s+by\s+(.+?)" + _Q)
def _created2(m):
    return "created_by", {"creator": _strip(m.group(1))}


@rule(r"^who\s+(?:has|have)\s+(.+?)\s+(?:fought|battled|faced)(?:\s+the\s+most)?" + _Q)
def _opp(m):
    return "opponents", {"name": _strip(m.group(1))}


@rule(r"^(?:(?:who|what)\s+(?:are|were|is|was)\s+)?(.+?)'s\s+(?:biggest\s+|main\s+|most\s+frequent\s+|top\s+|greatest\s+)?"
      r"(?:enemies|enemy|foes|rivals|rival|opponents|villains|arch-?enemy|arch-?nemesis|nemesis)" + _Q)
def _opp2(m):
    return "opponents", {"name": _strip(m.group(1))}


@rule(r"^(?:who\s+(?:are|were)\s+)?(?:the\s+)?(?:biggest\s+|main\s+|greatest\s+)?(?:enemies|foes|rivals|villains|opponents)\s+of\s+(.+?)" + _Q)
def _opp3(m):
    return "opponents", {"name": _strip(m.group(1))}


_MEDIUM_WORDS = r"(films?|movies?|tv|television|animation|animated\s+\w+|cartoons?|games?|video\s+games?|comics?|novels?|prose)"


def _medium_of(word: str) -> str | None:
    full = " ".join(word.lower().split())
    w = full.split()[0]
    return MEDIA.get(full) or MEDIA.get(full.rstrip("s")) or MEDIA.get(w) or MEDIA.get(w.rstrip("s")) or {"cartoon": "Animation", "cartoons": "Animation"}.get(w)


@rule(r"^(?:who|which\s+villains?|which\s+characters?)\s+(?:has|have|did)\s+(.+?)\s+(?:fought|fight|battled|faced)\s+in\s+(?:the\s+)?" + _MEDIUM_WORDS + _Q)
def _opp_medium(m):
    return "opponents", {"name": _strip(m.group(1)), "medium": _medium_of(m.group(2))}


@rule(r"^(?:who\s+(?:are|were)\s+)?(.+?)'s\s+(?:biggest\s+|main\s+|closest\s+|best\s+)?(?:allies|ally|friends|friend|teammates|partners|sidekicks?)" + _Q)
def _allies(m):
    return "allies", {"name": _strip(m.group(1))}


@rule(r"^(?:who\s+(?:are|were)\s+)?(?:the\s+)?(?:closest\s+)?(?:allies|friends|teammates|partners)\s+of\s+(.+?)" + _Q)
def _allies2(m):
    return "allies", {"name": _strip(m.group(1))}


@rule(r"^who\s+(?:has|have|does|did)\s+(.+?)\s+(?:teamed\s+up\s+with|team\s+up\s+with|fought\s+alongside|fight\s+alongside|worked\s+with|work\s+with)(?:\s+the\s+most)?" + _Q)
def _allies3(m):
    return "allies", {"name": _strip(m.group(1))}


@rule(r"^when\s+did\s+(.+?)\s+first\s+(?:fight|battle|face|clash\s+with|oppose)\s+(.+?)" + _Q)
def _first_fight(m):
    return "first_fight", {"a": _strip(m.group(1)), "b": _strip(m.group(2))}


@rule(r"^(?:what\s+(?:was|is)\s+)?(?:the\s+)?first\s+(?:fight|battle|clash)\s+between\s+(.+?)\s+and\s+(.+?)" + _Q)
def _first_fight2(m):
    return "first_fight", {"a": _strip(m.group(1)), "b": _strip(m.group(2))}


@rule(r"^(?:how\s+(?:many\s+times|often)\s+(?:has|have|did)\s+(.+?)\s+(?:fought|fight|battled|battle|faced|face)|"
      r"(?:has|have|did)\s+(.+?)\s+(?:ever\s+)?(?:fought|fight|battled|battle|faced|face))\s+(?!both\b)(.+?)" + _Q)
def _fight_count(m):
    return "first_fight", {"a": _strip(m.group(1) or m.group(2)), "b": _strip(m.group(3))}


@rule(r"^(?:how\s+(?:are|is|were|was)\s+(.+?)\s+and\s+(.+?)\s+(?:related|connected|linked)|"
      r"what\s+(?:is|was|'s)\s+the\s+(?:relationship|connection|link|history|rivalry)\s+between\s+(.+?)\s+and\s+(.+?))" + _Q)
def _relationship(m):
    a, b = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
    return "relationship", {"a": _strip(a), "b": _strip(b)}


@rule(r"^(?:are|were|is|was)\s+(.+?)\s+and\s+(.+?)\s+(?:enemies|allies|friends|rivals|related|family|teammates|"
      r"brothers|sisters|siblings|married|partners|connected)" + _Q)
def _relationship2(m):
    return "relationship", {"a": _strip(m.group(1)), "b": _strip(m.group(2))}


@rule(r"^(.+?)\s+(?:vs\.?|versus)\s+(.+?)" + _Q)
def _relationship3(m):
    return "relationship", {"a": _strip(m.group(1)), "b": _strip(m.group(2))}


@rule(r"^(?:who\s+killed|who\s+murdered|how\s+did\s+(?=.+\s+die\b))\s*(.+?)(?:\s+die)?" + _Q)
def _killed(m):
    return "death_of", {"name": _strip(m.group(1))}


@rule(r"^(?:who|which\s+characters?)\s+(?:has|have|did)\s+(.+?)\s+(?:killed|kill|murdered|murder)" + _Q)
def _kills(m):
    return "kills", {"name": _strip(m.group(1))}


@rule(r"^(?:who\s+(?:appears?|appeared|is|was|are|were)\s+in|who\s+(?:is|was)\s+featured\s+in|(?:what\s+is\s+)?(?:the\s+)?cast\s+of|"
      r"(?:list\s+)?(?:the\s+)?characters\s+in)\s+(.+?)" + _Q)
def _cast(m):
    return "who_appears", {"work": _strip(m.group(1))}


@rule(r"^(?:who\s+(?:are|were|is|was)\s+)?(?:the\s+)?(villains?|antagonists?|heroes)\s+(?:in|of)\s+(.+?)" + _Q)
def _cast_role(m):
    return "who_appears", {"work": _strip(m.group(2)), "role": m.group(1).lower()}


@rule(r"^(?:what\s+(?:is|was)\s+|tell\s+me\s+(?:about\s+)?|explain\s+)?(?:the\s+)?origin(?:\s+story)?\s+of\s+(.+?)" + _Q)
def _origin(m):
    return "origin", {"name": _strip(m.group(1))}


@rule(r"^(?:what\s+(?:is|was|are|were)\s+)?(.+?)'s\s+(?:origin(?:\s+story)?|backstory|powers|abilities)" + _Q)
def _origin2(m):
    return "origin", {"name": _strip(m.group(1))}


@rule(r"^(?:how\s+did\s+(.+?)\s+(?:get|gain|acquire|obtain)\s+(?:his|her|their|its)\s+powers|"
      r"how\s+(?:was|were|did)\s+(.+?)\s+(?:created|born|originate|become\s+.+)|"
      r"where\s+(?:is|was|does|did)\s+(.+?)\s+(?:from|born|come\s+from)|"
      r"what\s+(?:powers|abilities)\s+(?:does|did)\s+(.+?)\s+have)" + _Q)
def _origin3(m):
    return "origin", {"name": _strip(next(g for g in m.groups() if g))}


@rule(r"^who\s+(?:fought|was|were)\s+(?:on\s+each\s+side\s+)?in\s+(.+?)" + _Q)
def _event(m):
    return "event_sides", {"event": _strip(m.group(1))}


@rule(r"^(?:tell\s+me\s+about|what\s+is|what's|describe|who\s+is|who\s+are)\s+(.+?)" + _Q)
def _about(m):
    target = _strip(m.group(1))
    if re.match(r"^(earth|moira|jubilee)-", target, re.I):
        return "reality_info", {"reality": target}
    if len(target.split()) > 6 or re.search(r"\b(of|in|for|from)\b|'s\s", target, re.I):
        return None  # "what is the box office of X" is not a request for an entity summary
    return "entity_info", {"name": target}


def plan(question: str) -> tuple[str, dict] | None:
    q = re.sub(r"\s+", " ", question.strip())
    for pat, fn in RULES:
        m = pat.match(q)
        if m:
            out = fn(m)
            if out:
                return out
    return None
