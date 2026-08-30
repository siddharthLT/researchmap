import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone as dt_timezone
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from companymap.models import Company, CompanyLinkedInPost

RSSHUB_BASE_URL = getattr(settings, "RSSHUB_BASE_URL", "http://127.0.0.1:1201")
POSTS_PER_COMPANY = 10
REQUEST_DELAY_SECONDS = 2


def clean_text(value):
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(value))
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_linkedin_company_id(linkedin_url):
    if not linkedin_url:
        return None
    parsed = urlparse(linkedin_url)
    path = parsed.path.strip("/")
    # company/lonza or company/123456
    match = re.search(r"(?:^|/)company/([^/]+)", path)
    if not match:
        return None
    # LinkedIn slugs are alphanumeric/hyphen only (trailing hyphens can be
    # legitimate, e.g. "cellecta-inc-"), but a trailing "." is always a typo
    # baked into the stored URL (e.g. "...inc." from a copy-pasted sentence).
    return match.group(1).strip().rstrip(".")


def parse_date(value):
    if not value:
        return None
    value = str(value).strip()
    try:
        parsed = parsedate_to_datetime(value)
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed
    except Exception:
        pass
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed
    except Exception:
        return None


def parse_date_from_activity_id(post_url):
    """RSSHub's LinkedIn route doesn't reliably populate pubDate, but every
    post URL embeds a LinkedIn "activity" Snowflake ID whose top 41 bits are
    a millisecond Unix timestamp (no custom epoch offset, unlike Twitter's
    Snowflake). Verified against a handful of posts that *did* have a real
    pubDate: this decoding lands within about an hour of the true time."""
    # Two URL shapes show up: ".../posts/xyz-activity-1234-abc" and
    # ".../feed/update/urn:li:activity:1234" — handle both separators.
    match = re.search(r"activity[:-](\d+)", post_url or "")
    if not match:
        return None
    try:
        activity_id = int(match.group(1))
        ts_ms = activity_id >> 22
        return datetime.fromtimestamp(ts_ms / 1000, tz=dt_timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def fetch_xml(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 EmailCounter-RSSHub-Importer"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read()


def get_child_text(element, child_name):
    child = element.find(child_name)
    if child is not None and child.text:
        return child.text
    return ""


def parse_rss_items(xml_bytes):
    root = ET.fromstring(xml_bytes)
    items = []

    for item in root.findall(".//item"):
        title = get_child_text(item, "title")
        link = get_child_text(item, "link")
        description = get_child_text(item, "description")
        pub_date = get_child_text(item, "pubDate")
        items.append({
            "title": clean_text(title),
            "link": link.strip(),
            "text": clean_text(description or title),
            "published_at": parse_date(pub_date),
            "raw": {"title": title, "link": link, "description": description, "pubDate": pub_date},
        })

    atom_ns = "{http://www.w3.org/2005/Atom}"
    for entry in root.findall(f".//{atom_ns}entry"):
        title = get_child_text(entry, f"{atom_ns}title")
        summary = get_child_text(entry, f"{atom_ns}summary")
        content = get_child_text(entry, f"{atom_ns}content")
        published = get_child_text(entry, f"{atom_ns}published") or get_child_text(entry, f"{atom_ns}updated")
        link = ""
        link_el = entry.find(f"{atom_ns}link")
        if link_el is not None:
            link = link_el.attrib.get("href", "")
        items.append({
            "title": clean_text(title),
            "link": link.strip(),
            "text": clean_text(content or summary or title),
            "published_at": parse_date(published),
            "raw": {"title": title, "link": link, "summary": summary, "content": content, "published": published},
        })

    deduped = []
    seen_links = set()
    for item in items:
        link = item.get("link")
        if not link or link in seen_links:
            continue
        seen_links.add(link)
        deduped.append(item)
    return deduped[:POSTS_PER_COMPANY]


def import_company_posts(company):
    linkedin_company_id = parse_linkedin_company_id(company.linkedin_url)
    if not linkedin_company_id:
        return 0, "No LinkedIn company ID"

    feed_url = f"{RSSHUB_BASE_URL}/linkedin/company/{linkedin_company_id}/posts"

    try:
        xml_bytes = fetch_xml(feed_url)
        posts = parse_rss_items(xml_bytes)
    except Exception as error:
        return 0, f"Fetch failed: {error}"

    saved_count = 0
    for post in posts:
        post_url = post.get("link")
        if not post_url:
            continue
        post_date = post.get("published_at") or parse_date_from_activity_id(post_url)
        CompanyLinkedInPost.objects.update_or_create(
            post_url=post_url,
            defaults={
                "company": company,
                "linkedin_company_id": linkedin_company_id,
                "post_text": post.get("text") or "",
                "post_date": post_date,
                "raw_payload": post.get("raw") or {},
            },
        )
        saved_count += 1

    ids_to_keep = list(
        CompanyLinkedInPost.objects
        .filter(company=company)
        .order_by("-post_date", "-created_at")
        .values_list("id", flat=True)[:POSTS_PER_COMPANY]
    )
    CompanyLinkedInPost.objects.filter(company=company).exclude(id__in=ids_to_keep).delete()

    return saved_count, "OK"


class Command(BaseCommand):
    help = "Pull LinkedIn company-page posts via a local RSSHub instance and store them in CompanyLinkedInPost."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit", type=int, default=None,
            help="Only process the first N companies (for a quick test run).",
        )
        parser.add_argument(
            "--company-id", type=int, default=None,
            help="Only process a single Company by id.",
        )

    def handle(self, *args, **options):
        companies = Company.objects.exclude(linkedin_url="").order_by("id")

        if options["company_id"]:
            companies = companies.filter(id=options["company_id"])
        if options["limit"]:
            companies = companies[: options["limit"]]

        companies = list(companies)
        total_companies = len(companies)
        self.stdout.write(f"Found {total_companies} companies with a LinkedIn URL")

        total_posts = 0
        for index, company in enumerate(companies, start=1):
            saved_count, status = import_company_posts(company)
            total_posts += saved_count
            self.stdout.write(f"[{index}/{total_companies}] {company.name}: {saved_count} posts - {status}")
            if index < total_companies:
                time.sleep(REQUEST_DELAY_SECONDS)

        self.stdout.write(self.style.SUCCESS(f"Done. Saved/updated {total_posts} LinkedIn posts."))
