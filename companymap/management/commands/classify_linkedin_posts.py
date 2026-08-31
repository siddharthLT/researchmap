import datetime as dt
import json
import re
import time

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, connection
from django.utils import timezone

from companymap.models import CompanyLinkedInPost


def save_resilient(post, fields):
    """Save a post, tolerating a Neon connection that went stale while this
    long-running command sat in time.sleep() between LLM calls. On a dropped
    connection, close it (Django reopens fresh on the next query) and retry
    once rather than letting one blip kill the whole run."""
    try:
        post.save(update_fields=fields)
    except OperationalError:
        connection.close()
        post.save(update_fields=fields)


GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-120b"

# NVIDIA NIM (build.nvidia.com) is used as a fallback once Groq's account-wide
# daily token cap (TPD) is exhausted — Groq's per-minute limit recovers fine,
# but the on_demand tier's 200k-tokens/day cap can stay pinned for hours.
NIM_BASE = "https://integrate.api.nvidia.com/v1"
NIM_URL = f"{NIM_BASE}/chat/completions"
NIM_MODELS_URL = f"{NIM_BASE}/models"
# Only used if the live /v1/models lookup below fails — NVIDIA's catalog is
# renamed/retired over time (the same trap that broke a hardcoded Groq model
# id earlier), so prefer discovering a live model instead of trusting this.
# openai/gpt-oss-120b is confirmed working end-to-end on this account (many
# listed nemotron/llama variants either 404'd as "not found for account" or
# hung indefinitely despite being listed — NIM's /v1/models catalog is not a
# reliable guide to what's actually invokable on a given key).
NIM_FALLBACK_MODEL = "openai/gpt-oss-120b"

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


def parse_date_boundary(date_str):
    """Parse a --since/--until YYYY-MM-DD flag as a UTC midnight boundary
    (post_date is stored in UTC) rather than the server's local TIME_ZONE,
    so the filter means what it says regardless of where this runs."""
    naive = dt.datetime.strptime(date_str, "%Y-%m-%d")
    return naive.replace(tzinfo=dt.timezone.utc)


def build_user_prompt(posts):
    lines = []
    for p in posts:
        text = (p.post_text or "").strip().replace("\n", " ")
        if len(text) > MAX_TEXT_CHARS:
            text = text[:MAX_TEXT_CHARS] + "..."
        lines.append(f"[id={p.id}] Company: {p.company.name} | Text: {text}")
    return "Classify these posts:\n\n" + "\n\n".join(lines)


def extract_json_object(text):
    """Parse the model's JSON reply, tolerating providers/models that don't
    honor response_format=json_object and wrap the JSON in prose or markdown
    fences instead of returning it bare."""
    text = (text or "").strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("no JSON object found in model response")
    return json.loads(match.group(0))


def resolve_nim_model(session, api_key, stderr):
    """Ask NVIDIA NIM which models are currently live rather than trusting a
    hardcoded id to still exist."""
    try:
        resp = session.get(
            NIM_MODELS_URL, headers={"Authorization": f"Bearer {api_key}"}, timeout=20
        )
        resp.raise_for_status()
        ids = [m["id"] for m in resp.json().get("data", [])]
    except Exception as error:
        stderr.write(f"  could not list NVIDIA NIM models ({error}); using fallback model id")
        return NIM_FALLBACK_MODEL

    # openai/gpt-oss-* is confirmed reliable on this account (see comment on
    # NIM_FALLBACK_MODEL above) — use it directly if listed, rather than
    # guessing among the many nemotron/llama variants of unknown availability.
    for preferred in ("openai/gpt-oss-120b", "openai/gpt-oss-20b"):
        if preferred in ids:
            return preferred

    exclude = ("embed", "rerank", "vision", "guard", "safe", "code", "vlm", "moderation")
    candidates = [
        m
        for m in ids
        if ("instruct" in m.lower() or "chat" in m.lower() or "nemotron" in m.lower())
        and not any(x in m.lower() for x in exclude)
    ]
    for preferred in ("nemotron-super", "nemotron", "llama-3.3", "llama-3.1", "llama-3"):
        for m in candidates:
            if preferred in m.lower():
                return m
    return candidates[0] if candidates else NIM_FALLBACK_MODEL


def call_llm(session, url, headers, payload, label, stdout, stderr, max_attempts=3, max_wait=30):
    """POST to an OpenAI-compatible chat completions endpoint and return the
    parsed JSON result, retrying on transient failures and 429s. Falls back
    to a response_format-less request if the provider rejects json_object
    mode (returns that as saw_json_mode_error so the caller can stop asking
    for it on later batches)."""
    use_json_mode = "response_format" in payload
    saw_json_mode_error = False
    for attempt in range(max_attempts):
        body = dict(payload)
        if not use_json_mode:
            body.pop("response_format", None)
        try:
            response = session.post(url, headers=headers, json=body, timeout=60)
            if response.status_code == 429:
                wait = min(float(response.headers.get("retry-after", 5)), max_wait)
                stderr.write(f"  {label} attempt {attempt + 1}: 429, waiting {wait:.1f}s")
                if wait > 0:
                    time.sleep(wait)
                continue
            if response.status_code == 400 and use_json_mode and "response_format" in response.text.lower():
                stdout.write(f"  {label}: provider rejected response_format=json_object, retrying without it")
                use_json_mode = False
                saw_json_mode_error = True
                continue
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return extract_json_object(content), saw_json_mode_error
        except Exception as error:
            stderr.write(f"  {label} attempt {attempt + 1} failed: {error}")
            time.sleep(2)
    return None, saw_json_mode_error


class Command(BaseCommand):
    help = "Classify CompanyLinkedInPost rows into news categories via Groq (with an NVIDIA NIM fallback) and write a short AI headline."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None, help="Only process the first N unclassified posts.")
        parser.add_argument("--reclassify", action="store_true", help="Re-run even posts that already have a category.")
        parser.add_argument("--since", type=str, default=None, help="Only process posts with post_date >= this date (YYYY-MM-DD).")
        parser.add_argument("--until", type=str, default=None, help="Only process posts with post_date < this date (YYYY-MM-DD, exclusive).")

    def handle(self, *args, **options):
        groq_key = settings.GROQ_API_KEY
        nim_key = getattr(settings, "NVIDIA_NIM_API_KEY", "")
        if not groq_key and not nim_key:
            raise CommandError("Neither GROQ_API_KEY nor NVIDIA_NIM_API_KEY is set in the environment.")

        session = requests.Session()
        groq_headers = {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"}
        nim_headers = {"Authorization": f"Bearer {nim_key}", "Content-Type": "application/json"} if nim_key else None
        nim_model = resolve_nim_model(session, nim_key, self.stderr) if nim_key else None
        nim_json_mode = True

        if nim_key:
            self.stdout.write(f"NVIDIA NIM fallback enabled (model: {nim_model}).")
        else:
            self.stdout.write("No NVIDIA_NIM_API_KEY set — running Groq-only, no fallback on rate limits.")

        # Newest first by default so a partial/interrupted run still covers
        # the most relevant (recent) content, and so --since/--until slices
        # can be run as tiers (newest month first, then the next, etc).
        qs = CompanyLinkedInPost.objects.select_related("company").order_by("-post_date")
        if not options["reclassify"]:
            qs = qs.filter(category="")
        if options["since"]:
            qs = qs.filter(post_date__gte=parse_date_boundary(options["since"]))
        if options["until"]:
            qs = qs.filter(post_date__lt=parse_date_boundary(options["until"]))

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
        self.stdout.write(f"Tagged {empty_count} empty-text posts directly. Classifying {total} posts...")

        classified = 0
        failed_batches = 0
        groq_batches = 0
        nim_batches = 0

        for i in range(0, total, BATCH_SIZE):
            batch = posts[i : i + BATCH_SIZE]
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(batch)},
            ]
            batch_label = f"batch {i}-{i + len(batch)}"

            result = None
            provider_used = None

            if groq_key:
                payload = {
                    "model": GROQ_MODEL,
                    "messages": messages,
                    "response_format": {"type": "json_object"},
                    "temperature": 0.2,
                }
                # A single, no-wait attempt: Groq's daily cap can stay pinned
                # for hours, so don't burn time retrying/backing off on it —
                # fall straight through to NVIDIA NIM and let Groq's occasional
                # trickle of headroom get picked up by whichever batch is
                # lucky enough to hit it, rather than blocking on it.
                result, _ = call_llm(
                    session, GROQ_URL, groq_headers, payload, f"{batch_label} [groq]",
                    self.stdout, self.stderr, max_attempts=1, max_wait=0,
                )
                if result:
                    provider_used = "groq"

            if not result and nim_key:
                payload = {
                    "model": nim_model,
                    "messages": messages,
                    "temperature": 0.2,
                }
                if nim_json_mode:
                    payload["response_format"] = {"type": "json_object"}
                result, saw_json_mode_error = call_llm(
                    session, NIM_URL, nim_headers, payload, f"{batch_label} [nim:{nim_model}]",
                    self.stdout, self.stderr, max_attempts=3, max_wait=30,
                )
                if saw_json_mode_error:
                    nim_json_mode = False
                if result:
                    provider_used = "nim"

            if not result:
                failed_batches += 1
                self.stderr.write(f"  {batch_label}: giving up on all providers")
                continue

            if provider_used == "groq":
                groq_batches += 1
            else:
                nim_batches += 1

            # Each LLM call can sit for a while waiting out a rate limit, long
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

            self.stdout.write(
                f"  [{min(i + BATCH_SIZE, total)}/{total}] classified so far: {classified} "
                f"(groq batches: {groq_batches}, nim batches: {nim_batches})"
            )

        self.stdout.write(self.style.SUCCESS(
            f"Done. Classified {classified} posts ({groq_batches} batches via Groq, {nim_batches} via NVIDIA NIM), "
            f"{empty_count} tagged directly, {failed_batches} batches failed on all providers."
        ))
