"""Rule-based BD-adoption persona classifier, driven entirely by job title text
-- no per-person data is hardcoded here, so it stays safe to keep in source
control and re-run as contact data changes.

Tiers (highest precedence first):
- decision_maker: CxO / Chairman / President / Founder / Global Head -- can
  approve a purchase company-wide, regardless of function.
- champion: VP/SVP (any function), or Director/"Head of" in a BD-adjacent
  function (business development, marketing, sales, commercial, data,
  analytics, alliance/partnership/licensing, corporate development).
- influencer: Associate Director, or a Senior/Sr. Manager, in a BD-adjacent
  function -- mid-management.
- end_user: plain Manager/Associate/Specialist/Coordinator/Representative in
  a BD-adjacent function -- the day-to-day tool user.
- "" (unclassified): anything else, e.g. scientific/technical/QC/regulatory
  roles with no BD-adjacent function, where the persona doesn't apply.
"""

import re

from .models import Person

_CSUITE_RE = re.compile(
    r"chief\s+\w+(\s+\w+)?\s+officer"
    r"|\bce+o\b(?!\s*(office|team|group))"
    r"|\bcfo\b(?!\s*(office|team|group))"
    r"|\bcoo\b(?!\s*(office|team|group))"
    r"|\bcto\b(?!\s*(office|team|group))"
    r"|\bcdo\b(?!\s*(office|team|group))"
    r"|\bcbo\b(?!\s*(office|team|group))"
    r"|\bcmo\b(?!\s*(office|team|group))"
    r"|\bcio\b(?!\s*(office|team|group))"
    r"|\bchro\b(?!\s*(office|team|group))"
    r"|\bchairman\b|\bpresident\b|\bfounder\b"
    r"|global\s+head\s+of|head\s+of\s+global",
    re.IGNORECASE,
)
_VP_RE = re.compile(r"\bsvp\b|\bsr\.?\s*vp\b|\bvp\b|\bvice\s+president\b", re.IGNORECASE)
_ASSOCIATE_DIRECTOR_RE = re.compile(r"\bassociate\s+director\b", re.IGNORECASE)
_DIRECTOR_RE = re.compile(r"\bdirector\b", re.IGNORECASE)
_HEAD_OF_RE = re.compile(r"\bhead\s+of\b", re.IGNORECASE)
_SENIOR_RE = re.compile(r"\bsenior\b|\bsr\.?\b", re.IGNORECASE)
_MANAGER_RE = re.compile(r"\bmanager\b", re.IGNORECASE)
_MANAGER_TIER_RE = re.compile(
    r"\bmanager\b|\bassociate\b|\bspecialist\b|\bcoordinator\b|\brepresentative\b", re.IGNORECASE
)
_FUNCTION_RE = re.compile(
    r"business\s+development|\bbd\b|marketing|\bsales\b|commercial|\bdata\b|analytics"
    r"|alliance|partnership|licensing|corporate\s+development|inside\s+sales|\baccount\b",
    re.IGNORECASE,
)


def classify_title(title):
    """Return a Person.StakeholderRole value (or '') for a free-text job title."""
    if not title:
        return ""

    if _CSUITE_RE.search(title):
        return Person.StakeholderRole.DECISION_MAKER

    has_function = bool(_FUNCTION_RE.search(title))
    has_associate_director = bool(_ASSOCIATE_DIRECTOR_RE.search(title))
    has_bare_director = bool(_DIRECTOR_RE.search(title)) and not has_associate_director
    has_head_of = bool(_HEAD_OF_RE.search(title))

    if _VP_RE.search(title):
        return Person.StakeholderRole.CHAMPION
    if (has_bare_director or has_head_of) and has_function:
        return Person.StakeholderRole.CHAMPION

    is_senior_manager = has_associate_director or (
        bool(_SENIOR_RE.search(title)) and bool(_MANAGER_RE.search(title)) and not has_bare_director
    )
    if is_senior_manager and has_function:
        return Person.StakeholderRole.INFLUENCER

    if bool(_MANAGER_TIER_RE.search(title)) and has_function:
        return Person.StakeholderRole.END_USER

    return ""


def classify_people(people):
    """Classify an iterable of Person objects in place; returns counts by role."""
    counts = {}
    for person in people:
        role = classify_title(person.title)
        person.stakeholder_role = role
        counts[role or "unclassified"] = counts.get(role or "unclassified", 0) + 1
    return counts
