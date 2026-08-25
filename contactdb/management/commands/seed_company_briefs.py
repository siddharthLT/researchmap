from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from companymap.models import Company
from contactdb.models import CompanyBrief

BRIEFS = {
    "Ascendia Pharmaceutical Solutions": {
        "legal_name": "Ascendia Pharmaceutical Solutions",
        "founded": "2012",
        "headquarters": "North Brunswick, New Jersey, US",
        "employee_count": "51-200",
        "ownership": "Privately held; $2.5M seed round (2025), up to $10M cumulative funding reported",
        "nature": (
            "Specialty CDMO focused on formulation development and manufacturing for pharma and "
            "biotech companies, with advanced dosage-form capabilities (solubility enhancement, "
            "controlled release, complex injectable formulation)."
        ),
        "service_model": (
            "Outsourced drug product formulation and dosage-form development for preclinical through "
            "early Phase 2 programs. Positioned strictly as a CDMO, not a platform/software vendor."
        ),
        "client_profile": (
            "Small to mid-sized biotech and specialty pharma companies needing solubility enhancement, "
            "controlled-release, or complex injectable formulation support."
        ),
        "modality_focus": "Small Molecules, Biologics",
        "therapeutic_focus": (
            "Broad, skewing toward CNS and oncology. Lead pipeline asset ASD-001 (CNS, preclinical)."
        ),
        "trial_phase_preference": (
            "Preclinical, Phase 1, and early Phase 2. No evidence of late-phase or commercial-scale "
            "manufacturing focus."
        ),
        "decision_makers": [
            {"name": "Jingjun \"Jim\" Huang, Ph.D.", "title": "Founder/CEO"},
            {"name": "Todd Daviau", "title": "Interim CEO"},
            {"name": "Robert Bloder", "title": "Chief Business Officer"},
            {"name": "Troy Harmon", "title": "SVP Business Development"},
            {"name": "Julie Hilton", "title": "Senior Director, Business Development"},
            {"name": "Danni Song", "title": "Associate Director, Business Development"},
            {"name": "Rhonda Baker", "title": "Director, Business Development"},
            {"name": "Kevin Wilson", "title": "VP Sales"},
            {"name": "Jared Hahn", "title": "Senior Director, Business Development"},
            {"name": "Steven Scheyer", "title": "President & CEO"},
        ],
        "latest_signals_period": "May-Aug 2026",
        "latest_signals": [
            "Active hiring and narrative expansion following the 2025 seed round.",
            "No major partnership, clinical/commercial launch, or M&A activity in the past 3 months; growth signals moderate.",
            "Lead asset ASD-001 remains in CNS preclinical stage.",
            "Positioning emphasizes digital-transformation readiness and openness to new commercial tools.",
        ],
        "sources": [
            "ascendiacdmo.com",
            "synapse.patsnap.com (BD opportunity scan, 2026)",
            "CPHI Online",
            "LinkedIn leadership profiles",
        ],
        "source_document": "Ascendia_Pharmaceuticals_Company_Report.pdf",
    },
    "BAP Pharma": {
        "legal_name": "BAP Pharma Ltd",
        "founded": "2011",
        "headquarters": "Marlow, England, UK",
        "employee_count": "~78 (2024)",
        "ownership": "Privately held (Founder: Dr. Bashir Parkar)",
        "global_presence": "Offices in UK, US, Germany; operations in 100+ countries",
        "nature": (
            "Specialized life sciences service provider covering clinical trial supplies, comparator "
            "sourcing, medicines access, and secondary packaging -- positioned as the bridge between "
            "biopharma innovation and patient access."
        ),
        "service_model": (
            "Clinical trial supply (sourcing, logistics, secondary packaging/labeling), managed access, "
            "and expanded access programs."
        ),
        "client_profile": (
            "Mid-to-large biopharma running international Phase II/III trials; sponsors needing global "
            "comparator sourcing/managed access; CDMOs/CROs on complex multi-country studies; rare "
            "disease, immunology, oncology, and cardiovascular access programs."
        ),
        "modality_focus": "Small Molecules, Biologics",
        "therapeutic_focus": (
            "Immuno-oncology (exclusive global access partner for Agenus' botensilimab + balstilimab, "
            "2026), rare diseases, cardiovascular, immunology, Ehlers-Danlos syndrome."
        ),
        "trial_phase_preference": (
            "Phase II/III -- large-scale comparator sourcing and multi-country logistics. Demonstrated "
            "rapid trial rescue (Turkey cardiovascular restart, <7 days across 17 sites)."
        ),
        "decision_makers": [
            {"name": "Dr. Bashir Parkar", "title": "Founder and Owner", "note": "Strategic vision, transformation driver"},
            {"name": "Andrew Rawson", "title": "CCO", "note": "Commercial lead"},
            {"name": "Rebecca Bibby", "title": "Group Director, Medicines Access & UK GM"},
            {"name": "Mark Eisenberg", "title": "Director of Business Development, North America"},
        ],
        "latest_signals_period": "May-Aug 2026",
        "latest_signals": [
            "Named exclusive global access partner for Agenus' botensilimab + balstilimab immuno-oncology programs (April 2026).",
            "Continued US, Germany, and EU expansion; new US HQ opened 2024.",
            "2026 MSDUK High Growth Business of the Year award.",
            "No evidence of running proprietary asset trials -- pure service/logistics play.",
        ],
        "opportunity_assessment": (
            "HIGH -- fits the ideal client profile for advanced clinical trial services and medicines "
            "access; commercially active, internationally scaled, strong growth signals for CDMO/CRO-"
            "buyer BD targeting."
        ),
        "sources": [
            "bappharma.com",
            "MarketScreener (Agenus partnership)",
            "BAP Pharma case studies/events page",
            "LinkedIn leadership profiles",
        ],
        "source_document": "BAP_Pharma_Company_Report.pdf",
    },
    "Made Scientific": {
        "legal_name": "Made Scientific (formerly BioCentriq)",
        "founded": "2018",
        "headquarters": "Princeton, New Jersey (moved from Newark in 2024)",
        "ownership": "Acquired by GC Cell (Green Cross), 2022",
        "nature": (
            "US-based specialist cell & gene therapy CDMO, rebranded from BioCentriq to Made Scientific."
        ),
        "service_model": (
            "Process development/scale-up (autologous and allogeneic), GMP manufacturing (Phase I-III "
            "and commercial), analytical development/product release, regulatory support and "
            "technology transfer."
        ),
        "client_profile": (
            "Early- to mid-stage biotechs developing novel cell/gene therapy assets; larger pharma and "
            "academic centers needing advanced manufacturing from clinical to commercial scale."
        ),
        "modality_focus": "Cell Therapy, Gene Therapy",
        "therapeutic_focus": "Agnostic -- oncology, immunology, regenerative medicine, rare diseases, client-driven.",
        "trial_phase_preference": (
            "Full clinical-to-commercial continuum; especially active in first-in-human and Phase I/II."
        ),
        "decision_makers": [
            {"name": "Raghu Malapaka", "title": "Sr. Director, Global BD, Cell and Gene Therapy", "note": "San Francisco"},
            {"name": "Joe Sinclair", "title": "VP & Head of Commercial", "note": "Boston"},
            {"name": "Kyle Bullock", "title": "Director, Commercial Development", "note": "Princeton"},
            {"name": "Sun Bullins", "title": "VP & Head of Technical Operations", "note": "San Diego"},
            {"name": "Chathuranga Silva", "title": "Executive Director, Business Development", "note": "New York"},
            {"name": "Adam Haskett", "title": "Head of Strategic Alliances", "note": "California"},
            {"name": "Dustin Campbell", "title": "Sr. Director, Commercial Ops"},
        ],
        "latest_signals_period": "Last 3 months (2026)",
        "latest_signals": [
            "Multiple new partnerships for T-cell, iPSC, and mitochondrial therapies (Pluristyx, RoosterBio, Cellergy, Syenex, Telos Biotech).",
            "Selected manufacturer for Columbia University's ARPA-H-funded NOVAKnee living-implant program.",
            "Exclusive design partner with Streamline Bio for AI-driven robotic GMP manufacturing.",
            "New 60,000 sq ft Princeton HQ/facility now operational for clinical and GMP work.",
            "No new large funding rounds reported, but continued facility and team expansion.",
        ],
        "opportunity_assessment": (
            "Commercial and operational complexity high; strong digital-transformation readiness "
            "(early automation/digital-GMP adopter)."
        ),
        "summary": (
            "High-growth, technology-forward cell/gene therapy CDMO well integrated into the US "
            "advanced-therapies ecosystem, with decision makers across commercial, operational, and "
            "strategic-alliances functions."
        ),
        "sources": [
            "biocentriq.com (non-confidential overview, 2024)",
            "madescientific.com/news",
            "builtinnyc.com/company/biocentriq",
            "pharmasource.global (rebrand announcement)",
        ],
        "source_document": "BioCentriq__Made_Scientific__Company_Brief___2026.pdf",
    },
    "Freyr Solutions": {
        "legal_name": "Freyr Solutions",
        "founded": "2011",
        "headquarters": "Princeton, New Jersey, US",
        "employee_count": "2,053 (2026)",
        "ownership": "Private, self-funded",
        "global_presence": "US HQ; operations across North America, Europe, Asia, and emerging markets",
        "nature": (
            "Global regulatory solutions and RegTech provider at the intersection of technology and "
            "compliance for life sciences -- one of the world's largest regulatory affairs, "
            "pharmacovigilance, and quality-management service providers."
        ),
        "service_model": (
            "End-to-end regulatory strategy, submissions (including eCTD), nonclinical support, "
            "pharmacovigilance/safety monitoring, AI-driven RegTech (compliance/submissions/labeling), "
            "quality and GxP support."
        ),
        "client_profile": (
            "Small/mid biopharma needing regulatory strategy; large pharma and top-10 global life "
            "sciences companies outsourcing compliance and global filings; medical device, generics, "
            "and biosimilars companies; CROs."
        ),
        "modality_focus": "Small Molecules, Biologics",
        "therapeutic_focus": (
            "Therapeutic-area agnostic, with expertise across oncology, CNS, inflammation/autoimmune, "
            "metabolism, infectious disease, cardiovascular, and wound management."
        ),
        "trial_phase_preference": "Not phase-specific -- discovery through post-approval/marketed-product support.",
        "decision_makers": [
            {"name": "Sudhir Kandarth", "title": "Chief Revenue Officer & President, Freyr Digital"},
            {"name": "Prashil Panchal", "title": "Head, Strategy & Business Development"},
            {"name": "Gmak Gopi", "title": "VP, Strategy Business Development"},
            {"name": "Vinupama Gudela", "title": "Manager, BD, Regulatory Affairs ROW"},
            {"name": "Adnan Subhani", "title": "Sr VP, Head Global Strategic Accounts"},
        ],
        "latest_signals_period": "Last 3 months (2026)",
        "latest_signals": [
            "Renewed NVIDIA Preferred Cloud Partner - Compute status for AI regulatory workflows (Freyr Digital, July 2026).",
            "Secured a regulatory-services contract with a $600M+ South Korean pharma for US eCTD submissions (April 2026).",
            "Recognized as a global leader in life sciences regulatory/medical-affairs service delivery by Everest Group PEAK Matrix (June 2026).",
            "Launched periodic regulatory digests covering EU DPP, California Prop 65, and UK/EU regulation changes (July 2026).",
        ],
        "summary": (
            "Large, digitally progressive global regulatory partner, fully modality- and therapeutic-"
            "agnostic, serving top-tier and mid-market life sciences firms. Primary decision makers sit "
            "at CRO, Strategy/BD VP, and Global Account VP levels."
        ),
        "sources": [
            "freyrsolutions.com/about-us",
            "pitchbook.com",
            "freyrsolutions.com/press-releases",
            "linkedin.com/company/freyrsolutions",
            "freyrtech.ai/news",
        ],
        "source_document": "Freyr_Solutions_Company_Profile_Report.pdf",
    },
    "Wuxi AppTec": {
        "legal_name": "WuXi AppTec Co., Ltd.",
        "founded": "2000",
        "headquarters": "Shanghai, China",
        "employee_count": "33,834 globally (2026)",
        "ownership": "Publicly traded",
        "nature": (
            "Global Contract Research, Development & Manufacturing Organization (CRDMO) covering the "
            "full biopharma product life cycle, from discovery through commercial manufacturing."
        ),
        "service_model": (
            "Integrated drug discovery, preclinical development, clinical trials, manufacturing, and "
            "commercial operations. Direct-to-Biology (D2B) and DNA-Encoded Library (DEL) platforms "
            "accelerate early candidate discovery."
        ),
        "client_profile": (
            "Biotech and pharma innovators from early-stage startups to major pharmaceutical companies; "
            "~70% of orders originate overseas, notably the US and Europe."
        ),
        "modality_focus": "Peptides, Small Molecules, Biologics, Cell Therapy, Gene Therapy, ADCs",
        "therapeutic_focus": (
            "CNS (neurology, oligonucleotide therapeutics), oncology (stapled peptides, ADCs, "
            "conjugated therapeutics), and rare/genetic disorders."
        ),
        "trial_phase_preference": (
            "Discovery through IND and clinical supply, with particular strength in early "
            "(preclinical/IND) and mid-to-late-phase manufacturing scale-up."
        ),
        "decision_makers": [
            {"name": "Ge Li, Ph.D.", "title": "Chairman & CEO"},
            {"name": "Minzhang Chen, Ph.D.", "title": "Co-CEO"},
            {"name": "Zhigang Chen", "title": "SVP & Chief Digital Officer"},
            {"name": "Cijian Feng", "title": "Sr. Director, Corporate Development"},
            {"name": "Sukhvinder Chohan", "title": "Director, BD UK & Ireland"},
            {
                "name": "Nadeem Beg, Nikunj Parikh, Keisha Dykes, Sean Chen, Robert Cissell",
                "title": "Senior BD Directors",
                "note": "US, EU, manufacturing, preclinical/clinical, discovery, and peptide/oligonucleotide portfolios",
            },
        ],
        "latest_signals_period": "May-Aug 2026",
        "latest_signals": [
            "Q2 2026 revenue RMB 28.90B (+38.9% YoY); FY26 guidance raised to RMB 58.5-60.5B (+35-39% YoY).",
            "Order backlog up 25%; capex guidance raised to RMB 7.5-8.5B, Changzhou site accelerated.",
            "TIDES (peptides & oligonucleotides) segment revenue RMB 7.26B, up 44% YoY.",
            "ADC business expanded via TOT BIOPHARM acquisition and a new 3-year R&D/service agreement.",
            "Share buyback program (up to 10% of shares) initiated; named again to FTSE4Good and Dow Jones Sustainability World Index.",
        ],
        "opportunity_assessment": (
            "High opportunity -- commercial complexity, active global expansion, leadership capable of "
            "transformation, strong alignment with digital/analytical/advanced-modality coverage."
        ),
        "sources": [
            "wuxiapptec.com/about",
            "nasdaq.com press release (H1 2026 results)",
            "wuxiapptec.com/about/leadership",
            "eu.36kr.com",
            "news.futunn.com",
        ],
        "source_document": "WuXi_AppTec_Company_Report__2026.pdf",
    },
    "WuXi Biologics": {
        "legal_name": "WuXi Biologics (Cayman) Inc.",
        "founded": "2010",
        "headquarters": "Wuxi, Jiangsu, China",
        "employee_count": "13,000+ worldwide",
        "ownership": "Publicly listed, Hong Kong Stock Exchange (2269.HK)",
        "nature": (
            "Leading global CRDMO specializing in end-to-end biologics discovery, development, and "
            "manufacturing."
        ),
        "service_model": "Biologics R&D, process development, IND filings, GMP manufacturing, commercialization.",
        "client_profile": (
            ">810 global biopharma clients including 15 of the top 20 global pharma companies plus "
            "emerging biotechs; most new projects originate from North America and Europe."
        ),
        "modality_focus": "Biologics, mAbs, ADCs",
        "therapeutic_focus": (
            "No exclusive focus given its CDMO/CRDMO positioning; recent strength in oncology (PD-L1 "
            "immunotherapies, ADCs for solid/hematologic tumors) and autoimmune disease."
        ),
        "trial_phase_preference": (
            "Full spectrum -- discovery/IND-enabling (68 INDs filed H1 2026, targeting 300/year by "
            "2027) through late-stage/commercial (78 Phase III programs, 28 commercial manufacturing "
            "projects as of June 2026)."
        ),
        "decision_makers": [
            {"name": "Kevin Liu", "title": "Director, CRO Business Development NA-West", "note": "Antibody/Protein Engineering, Analytics; CA"},
            {"name": "Hidenori Meiseki", "title": "Senior Director, Head of APAC BD", "note": "Tokyo"},
            {"name": "Chintan Kapadia", "title": "Senior BD Manager, CRO Service", "note": "Formulations, RNA Medicines; NY"},
            {"name": "Mo Chen", "title": "Sr. Director, BD, Research Services", "note": "San Francisco"},
            {"name": "Haodi Dong", "title": "VP, BD & Alliance Management, North America", "note": "Cambridge, MA"},
            {"name": "Vincent Hua", "title": "Associate Director, BD", "note": "China"},
        ],
        "latest_signals_period": "June-Aug 2026",
        "latest_signals": [
            "123 new organic integrated projects added in H1 2026 (+43% YoY), plus 46 more from the BioDlink/WuXi XDC acquisition.",
            "70%+ of H1 projects and 50%+ overall are complex biologics (bi-/multi-specifics, ADCs).",
            "16 new 'Win-the-Molecule' deals in H1 2026, including 4 Phase III and 1 commercial.",
            "US$400M share repurchase announced (May 2026).",
            "China facilities passed FDA and EMA inspections, supporting autoimmune and oncology biologics commercialization.",
        ],
        "opportunity_assessment": "Buy/strong-performance ratings from multiple financial analysts noted in August 2026 reporting.",
        "sources": [
            "WuXi Biologics H1 2026 Financial Release",
            "SCMP Company News",
            "WuXi Bio 2026 Earnings Deck",
            "wuxibiologics.com",
        ],
        "source_document": "WuXi_Biologics_Company_Profile_Report__2026.pdf",
    },
}


class Command(BaseCommand):
    help = "Seed CompanyBrief records from researched Biolens PDF company reports."

    @transaction.atomic
    def handle(self, *args, **options):
        created = 0
        updated = 0
        for company_name, fields in BRIEFS.items():
            try:
                company = Company.objects.get(name=company_name)
            except Company.DoesNotExist:
                raise CommandError(f"Company not found: {company_name!r}")

            brief, was_created = CompanyBrief.objects.update_or_create(
                company=company, defaults=fields
            )
            if was_created:
                created += 1
            else:
                updated += 1
            self.stdout.write(f"{'Created' if was_created else 'Updated'} brief for {company_name}")

        self.stdout.write(self.style.SUCCESS(f"Done. Created {created}, updated {updated}."))
