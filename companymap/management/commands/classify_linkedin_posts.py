import json
import time

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, connection
from django.utils import timezone

from companymap.models import CompanyLinkedInPost


def save_resilient(post, fields):
    """Save a post, tolerating a Neon connection that went stale while this
    long-running command sat in time.sleep() between Groq calls. On a dropped
    connection, close it (Django reopens fresh on the next query) and retry
    once rather than letting one blip kill the whole run."""
    try:
        post.save(update_fields=fields)
    except OperationalError:
        connection.close()
        post.save(update_fields=fields)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"
BATCH_SIZE = 4
MAX_TEXT_CHARS = 700

VALID_CATEGORIES = {c.value for c in CompanyLinkedInPost.Category}

SYSTEM_PROMPT = """You are classifying LinkedIn posts from pharma/biotech/life-sciences supply-side \
companies (CDMOs, CROs, reagent and equipment suppliers, pharma manufacturers) for a B2B sales \
intelligence tool called Lunartree. For EACH post, assign exactly one category from this list:

- capability_expansion: new capability, manufacturing capacity, facility, equipment, technology \
platform, certification/accreditation
- new_partnership: new collaboration, licensing deal, joint venture, strategic alliance
- new_funding: new investment round, financing, grant, IPO
- research_milestone: new scientific findings, publication, data readout, clinical trial results, \
R&D breakthrough
- hiring: new hire announcement, leadership appointment, open roles, team growth
- event_attendance: attending, exhibiting, or speaking at a conference/trade show/event
- company_update: anything else (culture posts, holidays, generic marketing, awards, anniversaries, \
thought-leadership with no concrete news)

Also write a short headline for each post: STRICTLY 10 to 15 words, trade-press style, stating the \
concrete news (e.g. "Acme Bio opens new 50,000 sq ft GMP manufacturing facility in Boston"). If the \
post is a company_update with no real news, still write a brief neutral descriptive headline.

Return ONLY a JSON object of the exact shape:
{"results": [{"id": <post id as integer>, "category": "<one of the 7 categories above>", \
"headline": "<10-15 word headline>"}, ...]}
One entry per post given, in the same order, using the exact numeric id provided for each post."""


def build_user_prompt(posts):
    lines = []
    for p in posts:
        text = (p.post_text or "").strip().replace("\n", " ")
        if len(text) > MAX_TEXT_CHARS:
            text = text[:MAX_TEXT_CHARS] + "..."
        lines.append(f"[id={p.id}] Company: {p.company.name} | Text: {text}")
    return "Classify these posts:\n\n" + "\n\n".join(lines)


class Command(BaseCommand):
    help = "Classify CompanyLinkedInPost rows into news categories via Groq and write a short AI headline."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None, help="Only process the first N unclassified posts.")
        parser.add_argument("--reclassify", action="store_true", help="Re-run even posts that already have a category.")

    def handle(self, *args, **options):
        api_key = settings.GROQ_API_KEY
        if not api_key:
            raise CommandError("GROQ_API_KEY is not set in the environment.")

        qs = CompanyLinkedInPost.objects.select_related("company").order_by("id")
        if not options["reclassify"]:
            qs = qs.filter(category="")

        # Empty-text posts have nothing to classify from; tag them directly.
        empty = qs.filter(post_text="")
        empty_count = 0
        for post in empty:
            post.category = CompanyLinkedInPost.Category.COMPANY_UPDATE
            post.ai_headline = f"{post.company.name} posted on LinkedIn (no text captured)."
            post.ai_processed_at = timezone.now()
            save_resilient(post, ["category", "ai_headline", "ai_processed_at"])
            empty_count += 1

        qs = qs.exclude(post_text="")
        posts = list(qs[: options["limit"]] if options["limit"] else qs)
        total = len(posts)
        self.stdout.write(f"Tagged {empty_count} empty-text posts directly. Classifying {total} posts via Groq ({MODEL})...")

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        session = requests.Session()

        classified = 0
        failed_batches = 0

        for i in range(0, total, BATCH_SIZE):
            batch = posts[i : i + BATCH_SIZE]
            payload = {
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(batch)},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.2,
            }

            result = None
            for attempt in range(3):
                try:
                    response = session.post(GROQ_URL, headers=headers, json=payload, timeout=60)
                    if response.status_code == 429:
                        # Groq has occasionally been observed returning a retry-after
                        # far longer than the account's actual TPM window (confirmed
                        # via a direct probe showing the account was not really
                        # limited); cap the wait so one bad header can't stall a
                        # batch for tens of minutes.
                        wait = min(float(response.headers.get("retry-after", 5)), 30)
                        self.stderr.write(f"  batch {i}-{i+len(batch)} attempt {attempt+1}: 429, waiting {wait:.1f}s")
                        time.sleep(wait)
                        continue
                    response.raise_for_status()
                    content = response.json()["choices"][0]["message"]["content"]
                    result = json.loads(content)
                    break
                except Exception as error:
                    self.stderr.write(f"  batch {i}-{i+len(batch)} attempt {attempt+1} failed: {error}")
                    time.sleep(2)

            if not result:
                failed_batches += 1
                self.stderr.write(f"  batch {i}-{i+len(batch)}: giving up after 3 attempts")
                continue

            # Each Groq call can sit for minutes waiting out a rate limit, long
            # enough for Neon to silently drop an idle connection. Reusing a
            # connection in that state can hang forever on read() rather than
            # raising an error (seen in practice), so force a fresh one before
            # every batch of DB writes instead of waiting for a failure to react to.
            connection.close()

            by_id = {p.id: p for p in batch}
            now = timezone.now()
            for entry in result.get("results", []):
                post_id = entry.get("id")
                post = by_id.get(post_id)
                if not post:
                    continue
                category = entry.get("category") or ""
                if category not in VALID_CATEGORIES:
                    category = CompanyLinkedInPost.Category.COMPANY_UPDATE
                post.category = category
                post.ai_headline = (entry.get("headline") or "")[:200]
                post.ai_processed_at = now
                save_resilient(post, ["category", "ai_headline", "ai_processed_at"])
                classified += 1

            self.stdout.write(f"  [{min(i+BATCH_SIZE, total)}/{total}] classified so far: {classified}")

        self.stdout.write(self.style.SUCCESS(
            f"Done. Classified {classified} posts via Groq, {empty_count} tagged directly, {failed_batches} batches failed."
        ))
