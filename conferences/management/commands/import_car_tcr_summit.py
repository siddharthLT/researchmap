"""One-off import for the 11th CAR-TCR Summit (Boston, Sept 15-17 2026).

Unlike the other conference importers, the source here is a 34-page visual
event-guide PDF (conf/Full-Event-Guide-11th-CAR-TCR-Summit.pdf) with no
structured spreadsheet — company names, sponsorship tiers, and the full
agenda were transcribed by hand from the PDF pages (including logo-only
mentions that never appear as plain text). Company research (website,
segment, HQ) for the ~26 names that weren't already recognizable vendors was
done via a one-time web-research pass; the results are hardcoded below
rather than re-fetched on every run.

Company classification approach: this is a clinical/scientific cell-therapy
conference, so the "speaker" and "audience preview" company lists are almost
entirely CAR-T/TCR-T drug developers (buyer-side), not vendors. Those are
bulk-classified as Pharma/Biotech (added to the DB, hidden from the map).
Investors, academic/cancer-center, regulatory, and nonprofit entities are
dropped entirely (not added to the DB, not kept as conference attendees),
matching how non-vendor/non-biotech companies have been handled for the
other conferences in this app. Only the partner/exhibitor tier is treated as
genuine supply-side vendor candidates.
"""
import datetime

from django.core.management.base import BaseCommand
from django.db import transaction

from companymap.models import Company
from companymap.management.commands.import_companies import (
    CITY_CENTROIDS, WEST_COAST_STATES, EAST_COAST_STATES,
)
from conferences.management.commands.import_conference_xlsx import canon, classify_session_type
from conferences.models import Conference, ConferenceCompany, Session, Speaker

SEGMENT_LABEL = {
    "cdmo": "CDMO", "cro": "CRO", "cdmo_cro": "CDMO/CRO",
    "reagents": "Reagents", "equipment": "Equipment", "packaging": "Packaging",
}

# name -> (tags, notes) for every ConferenceCompany row to create
COMPANY_TAGS = {
    "Cellares": (["exhibitor"], "Lead Partner"),
    "Lonza": (["exhibitor"], "Expertise Partner"),
    "Sartorius": (["exhibitor"], "Expertise Partner"),
    "Accellix": (["exhibitor"], "Program Partner"),
    "Agilent Technologies": (["exhibitor"], "Program Partner"),
    "Beacon": ([], "Program Partner"),
    "BioLegend": (["exhibitor"], "Program Partner (from Revvity)"),
    "ElevateBio": (["exhibitor"], "Program Partner"),
    "Fresenius Kabi": (["exhibitor"], "Program Partner"),
    "LumaCyte": (["exhibitor"], "Program Partner"),
    "Miltenyi Biotec": (["exhibitor"], "Program Partner"),
    "Minaris": (["exhibitor"], "Program Partner"),
    "Syenex": (["exhibitor"], "Program Partner"),
    "TriLink BioTechnologies": (["exhibitor"], "Program Partner (part of Maravai LifeSciences)"),
    "Waters": (["exhibitor"], "Program Partner"),
    "PBS Biotech": (["exhibitor"], "Hosting Partner"),
    "ScaleReady": (["exhibitor"], "Hosting Partner"),
    "Astraveus": (["exhibitor"], "Innovation Partner"),
    "Bracco": (["exhibitor"], "Innovation Partner"),
    "Promega": (["exhibitor"], "Innovation Partner"),
    "AIT Worldwide Logistics": (["exhibitor"], "Exhibition Partner"),
    "Akron Bio": (["exhibitor"], "Exhibition Partner"),
    "American Red Cross Cell and Gene Therapy Solutions": (["exhibitor"], "Exhibition Partner"),
    "Biocytogen": (["exhibitor"], "Exhibition Partner"),
    "BioIVT": (["exhibitor"], "Exhibition Partner"),
    "Chemometec": (["exhibitor"], "Exhibition Partner"),
    "Aldevron": (["exhibitor"], "Exhibition Partner"),
    "GenScript": (["exhibitor"], "Exhibition Partner"),
    "Kincell": (["exhibitor"], "Exhibition Partner"),
    "Logos Biosystems": (["exhibitor"], "Exhibition Partner (part of Aligned Genetics)"),
    "MaxCyte": (["exhibitor"], "Exhibition Partner"),
    "Nona Biosciences": (["exhibitor"], "Exhibition Partner"),
    "Ozette": (["exhibitor"], "Exhibition Partner"),
    "Pixelgen Technologies": (["exhibitor"], "Exhibition Partner"),
    "QuickSTAT": (["exhibitor"], "Exhibition Partner (a Kuehne+Nagel company)"),
    "Trenchant": (["exhibitor"], "Exhibition Partner"),
    "Versiti": (["exhibitor"], "Exhibition Partner"),
    "Puresyn": (["exhibitor"], "Exhibition Partner"),
    "Catalent": (["exhibitor"], "Event Partner"),
    "Kapadi": (["exhibitor"], "Event Partner (a humaneva group company)"),
    "ProBio": (["exhibitor"], "Event Partner"),
    "ViroCell Biologics": (["exhibitor"], "Event Partner"),
    "Vitrafy Life Sciences": (["exhibitor"], "Event Partner"),
    "VJ Bio": (["exhibitor"], "Event Partner"),
    "Dana-Farber Cancer Institute": (["exhibitor"], "Exhibition Partner + academic speaker"),
    "LanceBio Ventures": (["speaker_session"], "Investor speaker (Bioptic)"),
    "AMoon Fund": (["speaker_session"], "Investor speaker"),
    "Mesa Verde Venture Partners": (["speaker_session"], "Investor speaker"),
    "Fast Track Initiative": (["speaker_session"], "Investor speaker"),
    "Aera Therapeutics": (["speaker_session"], "C-suite speaker"),
    "Allergene AI": (["speaker_session"], "C-suite speaker; track chair"),
    "Anocca": (["speaker_session"], "C-suite speaker"),
    "Autolus Therapeutics": (["speaker_session"], "C-suite speaker"),
    "BlueSphere Bio": (["speaker_session"], "C-suite speaker"),
    "Captain T Cell": (["speaker_session"], "C-suite speaker"),
    "GentiBio": (["speaker_session"], "C-suite speaker"),
    "IASO Biotherapeutics": (["speaker_session"], "C-suite speaker"),
    "Imviva Biotech": (["speaker_session"], "C-suite speaker"),
    "Kiragen Bio": (["speaker_session"], "C-suite speaker"),
    "Overland Therapeutics": (["speaker_session"], "C-suite speaker"),
    "PhosphoGam": (["speaker_session"], "C-suite speaker"),
    "JW Therapeutics": (["speaker_session"], "C-suite speaker"),
    "LIfT Biosciences": (["speaker_session"], "C-suite speaker"),
    "Link Cell Therapies": (["speaker_session"], "C-suite speaker"),
    "NKILT Therapeutics": (["speaker_session"], "C-suite speaker"),
    "Pan Cancer T": (["speaker_session"], "C-suite speaker"),
    "PolTREG": (["speaker_session"], "C-suite speaker (Immuthera)"),
    "Precigen": (["speaker_session"], "C-suite speaker"),
    "Senti Biosciences": (["speaker_session"], "C-suite speaker"),
    "T-Knife Therapeutics": (["speaker_session"], "C-suite speaker"),
    "Torpedo Bio": (["speaker_session"], "C-suite speaker"),
    "Tr1X Bio": (["speaker_session"], "C-suite speaker"),
    "AstraZeneca": (["speaker_session"], "Pharma Titan speaker"),
    "Bristol Myers Squibb": (["speaker_session"], "Pharma Titan speaker"),
    "Eli Lilly & Co.": (["speaker_session"], "Pharma Titan speaker"),
    "Johnson & Johnson": (["speaker_session"], "Pharma Titan speaker"),
    "Kite Pharma": (["speaker_session"], "Pharma Titan speaker (A Gilead Company)"),
    "Novartis": (["speaker_session"], "Pharma Titan speaker"),
    "Regeneron": (["speaker_session"], "Pharma Titan speaker"),
    "Cabaletta Bio": (["speaker_session"], "Biotech Visionary speaker"),
    "Caribou Biosciences": (["speaker_session"], "Biotech Visionary speaker"),
    "Cartherics": (["speaker_session"], "Biotech Visionary speaker"),
    "Century Therapeutics": (["speaker_session"], "Biotech Visionary speaker"),
    "CPTx": (["speaker_session"], "Biotech Visionary speaker"),
    "Eureka Therapeutics": (["speaker_session"], "Biotech Visionary speaker"),
    "Fate Therapeutics": (["speaker_session"], "Biotech Visionary speaker"),
    "Immatics": (["speaker_session"], "Biotech Visionary speaker"),
    "Legend Biotech": (["speaker_session"], "Biotech Visionary speaker"),
    "Lyell Immunopharma": (["speaker_session"], "Biotech Visionary speaker"),
    "Sail Biomedicines": (["speaker_session"], "Biotech Visionary speaker"),
    "Stealth Biotech": (["speaker_session"], "Biotech Visionary speaker"),
    "Vyriad": (["speaker_session"], "Biotech Visionary speaker"),
    "Allotera Therapeutics": (["speaker_session"], "Biotech Visionary speaker"),
    "Umoja Biopharma": (["speaker_session"], "Biotech Visionary speaker"),
    "Zelig Therapeutics": (["speaker_session"], "Biotech Visionary speaker"),
    "Alliance for Regenerative Medicine": (["speaker_session"], "Academic/Regulatory speaker (trade association)"),
    "Emily Whitehead Foundation": (["speaker_session"], "Academic/Regulatory speaker (nonprofit)"),
    "Memorial Sloan Kettering Cancer Center": (["speaker_session"], "Academic/Cancer Center speaker"),
    "Moffitt Cancer Center": (["speaker_session"], "Academic/Cancer Center speaker"),
    "University of Pennsylvania": (["speaker_session"], "Academic speaker"),
    "Stanford Medicine": (["speaker_session"], "Academic speaker (Stanford GMP Facility)"),
    "MHRA": (["speaker_session"], "Regulatory speaker (UK MHRA)"),
    "University of Southern California": (["speaker_session"], "Academic speaker"),
    "Gulf Coast Blood": (["speaker_session"], "Service Provider speaker"),
    "LifeSouth Community Blood Centers": (["speaker_session"], "Service Provider speaker"),
    "Vitalant": (["speaker_session"], "Service Provider speaker"),
    "Waters Biosciences": (["speaker_session"], "Service Provider speaker (same company as Waters)"),
    "Alaya.bio": ([], "Audience preview"),
    "Allogene": ([], "Audience preview"),
    "BioNTech": ([], "Audience preview"),
    "Boehringer Ingelheim": ([], "Audience preview"),
    "Cartesian Therapeutics": ([], "Audience preview"),
    "Cellectis": ([], "Audience preview"),
    "Editas Medicine": ([], "Audience preview"),
    "Exuma Biotech": ([], "Audience preview"),
    "Genentech": ([], "Audience preview"),
    "Gilead": ([], "Audience preview"),
    "Iovance Biotherapeutics": ([], "Audience preview"),
    "KermalBio": ([], "Audience preview"),
    "KSQ Therapeutics": ([], "Audience preview"),
    "Moderna": ([], "Audience preview"),
    "nkarta": ([], "Audience preview"),
    "Obsidian Therapeutics": ([], "Audience preview"),
    "RIDOX": ([], "Audience preview"),
    "Sana Biotechnology": ([], "Audience preview"),
    "Strike Pharma": ([], "Audience preview"),
    "Takeda": ([], "Audience preview"),
    "TSCAN Therapeutics": ([], "Audience preview"),
    "Wugen": ([], "Audience preview"),
}

# names already in companymap.Company under a slightly different string
# (missed by canon() exact-match, confirmed by hand)
DIRECT_LINKS = {"Fresenius Kabi": 2197, "GenScript": 615, "VJ Bio": 599}

# names that resolve via canon() to an existing record (kept explicit rather
# than re-deriving at runtime, since the point is reproducibility)
ALREADY_MATCHED = {
    "Bristol Myers Squibb", "Novartis", "Regeneron", "CPTx", "Boehringer Ingelheim", "Takeda",
    "Lonza", "Agilent Technologies", "BioLegend", "ElevateBio", "Miltenyi Biotec", "Minaris",
    "Syenex", "TriLink BioTechnologies", "PBS Biotech", "Promega", "Aldevron", "BioIVT",
    "Catalent", "ProBio",
}

SELF_CLASSIFIED = {
    "Waters": dict(segment="equipment", city="Milford", state="MA", country="United States",
                   domain="waters.com", notes="Analytical instrument maker (LC-MS, chromatography)."),
    "Gulf Coast Blood": dict(segment="reagents", city="Houston", state="TX", country="United States",
                              domain="", notes="Regional blood center supplying cell therapy starting material."),
    "LifeSouth Community Blood Centers": dict(segment="reagents", city="Gainesville", state="FL", country="United States",
                                               domain="lifesouth.org", notes="Nonprofit blood center network."),
    "Vitalant": dict(segment="reagents", city="Scottsdale", state="AZ", country="United States",
                      domain="vitalant.org", notes="National nonprofit blood services organization."),
}
# same underlying company as "Waters" — link, don't duplicate
ALIAS_OF = {"Waters Biosciences": "Waters"}

PHARMA_BIOTECH_BULK = [
    "Aera Therapeutics", "Allergene AI", "Anocca", "Autolus Therapeutics", "BlueSphere Bio",
    "Captain T Cell", "GentiBio", "IASO Biotherapeutics", "Imviva Biotech", "Kiragen Bio",
    "Overland Therapeutics", "PhosphoGam", "JW Therapeutics", "LIfT Biosciences",
    "Link Cell Therapies", "NKILT Therapeutics", "Pan Cancer T", "PolTREG", "Precigen",
    "Senti Biosciences", "T-Knife Therapeutics", "Torpedo Bio", "Tr1X Bio",
    "Cabaletta Bio", "Caribou Biosciences", "Cartherics", "Century Therapeutics",
    "Eureka Therapeutics", "Fate Therapeutics", "Immatics", "Legend Biotech",
    "Lyell Immunopharma", "Sail Biomedicines", "Stealth Biotech", "Vyriad",
    "Allotera Therapeutics", "Umoja Biopharma", "Zelig Therapeutics",
    "AstraZeneca", "Eli Lilly & Co.", "Johnson & Johnson", "Kite Pharma",
    "Alaya.bio", "Allogene", "BioNTech", "Cartesian Therapeutics", "Cellectis",
    "Editas Medicine", "Exuma Biotech", "Genentech", "Gilead", "Iovance Biotherapeutics",
    "KermalBio", "KSQ Therapeutics", "Moderna", "nkarta", "Obsidian Therapeutics",
    "RIDOX", "Sana Biotechnology", "Strike Pharma", "TSCAN Therapeutics", "Wugen",
]

DROP_NON_PHARMA = [
    "LanceBio Ventures", "AMoon Fund", "Mesa Verde Venture Partners", "Fast Track Initiative",
    "Alliance for Regenerative Medicine", "Emily Whitehead Foundation",
    "Memorial Sloan Kettering Cancer Center", "Moffitt Cancer Center",
    "University of Pennsylvania", "Stanford Medicine", "MHRA", "University of Southern California",
    "Dana-Farber Cancer Institute", "Beacon",  # Beacon: cell-therapy deal-intelligence data platform, not a vendor
]

# one-time web research results for the exhibitor/partner-tier names that
# weren't already recognizable (segment, city, state, country, domain, notes)
VENDOR_RESEARCH = {
    "Cellares": ("cdmo", "South San Francisco", "CA", "United States", "cellares.com", "Integrated cell-therapy development & manufacturing organization (IDMO)."),
    "Sartorius": ("equipment", "", "", "Germany", "sartorius.com", "Bioprocessing/single-use systems and lab equipment maker (Göttingen)."),
    "Accellix": ("equipment", "San Jose", "CA", "United States", "accellix.com", "Automated cell analysis instruments for cell therapy QC."),
    "LumaCyte": ("equipment", "Charlottesville", "VA", "United States", "lumacyte.com", "Laser force cytology instruments."),
    "ScaleReady": ("equipment", "St. Paul", "MN", "United States", "scaleready.com", "Cell therapy manufacturing platform (Wilson Wolf / Bio-Techne JV)."),
    "Astraveus": ("equipment", "", "", "France", "astraveus.com", "Microfluidic-powered automated cell therapy manufacturing."),
    "Bracco": ("reagents", "", "", "Italy", "bracco.com", "Diagnostic imaging company; exhibits for its BubbleGen cell-selection products."),
    "AIT Worldwide Logistics": ("packaging", "Itasca", "IL", "United States", "aitworldwide.com", "Specialty logistics incl. pharma cold-chain shipping."),
    "Akron Bio": ("reagents", "Boca Raton", "FL", "United States", "akronbiotech.com", "Raw materials/cytokines for cell & gene therapy manufacturing."),
    "American Red Cross Cell and Gene Therapy Solutions": ("reagents", "Washington", "DC", "United States", "redcrossblood.org", "Blood/biospecimen starting-material solutions for cell & gene therapy."),
    "Biocytogen": ("cro", "", "", "China", "biocytogen.com", "Antibody/animal model contract research."),
    "Chemometec": ("equipment", "", "", "Denmark", "chemometec.com", "Automated cell counting/analysis instruments."),
    "Kincell": ("cdmo", "Gainesville", "FL", "United States", "kincellbio.com", "Cell and gene therapy CDMO."),
    "Logos Biosystems": ("equipment", "", "", "South Korea", "logosbio.com", "Cell imaging/counting instruments (part of Aligned Genetics)."),
    "MaxCyte": ("equipment", "Rockville", "MD", "United States", "maxcyte.com", "Cell engineering (electroporation) instruments."),
    "Nona Biosciences": ("cro", "", "", "China", "nonabio.com", "Antibody discovery contract research."),
    "Ozette": ("cro", "Seattle", "WA", "United States", "ozette.com", "AI-powered cytometry/immune profiling analysis services."),
    "Pixelgen Technologies": ("reagents", "", "", "Sweden", "pixelgen.com", "Single-cell spatial proteomics reagent kits."),
    "QuickSTAT": ("packaging", "Jamaica", "NY", "United States", "quickstat.com", "Time-critical pharma/cell-therapy logistics (a Kuehne+Nagel company)."),
    "Trenchant": ("equipment", "San Diego", "CA", "United States", "trenchantbio.com", "Automated CAR-T manufacturing platform."),
    "Versiti": ("reagents", "Milwaukee", "WI", "United States", "versiti.org", "Blood center network, cell therapy starting material."),
    "Puresyn": ("reagents", "Malvern", "PA", "United States", "puresyn.com", "Custom nucleic acid/peptide reagent manufacturing."),
    "Kapadi": ("cro", "Raleigh", "NC", "United States", "kapadi.com", "Oncology CRO (a Humaneva Group company)."),
    "ViroCell Biologics": ("cdmo", "", "", "United Kingdom", "virocell.com", "Viral vector CDMO for cell & gene therapy."),
    "Vitrafy Life Sciences": ("equipment", "", "", "Australia", "vitrafy.com", "Cryopreservation/cold-chain technology for cell & gene therapy."),
}


class Command(BaseCommand):
    help = "Import the 11th CAR-TCR Summit (manually transcribed from the event-guide PDF)."

    @transaction.atomic
    def handle(self, *args, **options):
        conference, created = Conference.objects.update_or_create(
            name="CAR-TCR Summit 2026",
            defaults={
                "location": "Boston, MA",
                "start_date": datetime.date(2026, 9, 15),
                "end_date": datetime.date(2026, 9, 17),
                "source_file": "Full-Event-Guide-11th-CAR-TCR-Summit.pdf",
                "description": "11th Annual CAR-TCR Summit: Engineering a Disease-Free World. "
                                "Manually transcribed from the event guide PDF (no structured data source).",
            },
        )
        conference.companies.all().delete()
        conference.sessions.all().delete()
        conference.speakers.all().delete()

        company_id_by_name = {}
        company_id_by_name.update(DIRECT_LINKS)

        existing_by_canon = {}
        for c in Company.objects.only("id", "name"):
            key = canon(c.name)
            if key and key not in existing_by_canon:
                existing_by_canon[key] = c.id
        for name in ALREADY_MATCHED:
            cid = existing_by_canon.get(canon(name))
            if cid is None:
                self.stderr.write(f"WARNING: expected pre-existing match for {name!r} not found")
                continue
            company_id_by_name[name] = cid

        for name, spec in SELF_CLASSIFIED.items():
            c = self._get_or_create(name, SEGMENT_LABEL[spec["segment"]], spec["city"],
                                     spec["state"], spec["country"], spec["domain"], spec["notes"])
            company_id_by_name[name] = c.id
        for alias, target in ALIAS_OF.items():
            company_id_by_name[alias] = company_id_by_name[target]

        for name in PHARMA_BIOTECH_BULK:
            c = self._get_or_create(name, "Pharma / Biotech", notes="CAR-T/TCR-T cell therapy developer.")
            if c.show_on_map:
                c.show_on_map = False
                c.save(update_fields=["show_on_map"])
            company_id_by_name[name] = c.id

        for name in DROP_NON_PHARMA:
            company_id_by_name[name] = None

        for name, (seg, city, state, country, domain, notes) in VENDOR_RESEARCH.items():
            c = self._get_or_create(name, SEGMENT_LABEL[seg], city, state, country, domain, notes)
            company_id_by_name[name] = c.id

        created_ccs = 0
        dropped = 0
        for name, (tags, notes) in COMPANY_TAGS.items():
            cid = company_id_by_name.get(name, "MISSING")
            if cid is None:
                dropped += 1
                continue
            if cid == "MISSING":
                self.stderr.write(f"WARNING: no resolution for {name!r}, skipping")
                continue
            ConferenceCompany.objects.create(conference=conference, name=name, tags=tags, notes=notes, company_id=cid)
            created_ccs += 1

        session_count, speaker_count = self._import_sessions(conference)

        self.stdout.write(self.style.SUCCESS(
            f"{'Created' if created else 'Updated'} {conference.name}: "
            f"{created_ccs} companies ({dropped} dropped as non-vendor/non-biotech), "
            f"{session_count} sessions, {speaker_count} speakers."
        ))
        self.stdout.write(
            "Note: new companies with a US city/state but no CITY_CENTROIDS entry won't have "
            "map coordinates yet — run geocode_companies to fill those in."
        )

    def _get_or_create(self, name, segment_label, city="", state="", country="", domain="", notes=""):
        existing = Company.objects.filter(name__iexact=name).first()
        if existing:
            return existing
        is_us = country == "United States"
        lat = lng = None
        if is_us and city and state:
            centroid = CITY_CENTROIDS.get((city, state))
            if centroid:
                lat, lng = centroid
        show_on_map = bool(is_us and lat is not None and segment_label in SEGMENT_LABEL.values())
        region = Company.Region.OTHER
        if is_us:
            if state in WEST_COAST_STATES:
                region = Company.Region.WEST_COAST
            elif state in EAST_COAST_STATES:
                region = Company.Region.EAST_COAST
        return Company.objects.create(
            name=name, url=f"https://{domain}" if domain else "", domain=domain,
            city=city, state_code=state if is_us else "", country=country,
            segment=segment_label, region=region, latitude=lat, longitude=lng,
            show_on_map=show_on_map, account_list_source="CAR-TCR Summit 2026 import", notes=notes,
        )

    def _import_sessions(self, conference):
        D1, D2, D3 = datetime.date(2026, 9, 15), datetime.date(2026, 9, 16), datetime.date(2026, 9, 17)

        def t(h, m):
            return datetime.time(h, m)

        raw = [
            (D1, t(9, 0), "Boosting the Efficacy of TCR- & CAR-T Cells Using a Novel TGF-beta SWITCH Receptor", "Cell Therapy Fundamentals Bootcamp", [("Felix Lorenz", "Captain T Cell")]),
            (D1, t(9, 0), "Disrupting the Autoimmune Disease Treatment Paradigm - Transient, Potent, & Scalable eRNA-based In Vivo CD19 CAR-T Therapy", "In Vivo Bootcamp", [("Siobhan Rice", "Sail Biomedicines")]),
            (D1, t(9, 0), "Workshop A: Leveraging Automated Manufacturing to Reduce COGs & Enhance Commercial Scale Readiness While Aligning with GMP Expectations", "Automated Manufacturing, Regulations & Partnering Bootcamp", []),
            (D1, t(9, 30), "Enhancing CAR-T Persistence & Outcomes through IL-2-Driven Optimization & Strategic Combination Therapy", "Cell Therapy Fundamentals Bootcamp", []),
            (D1, t(9, 30), "Panel Discussion: Investigating the Evolution of In Vivo Therapies to Accelerate Innovations", "In Vivo Bootcamp", [("Ruth Salmon", "Bristol Myers Squibb"), ("Luke Russell", "Vyriad"), ("Sidharth Kerkar", "Allergene AI")]),
            (D1, t(9, 30), "Workshop A Continued", "Automated Manufacturing, Regulations & Partnering Bootcamp", [("Xiuyan Wang", "Memorial Sloan Kettering Cancer Center"), ("Stephan Krause", "Bristol Myers Squibb"), ("Vaishali Shulka", "Eli Lilly & Co."), ("Sharon Anderson", "Alliance for Regenerative Medicine")]),
            (D1, t(10, 0), "Defining the Depth & Breadth of B-Cell Depletion to Understand the Depth & Breadth of Therapeutic Success", "Cell Therapy Fundamentals Bootcamp", [("Jan Davidson", "Imviva Biotech")]),
            (D1, t(10, 0), "Reserved for Syenex, Inc.", "In Vivo Bootcamp", [("Jay Rosanelli", "Syenex")]),
            (D1, t(11, 30), "Utilizing Targeted Gene Editing to Engineer Durable T-Cell Therapies", "Optimizing Approaches to Prevent Downregulation", [("Enrique Zudaire", "Caribou Biosciences")]),
            (D1, t(11, 30), "Designing In Vivo T-Cell Therapies to Combat Resistance & Enhance Durability in Solid Tumors", "In Vivo Bootcamp", [("Peggy Sotiropoulou", "T-Knife Therapeutics")]),
            (D1, t(11, 30), "Analyzing Acquisition Case Studies to Understand Deal Drivers & Strategic Characteristics", "Building Strong Regulatory & Commercial Strategies", [("Safia Abdi", "Beacon")]),
            (D1, t(12, 0), "Tailoring CAR-T Cell Therapies for Solid Tumors", "Optimizing Approaches to Prevent Downregulation", [("Leonardo Ferreira", "Torpedo Bio")]),
            (D1, t(12, 0), "Expanding CAR-T Therapies Beyond Cancer & Autoimmune Diseases into Mast Cell Diseases, Allergy & Immunology", "In Vivo Bootcamp", [("Sidharth Kerkar", "Allergene AI")]),
            (D1, t(12, 0), "Bridging Regulatory & Commercial Expectations to Restructure the Pathway to Commercialization & Long-Term Follow Ups", "Building Strong Regulatory & Commercial Strategies", [("Lana Shiu", "Kite Pharma"), ("Seraphin Kuate", "Bristol Myers Squibb")]),
            (D1, t(13, 30), "Preventing Tumor Suppression: Multiplex Engineering for Durable CAR-T in GBM", "Optimizing Approaches to Prevent Downregulation", [("Aaron Edwards", "Kiragen Bio")]),
            (D1, t(13, 30), "Non-Viral ssDNA Vector Delivery Strategies to Optimize Persistence & Patient Safety", "Evaluating Vector Delivery Approaches", [("Matthias Bozza", "CPTx")]),
            (D1, t(13, 30), "Workshop B: Aligning Partnership Expectations & Facilitating Face-to-Face Interactions to Encourage Successful Collaborations", "Automated Manufacturing, Regulations & Partnering Bootcamp", [("Xiaodong Zhang", "Novartis"), ("Hong Xin", "Johnson & Johnson"), ("Nikhil Mutyal", "AstraZeneca"), ("Patrick Rivers", "AMoon Fund"), ("Koji Yasuda", "Fast Track Initiative")]),
            (D1, t(14, 0), "Panel Discussion: Selecting Gene Editing Strategies to Prevent Downregulation & Enhance Cell Therapy Outcomes", "Optimizing Approaches to Prevent Downregulation", []),
            (D1, t(14, 0), "Developing High-Quality Lentiviral Vectors to Enhance Reliable Delivery & Reduce Cost", "Evaluating Vector Delivery Approaches", [("Luke Russell", "Vyriad")]),
            (D1, t(14, 0), "Workshop B Continued", "Automated Manufacturing, Regulations & Partnering Bootcamp", [("Leonardo Ferreira", "Torpedo Bio"), ("Aaron Edwards", "Kiragen Bio")]),
            (D1, t(14, 30), "Optimizing In Vivo LNP Delivery of CAR mRNAs to Unlock Autoimmune Disease Treatments", "Evaluating Vector Delivery Approaches", [("Bill Querbes", "Aera Therapeutics")]),
            (D1, t(15, 30), "C-Level Think Tank: Scale Readiness Across Modalities", "Invite Only Session", [("Daniel Shelly", "PolTREG")]),
            (D1, t(17, 30), "CAR-TCR Connect", "Networking Reception", []),
            (D2, t(8, 10), "Program Directors' Welcome Address", "Plenary", [("Lauren Gollop", "")]),
            (D2, t(8, 15), "Chair's Opening Remarks", "Plenary", [("Vicki Plaks", "Johnson & Johnson")]),
            (D2, t(8, 20), "Industry Leader's Fireside Chat: Evaluating the CAR & TCR Therapeutic & Commercial Landscape to Propel Advanced Cell Therapy Innovation, Expand Treatment Options & Ensure Positive Commercial Outcomes", "Plenary", [("Vicki Plaks", "Johnson & Johnson"), ("Emad Abdelnaby", "Legend Biotech"), ("Serena De Vita", "AstraZeneca")]),
            (D2, t(8, 55), "Delivering Commercially-Ready Cell Therapies at Scale through a Global Network of Smart Factories", "Plenary", [("Fabian Gerlinghaus", "Cellares")]),
            (D2, t(9, 25), "Proving Durable Autoimmune Responses to Expand Safety, Access & Clinical Impact", "Plenary", [("Natalie Shiff", "Fate Therapeutics")]),
            (D2, t(9, 50), "Developing the UltraCAR-T Platform to Expand Patient Access & Drive Scalable Manufacturing in Next-Generation Cell Therapy", "Plenary", [("Helen Sabzevari", "Precigen")]),
            (D2, t(11, 15), "Characterizing Next Generation CAR Designs to Overcome Solid Tumor Limitations", "Discovery & Translation Track", [("Preet M. Chaudhary", "University of Southern California")]),
            (D2, t(11, 15), "Proving Durable Autoimmune Responses Without Lymphodepletion to Expand Safety, Access & Clinical Impact", "Clinical Track", [("Daniel Nunez", "Cabaletta Bio")]),
            (D2, t(11, 15), "Optimizing Starting Materials to Enable Future Scalable Cell Therapy Production", "Early-Stage Manufacturing Track", [("Rudolph Hulspas", "Dana-Farber Cancer Institute")]),
            (D2, t(11, 15), "Enabling Effective Scale-Up to Deliver Commercialized Complex Cell Therapy Products", "Late-Stage Manufacturing Track", [("Naren Kadaba", "Kite Pharma")]),
            (D2, t(11, 40), "Accelerating CAR T-Cell Development and Manufacturing Optimization Through Integrated Analytics", "Discovery & Translation Track", [("Xiaoyu Zhang", "Agilent Technologies")]),
            (D2, t(11, 40), "Roundtable Discussion: Diversifying Autoimmune Treatments to Enhance Treatment Availability", "Clinical Track", []),
            (D2, t(11, 40), "A Novel CD3 Cell Selection Workflow Across Starting Materials", "Early-Stage Manufacturing Track", [("Amelia Hessen", "Fresenius Kabi")]),
            (D2, t(11, 40), "From Clinical Promise to Commercial Reality: Enabling Cell Therapy Commercialization at Scale", "Late-Stage Manufacturing Track", [("Francesca Vitelli", "Minaris")]),
            (D2, t(12, 10), "Engineering Gated CAR-Ts to Enhance Target Specificity & Combat the Solid Tumor Microenvironment", "Discovery & Translation Track", [("Mark Wallet", "Link Cell Therapies")]),
            (D2, t(12, 10), "Evolving CAR-T Therapies to Shift Beyond Hematological Malignancies", "Clinical Track", [("Matthias Will", "Autolus Therapeutics")]),
            (D2, t(12, 10), "How Long Is Long Enough? Rethinking mRNA for In Vivo CAR-T", "Early-Stage Manufacturing Track", [("Davide De Lucrezia", "TriLink BioTechnologies")]),
            (D2, t(12, 10), "Scaling Cell Therapies to Enable Large Scale Manufacturing & Market Readiness", "Late-Stage Manufacturing Track", [("Justin Skoble", "Caribou Biosciences")]),
            (D2, t(12, 35), "The Next Generation of Cytometry: Imaging, Standardized Spectral Analysis and Automation", "Discovery & Translation Track", [("Scott Bornheimer", "Waters")]),
            (D2, t(12, 35), "Position Reserved for Program Partner", "Clinical Track", []),
            (D2, t(12, 35), "The Evolving Role of Blood Centers in Delivering Characterized Starting Material for CGT Manufacturing", "Early-Stage Manufacturing Track", [("Kelly Anderson", "LifeSouth Community Blood Centers"), ("Felix A. Montero Julian", "Accellix"), ("Daniel Welder", "Gulf Coast Blood"), ("Nisha Durand", "Vitalant")]),
            (D2, t(12, 35), "Key Considerations in Leveraging Automation to Achieve Analytical Comparability", "Late-Stage Manufacturing Track", [("Isabel Tian", "Cellares")]),
            (D2, t(14, 5), "Next-Generation TCR Engineering: Integrating Co-Stimulation & Novel Antigen Targeting to Expand the Reach of T-Cell Therapies", "Discovery & Translation Track", [("Rachel Abbott", "Pan Cancer T")]),
            (D2, t(14, 5), "Charting Regulatory Shifts in CGT: Decisions, Innovation & What's Next", "Clinical Track", [("Sharon Anderson", "Alliance for Regenerative Medicine")]),
            (D2, t(14, 5), "Streamlining Manufacturing Strategies for Complex Allogeneic T-Cell Therapies", "Early-Stage Manufacturing Track", [("Keith Wilson", "Century Therapeutics")]),
            (D2, t(14, 5), "Evaluating Manufacturing to Balance Scientific Rigor & Commercial Scalability", "Late-Stage Manufacturing Track", [("Lavakumar Karyampudi", "Moffitt Cancer Center")]),
            (D2, t(14, 30), "Panel Discussion: Aligning Preclinical Model Selection with Regulatory Expectations to Improve Translation & Approval Confidence", "Discovery & Translation Track", [("Matthias Bozza", "CPTx"), ("Aaron Edwards", "Kiragen Bio"), ("Sidharth Kerkar", "Allergene AI")]),
            (D2, t(14, 30), "Panel Discussion: Highlighting Strategies to Streamline Regulatory Approval Across Regulatory Agencies", "Clinical Track", [("Pei Wang", "Eureka Therapeutics"), ("Daniel Passeri", "LIfT Biosciences")]),
            (D2, t(14, 30), "USP1043 Compliant GMP-Grade Cell Culture Reagent Supporting Cell-Based Immunotherapy From Bench to Bioprocess", "Early-Stage Manufacturing Track", [("Jessie H.T. Ni", "BioLegend")]),
            (D2, t(14, 30), "Scaling Cell Therapy Manufacturing by 10x: From Tech Transfer to High-Volume Readiness", "Late-Stage Manufacturing Track", [("Courtney Keiser", "ElevateBio"), ("Christopher Shumway", "ElevateBio")]),
            (D2, t(15, 0), "Outlining MHRA Cell Therapy Clinical & Manufacturing Regulations to Ensure Improved Patient Access & Outcomes", "Discovery & Translation Track", [("Kingyin Lee", "MHRA")]),
            (D2, t(15, 0), "Roundtable Discussion: Aligning Assay Strategy with Regulatory Expectations to Streamline Cell Therapy Testing", "Early-Stage Manufacturing Track", [("Samantha O'Hara", "Umoja Biopharma")]),
            (D2, t(15, 0), "Panel Discussion: Designing Commercial Manufacturing for Speed or Scale & the Regulatory Trade-Offs", "Late-Stage Manufacturing Track", [("Jose Caraballo Oramas", "Kite Pharma"), ("Justin Skoble", "Caribou Biosciences"), ("Renee Hart", "LumaCyte")]),
            (D2, t(15, 30), "IMANs as an Example of Innate Cells' Direct & Indirect Therapeutic Activity", "Discovery & Translation Track", [("Daniel Passeri", "LIfT Biosciences")]),
            (D2, t(15, 30), "Building In Vivo Clinical Success Leveraging the IIT Pathway to Accelerate Global Clinical Development", "Clinical Track", [("Yongke Zhang", "IASO Biotherapeutics")]),
            (D2, t(15, 30), "Advancing Cytotoxicity Assays to Strengthen Early CAR-T Development Decisions", "Early-Stage Manufacturing Track", []),
            (D2, t(15, 30), "Smart Design & Precision Execution for Late-Stage Allogeneic CAR-T Manufacturing", "Late-Stage Manufacturing Track", [("Chupei Zhang", "Allotera Therapeutics")]),
            (D2, t(17, 0), "Reserved for Lonza", "Plenary", [("Davide Zocco", "Lonza")]),
            (D2, t(17, 30), "Establishing Durable Impact on Tumors through Phase 1 Evidence: Bench to Bedside & Back", "Plenary", [("Bruce Levine", "University of Pennsylvania")]),
            (D2, t(17, 55), "Advancing Autologous Therapies to Enable Durable Solid Tumor Therapy", "Plenary", [("Pei Wang", "Eureka Therapeutics")]),
            (D2, t(18, 20), "11th Annual Cell-ebrations & Poster Session", "The Pavillion", []),
            (D3, t(8, 25), "Chair's Opening Remarks", "Plenary", []),
            (D3, t(9, 0), "Investors Panel Discussion: Shaping Cell Therapy Funding & Partnerships with Investor Perspectives", "Plenary", [("Ilya Yasny", "LanceBio Ventures"), ("Patrick Rivers", "AMoon Fund"), ("Randy Berholtz", "Mesa Verde Venture Partners"), ("Koji Yasuda", "Fast Track Initiative")]),
            (D3, t(9, 45), "Introducing Eveo Cell Therapy Manufacturing Platform: Unlocking the Industrialization of Cell Therapy Production", "Plenary", [("Pierre Springuel", "Sartorius")]),
            (D3, t(10, 15), "Empowering Patients. Delivering Access.", "Plenary", [("George Eastwood", "Emily Whitehead Foundation")]),
            (D3, t(11, 30), "Engineering Cellular Shielding to Reduce Allogeneic Rejection", "Discovery & Translation Track", [("Tom Wickham", "GentiBio")]),
            (D3, t(11, 30), "Demonstrating Clinical Success in CD19/CD20 Dual CAR Innovation to Enhance Clinical Impact", "Clinical Track", [("Shawn He", "JW Therapeutics")]),
            (D3, t(11, 30), "Partnering for Scale: Maximizing Allogeneic Cell Therapy Success using the Right CDMO", "Early-Stage Manufacturing Track", [("James Adams", "Tr1X Bio")]),
            (D3, t(11, 30), "Defining Phase-Appropriate Control Strategies for Diverse Cell Therapy Products", "Late-Stage Manufacturing Track", [("Stephan Krause", "Bristol Myers Squibb")]),
            (D3, t(11, 55), "Enhancing TCR Design to Advance Targeted Delivery & Clinical Impact", "Discovery & Translation Track", [("Luke Pase", "Anocca")]),
            (D3, t(11, 55), "Biomarkers Associated with Clinical Outcomes of CAR-T Cell Therapies for Relapse/Refractory Multiple Myeloma", "Clinical Track", [("Vicki Plaks", "Johnson & Johnson")]),
            (D3, t(11, 55), "Transitioning Between Viral & Non-Viral Platforms to Enhance CAR-T Safety & Durability", "Early-Stage Manufacturing Track", [("Steven Feldman", "Stanford Medicine")]),
            (D3, t(11, 55), "Refining CQAs to Balance Development Flexibility & Patient Safety", "Late-Stage Manufacturing Track", [("Emily Lowe", "AstraZeneca")]),
            (D3, t(12, 20), "Reserved for Promega Corporation", "Discovery & Translation Track", [("", "Promega")]),
            (D3, t(12, 20), "Setting the Benchmark for Efficacy & Safety in CAR-T Therapy", "Clinical Track", []),
            (D3, t(12, 25), "Simplifying Cell Selection and Activation: A New Path to Greater Manufacturing Flexibility with BubbleGen", "Early-Stage Manufacturing Track", [("Michael Godeny", "Bracco")]),
            (D3, t(12, 30), "Engineering Next Generation NK-Cell Therapies to Enhance Persistence in Solid Tumors", "Discovery & Translation Track", [("Raphaël G. Ognar", "NKILT Therapeutics")]),
            (D3, t(12, 30), "Characterizing CAR Function Across Disease Indications to Enable Clinical Expansion", "Early-Stage Manufacturing Track", [("Samantha O'Hara", "Umoja Biopharma")]),
            (D3, t(12, 30), "Designing Process Characterization Strategies to Turn Process Knowledge into Predictable Product Success", "Late-Stage Manufacturing Track", [("E-Ching Ong", "Lyell Immunopharma")]),
            (D3, t(14, 10), "Innovating Tumor Homing, Scalable Allogeneic Therapy Design to Unlock Cost Effective Cell Therapy Access", "Discovery & Translation Track", [("Tim Gallager", "PhosphoGam")]),
            (D3, t(14, 10), "Clinical Activity of IMA203CD8, a PRAME-Directed TCR T-Cell Therapy in Solid Tumors", "Clinical Track", [("Karine Pozo", "Immatics")]),
            (D3, t(14, 10), "Building Quality into iPSCs Early to Minimize Testing, Improve Reproducibility & Accelerate Commercialization", "Early-Stage Manufacturing Track", [("Damien Zanker", "Cartherics")]),
            (D3, t(14, 10), "Defining Potency in CAR-T & Cell Therapies to Align with FDA Expectations", "Late-Stage Manufacturing Track", [("Yu Qian", "Novartis")]),
            (D3, t(14, 35), "Roundtable Discussion: Navigating Regulatory Expectations for Next-Generation Cell Therapies to Accelerate Translation to the Clinic", "Discovery & Translation Track", []),
            (D3, t(14, 35), "Roundtable Discussion: Utilizing Biomarkers to Guide Patient Selection, Predict Responses & Improve Safety", "Clinical Track", [("Kanya Rajangam", "Senti Biosciences")]),
            (D3, t(14, 35), "Panel Discussion: Designing Early Manufacturing Processes with Long-term Strategic Alignment to Ensure Success in Phase 1 & Beyond", "Early-Stage Manufacturing Track", [("Steven Feldman", "Stanford Medicine"), ("Keith Wilson", "Century Therapeutics")]),
            (D3, t(14, 35), "Roundtable Discussion: Accelerating Vein-to-Vein Time through Innovative QC Testing Strategies", "Late-Stage Manufacturing Track", [("Vaishali Shulka", "Eli Lilly & Co.")]),
            (D3, t(15, 10), "Scaling Manufacturing, Not Facilities: Demonstrating the potential of a microfluidic-powered Cell Factory to make CAR-T better, faster, cheaper!", "Early-Stage Manufacturing Track", [("Thomas Denèfle", "Astraveus")]),
            (D3, t(15, 20), "Q-CAR: An In Vivo CAR-T Targeting IgE B-Cells as a Treatment for Severe Allergies", "Discovery & Translation Track", [("Shon Green", "Zelig Therapeutics")]),
            (D3, t(15, 20), "First In Class Logic Gated Allogeneic CAR Cell Therapy with RMAT Designation Phase 1 Data", "Clinical Track", [("Kanya Rajangam", "Senti Biosciences")]),
            (D3, t(15, 20), "Panel Discussion: Highlighting Differences in US & China Manufacturing Processes to Shift for Scalability", "Early-Stage Manufacturing Track", [("Yu (Clay) Cao", "Stealth Biotech"), ("Huiyi Zhu", "ProBio")]),
            (D3, t(15, 20), "Applying Proven Manufacturing Strategies to De-Risk Scale-Up & Accelerate Commercial Delivery", "Late-Stage Manufacturing Track", [("Yan Li", "Cabaletta Bio")]),
            (D3, t(16, 30), "Highlighting Overland Therapeutics' GPRC5D/BCMA Dual CAR-T Clinical Data", "Plenary", [("Ed Zhang", "Overland Therapeutics")]),
            (D3, t(16, 55), "CAR & TCR Therapies: A Landscape Review", "Plenary", [("Safia Abdi", "Beacon")]),
            (D3, t(17, 20), "Chair's Closing Remarks", "Plenary", []),
        ]

        sessions = []
        speakers_seen = {}
        for day, start_time, title, location, speaker_list in raw:
            speakers_json = [{"name": n, "affiliation": co} for n, co in speaker_list if n]
            sessions.append(Session(
                conference=conference, title=title, session_type=classify_session_type(title),
                day=day, start_time=start_time, location=location, speakers=speakers_json,
                source_sheet="Event Guide PDF (manual transcription)",
            ))
            for n, co in speaker_list:
                if n and n not in speakers_seen:
                    speakers_seen[n] = co

        Session.objects.bulk_create(sessions)
        speaker_records = [Speaker(conference=conference, name=n, company_name=co) for n, co in speakers_seen.items()]
        Speaker.objects.bulk_create(speaker_records)
        return len(sessions), len(speaker_records)
