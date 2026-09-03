import csv
import json
import re
import time
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-120b"

# NVIDIA NIM (build.nvidia.com) fallback — see companymap/management/commands/
# classify_linkedin_posts.py for why this specific model id is pinned rather
# than trusting NIM's live catalog.
NIM_BASE = "https://integrate.api.nvidia.com/v1"
NIM_URL = f"{NIM_BASE}/chat/completions"
NIM_MODEL = "openai/gpt-oss-120b"

BATCH_SIZE = 15
MAX_DESC_CHARS = 400
MAX_KEYWORDS_CHARS = 200

SEGMENT_LABELS = {
    "pharma_biotech": "Pharma/Biotech",
    "cdmo": "CDMO",
    "cro": "CRO",
    "cdmo_cro": "CDMO/CRO",
    "reagents": "Reagents",
    "equipment": "Equipment",
    "non_pharma": "Non-Pharma",
    "unclear": "Unclear",
}

SYSTEM_PROMPT = """You are triaging a list of California biopharma-adjacent companies for a B2B sales \
intelligence tool called Lunartree, which sells to supply-side vendors that serve pharma/biotech R&D \
and manufacturing (CDMOs, CROs, reagent suppliers, lab/medical equipment makers). For EACH company, \
assign exactly one segment from this list:

- pharma_biotech: a pharmaceutical or biotech company discovering/developing its OWN drugs, \
therapies, diagnostics, or platform (a potential BUYER of CDMO/CRO/reagent/equipment services, not a \
supplier of them). Includes "platform biotech" companies that sell their tech but are still primarily \
an R&D/drug-developer, not a contract vendor.
- cdmo: contract development & manufacturing organization — manufactures drug substance, drug \
product, biologics, or devices UNDER CONTRACT for other companies.
- cro: contract research organization — provides research, preclinical, clinical trial, bioanalytical, \
or testing SERVICES under contract for other companies.
- cdmo_cro: explicitly does both CDMO and CRO work as a combined/full-service offering.
- reagents: manufactures or sells reagents, consumables, lab chemicals, assay/diagnostic kits, media, \
antibodies, or similar as PRODUCTS (not services).
- equipment: manufactures or sells lab instruments, scientific/analytical equipment, medical devices, \
hardware, or systems.
- non_pharma: not in the biopharma/life-sciences space at all, OR life-sciences-adjacent but not a \
biotech/pharma company or a CDMO/CRO/reagent/equipment supplier (e.g. staffing agency, generic IT \
vendor, real estate, consulting firm, VC/investor, unrelated industry).
- unclear: genuinely not enough information in what's given to classify confidently.

Classify by the company's PRIMARY declared business. If a company both develops its own pipeline AND \
does contract work for others, prefer cdmo/cro/cdmo_cro only if the contract-services side is clearly \
the primary or an equally prominent business line; otherwise use pharma_biotech.

Return ONLY a JSON object of the exact shape:
{"results": [{"id": <row id as integer>, "segment": "<one of: pharma_biotech, cdmo, cro, cdmo_cro, \
reagents, equipment, non_pharma, unclear>"}, ...]}
One entry per company given, in the same order, using the exact numeric id provided for each."""


def truncate(text, max_chars):
    text = (text or "").strip().replace("\n", " ")
    if len(text) > max_chars:
        return text[:max_chars] + "..."
    return text


def build_user_prompt(rows):
    lines = []
    for r in rows:
        parts = [f"Name: {r['Company Name']}"]
        if r.get("Industry"):
            parts.append(f"Industry: {r['Industry']}")
        if r.get("SIC Codes"):
            parts.append(f"SIC: {r['SIC Codes']}")
        if r.get("NAICS Codes"):
            parts.append(f"NAICS: {r['NAICS Codes']}")
        desc = truncate(r.get("Short Description"), MAX_DESC_CHARS)
        if desc:
            parts.append(f"Description: {desc}")
        kw = truncate(r.get("Keywords"), MAX_KEYWORDS_CHARS)
        if kw:
            parts.append(f"Keywords: {kw}")
        lines.append(f"[id={r['_id']}] " + " | ".join(parts))
    return "Classify these companies:\n\n" + "\n\n".join(lines)


def extract_json_object(text):
    text = (text or "").strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("no JSON object found in model response")
    return json.loads(match.group(0))


def call_llm(session, url, headers, payload, label, stdout, stderr, max_attempts=3, max_wait=30):
    use_json_mode = "response_format" in payload
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
                continue
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return extract_json_object(content)
        except Exception as error:
            stderr.write(f"  {label} attempt {attempt + 1} failed: {error}")
            time.sleep(2)
    return None


class Command(BaseCommand):
    help = "Classify accounts in a CSV export (e.g. cal-accs.csv) into pharma/biotech supply-chain segments via Groq (with NVIDIA NIM fallback), writing an AI Segment column to an output CSV."

    def add_arguments(self, parser):
        parser.add_argument("input_csv", type=str)
        parser.add_argument("output_csv", type=str)
        parser.add_argument("--limit", type=int, default=None, help="Only classify the first N rows.")

    def handle(self, *args, **options):
        groq_key = settings.GROQ_API_KEY
        nim_key = getattr(settings, "NVIDIA_NIM_API_KEY", "")
        if not groq_key and not nim_key:
            raise CommandError("Neither GROQ_API_KEY nor NVIDIA_NIM_API_KEY is set in the environment.")

        input_path = Path(options["input_csv"])
        if not input_path.exists():
            raise CommandError(f"Input CSV not found: {input_path}")

        with input_path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            fieldnames = list(reader.fieldnames)
            rows = list(reader)

        for i, row in enumerate(rows):
            row["_id"] = i

        if options["limit"]:
            target_rows = rows[: options["limit"]]
        else:
            target_rows = rows

        session = requests.Session()
        groq_headers = {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"} if groq_key else None
        nim_headers = {"Authorization": f"Bearer {nim_key}", "Content-Type": "application/json"} if nim_key else None

        total = len(target_rows)
        self.stdout.write(f"Classifying {total} of {len(rows)} rows from {input_path}...")

        segments = {}
        groq_batches = 0
        nim_batches = 0
        failed_batches = 0

        for i in range(0, total, BATCH_SIZE):
            batch = target_rows[i : i + BATCH_SIZE]
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(batch)},
            ]
            batch_label = f"batch {i}-{i + len(batch)}"
            result = None

            if groq_key:
                payload = {
                    "model": GROQ_MODEL,
                    "messages": messages,
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1,
                }
                result = call_llm(
                    session, GROQ_URL, groq_headers, payload, f"{batch_label} [groq]",
                    self.stdout, self.stderr, max_attempts=1, max_wait=0,
                )
                if result:
                    groq_batches += 1

            if not result and nim_key:
                payload = {
                    "model": NIM_MODEL,
                    "messages": messages,
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1,
                }
                result = call_llm(
                    session, NIM_URL, nim_headers, payload, f"{batch_label} [nim]",
                    self.stdout, self.stderr, max_attempts=3, max_wait=20,
                )
                if result:
                    nim_batches += 1

            if not result:
                failed_batches += 1
                self.stderr.write(f"  {batch_label}: both providers failed, leaving unclassified")
                continue

            for item in result.get("results", []):
                try:
                    rid = int(item["id"])
                    seg = item["segment"]
                except (KeyError, ValueError, TypeError):
                    continue
                if seg in SEGMENT_LABELS:
                    segments[rid] = SEGMENT_LABELS[seg]

            self.stdout.write(f"  {batch_label}: classified {len(result.get('results', []))} (running total {len(segments)}/{total})")

        for row in rows:
            row["AI Segment"] = segments.get(row["_id"], "")
            del row["_id"]

        output_path = Path(options["output_csv"])
        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames + ["AI Segment"])
            writer.writeheader()
            writer.writerows(rows)

        from collections import Counter

        counts = Counter(row["AI Segment"] for row in rows)
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Wrote {output_path} ({groq_batches} groq batches, {nim_batches} nim batches, {failed_batches} failed batches)."))
        self.stdout.write("Segment breakdown:")
        for label in list(SEGMENT_LABELS.values()) + [""]:
            n = counts.get(label, 0)
            if n:
                self.stdout.write(f"  {label or '(unclassified)'}: {n}")
