import json
from collections import Counter, defaultdict
from datetime import datetime

from django.db.models import Count
from django.shortcuts import get_object_or_404, render

from companymap.models import Company

from .models import Conference, ConferenceCompany, Session

DEFAULT_DURATION_MINUTES = 45
MIN_BLOCK_MINUTES = 20
AXIS_PADDING_MINUTES = 30
BANNER_THRESHOLD_MINUTES = 300


def home(request):
    conferences = Conference.objects.annotate(
        company_count=Count("companies", distinct=True),
        session_count=Count("sessions", distinct=True),
    )
    return render(request, "conferences/home.html", {"conferences": conferences})


def _minutes(t):
    return t.hour * 60 + t.minute


def _layout_day(sessions_with_times):
    """Greedy interval-column packing (same idea as Google Calendar's day
    view): overlapping sessions get placed side by side, non-overlapping
    ones share the full width. Returns [(session, col_index, col_count)]."""
    items = sorted(sessions_with_times, key=lambda x: x[1])
    clusters = []
    current, current_end = [], None
    for item in items:
        start, end = item[1], item[2]
        if current and start >= current_end:
            clusters.append(current)
            current, current_end = [item], end
        else:
            current.append(item)
            current_end = max(current_end or 0, end)
    if current:
        clusters.append(current)

    result = []
    for cluster in clusters:
        columns = []  # each entry: minute the column is free from
        placed = []
        for item in cluster:
            start, end = item[1], item[2]
            for ci, free_from in enumerate(columns):
                if start >= free_from:
                    columns[ci] = end
                    placed.append((item, ci))
                    break
            else:
                columns.append(end)
                placed.append((item, len(columns) - 1))
        total = len(columns)
        for item, ci in placed:
            result.append((item[0], ci, total))
    return result


def conference_detail(request, slug):
    conference = get_object_or_404(Conference, slug=slug)

    companies = conference.companies.select_related("company").all().order_by("name")
    tag_counts = Counter()
    for company in companies:
        for tag in company.tags:
            tag_counts[tag] += 1
    tag_labels = dict(ConferenceCompany.Tag.choices)
    tag_options = [
        {"value": value, "label": tag_labels.get(value, value), "count": count}
        for value, count in sorted(tag_counts.items(), key=lambda kv: -kv[1])
    ]
    synthego_labels = dict(Company.SynthegoRelation.choices)
    for company in companies:
        company.data_tags = "|".join(company.tags)
        company.tag_badges = [{"value": t, "label": tag_labels.get(t, t)} for t in company.tags]

        info_badges = []
        mapped = company.company
        if mapped:
            if mapped.segment:
                info_badges.append({"kind": "segment", "label": mapped.segment})
            if mapped.synthego_relation and mapped.synthego_relation != Company.SynthegoRelation.NO_RELATION:
                info_badges.append(
                    {"kind": "synthego_" + mapped.synthego_relation, "label": synthego_labels[mapped.synthego_relation]}
                )
            if mapped.has_marketing_presales_team:
                info_badges.append({"kind": "presales", "label": "Marketing/Presales"})
            if mapped.has_data_bi_team:
                info_badges.append({"kind": "data_bi", "label": "Data/BI"})
        company.info_badges = info_badges

    sessions = list(conference.sessions.all().order_by("day", "start_time", "id"))
    for session in sessions:
        session.data = json.dumps(
            {
                "title": session.title,
                "type": session.get_session_type_display(),
                "day": session.day.strftime("%A, %B %-d") if session.day else "",
                "time": _format_time_range(session),
                "location": session.location,
                "company": session.company_name,
                "speakers": session.speakers,
                "description": session.description,
            }
        )

    by_day = defaultdict(list)
    unscheduled_by_day = defaultdict(list)
    banner_by_day = defaultdict(list)
    all_minutes = []
    for session in sessions:
        if not session.day:
            continue
        if not session.start_time:
            unscheduled_by_day[session.day].append(session)
            continue
        start_min = _minutes(session.start_time)
        end_min = _minutes(session.end_time) if session.end_time else start_min + DEFAULT_DURATION_MINUTES
        if end_min <= start_min:
            end_min = start_min + MIN_BLOCK_MINUTES
        # Venue-wide "X open all day" logistics entries (Registration, Exhibit
        # Halls Open, Private Meeting Rooms...) span most of the day and would
        # otherwise force every real session into a narrow sliver via the
        # overlap-column packing below. Show those as a banner row instead,
        # like Google Calendar's all-day events.
        if session.session_type == Session.SessionType.LOGISTICS or (end_min - start_min) >= BANNER_THRESHOLD_MINUTES:
            banner_by_day[session.day].append(session)
            continue
        by_day[session.day].append((session, start_min, end_min))
        all_minutes.extend([start_min, end_min])

    if all_minutes:
        axis_start = max(0, min(all_minutes) - AXIS_PADDING_MINUTES)
        axis_end = min(24 * 60, max(all_minutes) + AXIS_PADDING_MINUTES)
    else:
        axis_start, axis_end = 8 * 60, 18 * 60
    axis_start = (axis_start // 60) * 60
    axis_end = ((axis_end + 59) // 60) * 60
    axis_span = max(axis_end - axis_start, 60)

    hour_marks = []
    hour = axis_start
    while hour <= axis_end:
        hour_marks.append(
            {
                "label": datetime(2000, 1, 1, (hour // 60) % 24, 0).strftime("%-I %p"),
                "top_pct": round((hour - axis_start) / axis_span * 100, 3),
            }
        )
        hour += 60

    days = []
    for day in sorted(by_day.keys() | unscheduled_by_day.keys() | banner_by_day.keys()):
        placed = _layout_day(by_day.get(day, []))
        blocks = []
        for session, ci, total in placed:
            start_min = _minutes(session.start_time)
            end_min = _minutes(session.end_time) if session.end_time else start_min + DEFAULT_DURATION_MINUTES
            if end_min <= start_min:
                end_min = start_min + MIN_BLOCK_MINUTES
            blocks.append(
                {
                    "session": session,
                    "top_pct": round((start_min - axis_start) / axis_span * 100, 3),
                    "height_pct": round((end_min - start_min) / axis_span * 100, 3),
                    "left_pct": round(ci / total * 100, 3),
                    "width_pct": round(100 / total, 3),
                }
            )
        days.append(
            {
                "date": day,
                "blocks": blocks,
                "unscheduled": unscheduled_by_day.get(day, []),
                "banners": banner_by_day.get(day, []),
            }
        )

    return render(
        request,
        "conferences/detail.html",
        {
            "conference": conference,
            "companies": companies,
            "tag_options": tag_options,
            "days": days,
            "hour_marks": hour_marks,
            "total_sessions": len(sessions),
        },
    )


def _format_time_range(session):
    if session.start_time and session.end_time:
        return f"{session.start_time.strftime('%-I:%M %p')} – {session.end_time.strftime('%-I:%M %p')}"
    if session.start_time:
        return session.start_time.strftime("%-I:%M %p")
    return session.raw_time_label or "Time TBD"
