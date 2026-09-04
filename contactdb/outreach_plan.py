"""Builds the data for the Vedant Sept-2026 trip outreach plan page.

Every phase is computed live from the current database (conference
attendance, warm connections, company segments, and each person's own
location where relevant) rather than a frozen snapshot, so the page stays
accurate as data changes.
"""

import re

from companymap.models import Company
from conferences.models import Conference, ConferenceCompany
from contactdb.models import Person

PRIMARY_SEGMENTS = ["CDMO", "CDMO/CRO", "Reagents"]
EQUIPMENT_SEGMENTS = ["Equipment", "Equipment/Reagent", "Instruments"]

SENIOR_RE = re.compile(
    r"\b(vp|vice president|director|chief|ceo|cfo|coo|cco|cto|cmo|president|"
    r"head of|global head|founder|chairman|partner)\b", re.I,
)
MANAGER_RE = re.compile(r"\b(manager|associate|coordinator|specialist|analyst)\b", re.I)

CHANNEL_BY_TIER = {
    "confirmed": "LinkedIn reply/DM referencing their post",
    "warm": "LinkedIn + email to book a slot",
    "senior": "LinkedIn connect, then email 2-3 days later",
    "manager": "Email",
    "other": "Email",
    "equipment": "Skip unless time permits",
}
TIER_LABELS = {
    "confirmed": "Confirmed attending (posted on LinkedIn)",
    "warm": "Warm connections",
    "senior": "Senior (VP / Director / C-suite / Head)",
    "manager": "Manager-level",
    "other": "Other / unlabeled title",
    "equipment": "Equipment companies (deprioritized)",
}
TIER_COLORS = {
    "confirmed": "--s3",
    "warm": "--s1",
    "senior": "--s5",
    "manager": "--s4",
    "other": "--s7",
    "equipment": "--s2",
}
PHASE_COLORS = ["--s1", "--s2", "--s3", "--s4", "--s5"]


def _company_website(company):
    if not company:
        return ""
    if company.url:
        return company.url
    if company.domain:
        return f"https://{company.domain}"
    return ""


def _person_dict(person, company, note_title=None, in_db=True):
    return {
        "id": person.id if in_db else None,
        "name": person.name,
        "title": note_title or person.title,
        "company_name": company.name if company else (person.company_name or ""),
        "company_id": company.id if company else None,
        "website": _company_website(company),
        "has_linkedin": bool(in_db and getattr(person, "linkedin_url", "")),
        "has_email": bool(in_db and getattr(person, "email", "")),
        "in_db": in_db,
    }


def _tier_people(people, company_lookup):
    tiers = {"warm": [], "senior": [], "manager": [], "other": []}
    for p in people:
        company = company_lookup.get(p.company_id)
        d = _person_dict(p, company)
        if p.prior_connections:
            tiers["warm"].append(d)
        elif SENIOR_RE.search(p.title or ""):
            tiers["senior"].append(d)
        elif MANAGER_RE.search(p.title or ""):
            tiers["manager"].append(d)
        else:
            tiers["other"].append(d)
    return tiers


def _confirmed_attendees_from_notes(conference, company_lookup):
    """Parse the 'Name (Title)' lines that classify_conference_xlsx-style
    importers embed in ConferenceCompany.notes from a LinkedIn-post-capture
    sheet, and match each name back to a real Person record where possible."""
    confirmed = []
    seen = set()
    ccs = conference.companies.exclude(notes="").filter(company__isnull=False)
    for cc in ccs:
        for line in cc.notes.split("\n"):
            m = re.match(r"^(.*?) \((.*?)\)$", line.strip())
            if not m:
                continue
            name, title = m.group(1).strip(), m.group(2).strip()
            if not name or name.upper() == "NONE":
                continue
            key = (name.lower(), cc.company_id)
            if key in seen:
                continue
            seen.add(key)
            match = Person.objects.filter(name__iexact=name, company_id=cc.company_id).first()
            company = company_lookup.get(cc.company_id)
            if match:
                confirmed.append(_person_dict(match, company, note_title=title, in_db=True))
            else:
                confirmed.append({
                    "id": None, "name": name, "title": title,
                    "company_name": company.name if company else cc.name,
                    "company_id": company.id if company else None,
                    "website": _company_website(company),
                    "has_linkedin": False, "has_email": False, "in_db": False,
                })
    return confirmed


def _conference_phase(key, title, window, conference_name, company_lookup, include_confirmed=True):
    conference = Conference.objects.get(name=conference_name)
    attending_ids = [c.company_id for c in conference.companies.filter(company__isnull=False)]

    primary_ids = [cid for cid in attending_ids if company_lookup.get(cid) and company_lookup[cid].segment in PRIMARY_SEGMENTS]
    equip_ids = [cid for cid in attending_ids if company_lookup.get(cid) and company_lookup[cid].segment in EQUIPMENT_SEGMENTS]

    primary_people = list(
        Person.objects.filter(company_id__in=primary_ids)
        .only("id", "name", "title", "email", "linkedin_url", "company_id", "company_name", "prior_connections")
    )
    equip_people = list(
        Person.objects.filter(company_id__in=equip_ids)
        .only("id", "name", "title", "email", "linkedin_url", "company_id", "company_name", "prior_connections")
    )

    tiers = _tier_people(primary_people, company_lookup)
    confirmed = _confirmed_attendees_from_notes(conference, company_lookup) if include_confirmed else []
    equipment = [_person_dict(p, company_lookup.get(p.company_id)) for p in equip_people]

    segments = []
    if include_confirmed:
        segments.append(_segment("confirmed", confirmed))
    segments += [
        _segment("warm", tiers["warm"]),
        _segment("senior", tiers["senior"]),
        _segment("manager", tiers["manager"]),
        _segment("other", tiers["other"]),
        _segment("equipment", equipment),
    ]

    return {
        "key": key,
        "title": title,
        "window": window,
        "universe_note": (
            f"{len(primary_ids)} companies / {len(primary_people)} people "
            f"(CDMO + CDMO/CRO + Reagents attending {conference.name})"
        ),
        "segments": segments,
        "total_people": len(primary_people) + len(equipment) + len(confirmed) - sum(
            1 for c in confirmed if c["in_db"] and any(c["id"] == p["id"] for p in tiers["warm"] + tiers["senior"] + tiers["manager"] + tiers["other"])
        ),
    }


def _regional_phase(key, title, window, state_full_name, company_lookup):
    people = list(
        Person.objects.filter(raw_data__State=state_full_name)
        .only("id", "name", "title", "email", "linkedin_url", "company_id", "company_name", "prior_connections")
    )
    primary_people = [p for p in people if p.company_id and company_lookup.get(p.company_id) and company_lookup[p.company_id].segment in PRIMARY_SEGMENTS]
    equip_people = [p for p in people if p.company_id and company_lookup.get(p.company_id) and company_lookup[p.company_id].segment in EQUIPMENT_SEGMENTS]
    other_count = len(people) - len(primary_people) - len(equip_people)

    tiers = _tier_people(primary_people, company_lookup)
    equipment = [_person_dict(p, company_lookup.get(p.company_id)) for p in equip_people]

    segments = [
        _segment("warm", tiers["warm"]),
        _segment("senior", tiers["senior"]),
        _segment("manager", tiers["manager"]),
        _segment("other", tiers["other"]),
        _segment("equipment", equipment),
    ]

    return {
        "key": key,
        "title": title,
        "window": window,
        "universe_note": (
            f"{len(primary_people)} people across "
            f"{len(set(p.company_id for p in primary_people))} companies "
            f"(CDMO + CDMO/CRO + Reagents) personally based in {state_full_name}. "
            f"{len(people)} people total personally in {state_full_name}; "
            f"{other_count} work at companies outside our target universe (pharma/biotech, "
            f"non-pharma, or unmatched) and aren't listed below."
        ),
        "segments": segments,
        "total_people": len(primary_people) + len(equipment),
    }


def _segment(tier_key, people):
    return {
        "key": tier_key,
        "label": TIER_LABELS[tier_key],
        "channel": CHANNEL_BY_TIER[tier_key],
        "color": TIER_COLORS[tier_key],
        "people": sorted(people, key=lambda d: d["company_name"]),
        "count": len(people),
    }


def build_outreach_plan():
    company_lookup = {c.id: c for c in Company.objects.only("id", "name", "segment", "url", "domain")}

    phase1 = _conference_phase(
        "phase1",
        "Phase 1 — ChemOutsourcing Boston (pre-conference outreach)",
        "Sept 4–5 (from Chicago), Sept 10–11 (from New Jersey)",
        "ChemOutsourcing 2026",
        company_lookup,
        include_confirmed=True,
    )
    phase2 = _regional_phase(
        "phase2",
        "Phase 2 — New Jersey (regional visits)",
        "Sept 6–9, physically in NJ",
        "New Jersey",
        company_lookup,
    )
    phase3a = _regional_phase(
        "phase3a",
        "Phase 3a — Boston (regional visits)",
        "Sept 12–13, physically in Boston",
        "Massachusetts",
        company_lookup,
    )
    phase3b = _conference_phase(
        "phase3b",
        "Phase 3b — American Drug Delivery & Formulation Summit",
        "Sept 14–15, conference days in Boston",
        "American Drug Delivery & Formulation Summit 2026",
        company_lookup,
        include_confirmed=False,
    )
    phase4 = _conference_phase(
        "phase4",
        "Phase 4 — Contract Pharma (pre-conference outreach)",
        "Sept 16–18 from Boston/NJ; event itself is Sept 24–25 in New Brunswick, NJ",
        "Contract Pharma 2026",
        company_lookup,
        include_confirmed=True,
    )

    phases = [phase1, phase2, phase3a, phase3b, phase4]
    for phase, color in zip(phases, PHASE_COLORS):
        phase["color"] = color
    return phases
