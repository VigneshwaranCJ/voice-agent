"""Seed reference data + two FICTIONAL demo businesses (development only).

Run: uv run python -m app.seed      (also runs automatically on startup when SEED_DEMO_DATA=true and DB is empty)
Credentials come from SEED_* env vars (see .env.example).
"""

import asyncio
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.business_data import add_slots
from app.core.database import SessionLocal, create_all
from app.industries.healthcare.models import Department, Doctor
from app.industries.real_estate.models import Property, SalesExecutive
from app.industries.registry import get_industry
from app.knowledge.ingest import index_document
from app.models import (
    Agent, AgentConfiguration, BusinessProfile, KnowledgeDocument, Role, SupportedLanguage, Tenant, User,
)
from app.security.crypto import hash_password

LANGS = [("en-IN", "English"), ("ta-IN", "Tamil"), ("hi-IN", "Hindi"), ("te-IN", "Telugu"), ("kn-IN", "Kannada"),
         ("ml-IN", "Malayalam"), ("bn-IN", "Bengali"), ("mr-IN", "Marathi"), ("gu-IN", "Gujarati"),
         ("pa-IN", "Punjabi"), ("od-IN", "Odia")]
ROLES = [("platform_admin", "Manages all tenants"), ("tenant_admin", "Manages one business"),
         ("tenant_agent", "Views calls and data for one business")]

PERSONALITY = ("Gentle, warm, calm and patient. Professional but friendly, like an experienced customer-care "
               "executive who genuinely wants to help. Empathetic when the caller is worried or frustrated.")

RE_FAQ = """Booking and payments
A booking amount of 2 lakh rupees reserves a unit. The balance follows the construction-linked payment plan.

Home loans
We have tie-ups with SBI, HDFC and ICICI home loans. Our team helps with documentation at no extra cost.

RERA
All our ongoing projects are registered with TNRERA. Registration numbers are shared during the site visit.

Site visits
Site visits are available every day from 9 AM to 6 PM, including Sundays. Free pickup within city limits.

Cancellation
Cancellation within 30 days of booking: full refund minus 25,000 rupees processing fee."""

HOSPITAL_FAQ = """Visiting hours
General wards: 4 PM to 7 PM daily. ICU: one visitor at a time, 11 AM to 12 noon and 5 PM to 6 PM.

Emergency
The Emergency department is open 24 hours on the ground floor, Block A. Ambulance: call 108 or the hospital emergency line.

Insurance and cashless
Cashless treatment with Star Health, HDFC Ergo, ICICI Lombard and CGHS. Bring your insurance card and photo ID.

Reports
Lab reports are available on the patient portal within 24 hours, or at the Block B report counter from 8 AM to 8 PM.

Parking
Visitor parking is in the basement of Block B. The first 2 hours are free.

Consultation
Please arrive 15 minutes before your appointment with any previous prescriptions and reports."""


async def _ensure_reference(db: AsyncSession) -> None:
    for code, name in LANGS:
        if not await db.get(SupportedLanguage, code):
            db.add(SupportedLanguage(code=code, name=name))
    for name, desc in ROLES:
        if not (await db.execute(select(Role).where(Role.name == name))).scalar_one_or_none():
            db.add(Role(name=name, description=desc))
    await db.flush()


async def _tenant(db: AsyncSession, *, name: str, slug: str, industry: str, profile: dict, admin_email: str,
                  agent_name: str, persona: str, knowledge: str) -> tuple[Tenant, Agent]:
    t = Tenant(name=name, slug=slug, industry=industry, settings={"recording_enabled": False, "retention_days": 180})
    db.add(t)
    await db.flush()
    db.add(BusinessProfile(tenant_id=t.id, display_name=name, **profile))
    db.add(User(tenant_id=t.id, email=admin_email, full_name=f"{name} Admin", role="tenant_admin",
                password_hash=hash_password(os.getenv("SEED_TENANT_PASSWORD", "ChangeMe-Tenant-123"))))
    await db.flush()
    a = Agent(tenant_id=t.id, name=agent_name, industry=industry, default_language="en-IN",
              languages=["en-IN", "ta-IN"], public_widget_enabled=True)
    db.add(a)
    await db.flush()
    db.add(AgentConfiguration(tenant_id=t.id, agent_id=a.id, version=1, persona_name=persona, personality=PERSONALITY,
                              enabled_tools=get_industry(industry).default_tools))
    doc = KnowledgeDocument(tenant_id=t.id, agent_id=None, title=f"{name} FAQ", source_type="faq", raw_text=knowledge)
    db.add(doc)
    await db.flush()
    await index_document(db, doc)
    return t, a


async def seed(db: AsyncSession) -> bool:
    await _ensure_reference(db)
    if (await db.execute(select(Tenant).limit(1))).first():
        await db.commit()
        return False

    db.add(User(tenant_id=None, email=os.getenv("SEED_ADMIN_EMAIL", "admin@platform.local"), full_name="Platform Admin",
                role="platform_admin", password_hash=hash_password(os.getenv("SEED_ADMIN_PASSWORD", "ChangeMe-Admin-123"))))

    # --- Real estate (fictional) ---
    t, _ = await _tenant(
        db, name="Sunrise Realty", slug="sunrise-realty", industry="real_estate", admin_email="admin@sunrise.local",
        agent_name="Sunrise Property Desk", persona="Kavya", knowledge=RE_FAQ,
        profile=dict(description="Residential developer in Coimbatore and Chennai.", phone="0422 400 1234",
                     operating_hours={"Mon-Sun": "9:00 AM - 7:00 PM"},
                     locations=[{"name": "Sales office", "address": "12 Avinashi Road, Peelamedu, Coimbatore"}],
                     services=["Apartments", "Villas", "Plots", "Home loan assistance"]))
    props = [
        ("Sunrise Meadows", "apartment", 2, "Coimbatore", "Saravanampatti", 5_200_000, 6_100_000, 1080, 14, "Dec 2027"),
        ("Sunrise Meadows", "apartment", 3, "Coimbatore", "Saravanampatti", 7_400_000, 8_300_000, 1450, 6, "Dec 2027"),
        ("Sunrise Heights", "apartment", 2, "Coimbatore", "Peelamedu", 6_800_000, 7_600_000, 1150, 3, "Ready to move"),
        ("Sunrise Heights", "apartment", 3, "Coimbatore", "Peelamedu", 9_200_000, 10_500_000, 1620, 0, "Ready to move"),
        ("Sunrise Greens Villas", "villa", 3, "Coimbatore", "Vadavalli", 11_500_000, 13_800_000, 2100, 5, "Jun 2027"),
        ("Sunrise Enclave Plots", "plot", None, "Coimbatore", "Kovaipudur", 2_400_000, 4_800_000, 1200, 22, "Immediate"),
        ("Sunrise Bayview", "apartment", 2, "Chennai", "OMR Thoraipakkam", 7_900_000, 8_900_000, 1100, 9, "Mar 2028"),
        ("Sunrise Bayview", "apartment", 3, "Chennai", "OMR Thoraipakkam", 10_900_000, 12_400_000, 1500, 4, "Mar 2028"),
    ]
    for name, ptype, bhk, city, loc, pmin, pmax, area, units, poss in props:
        db.add(Property(tenant_id=t.id, name=f"{name}{f' {bhk}BHK' if bhk else ''}", project=name, property_type=ptype,
                        bhk=bhk, city=city, locality=loc, price_min=pmin, price_max=pmax, area_sqft=area,
                        units_available=units, status="available" if units else "sold_out", possession=poss,
                        amenities=["Covered parking", "Power backup", "Gym", "Children's play area"],
                        description=f"{ptype.title()} in {loc}, {city}."))
    db.add(SalesExecutive(tenant_id=t.id, name="Arun", phone="9000000001",
                          localities=["Saravanampatti", "Peelamedu", "Kovaipudur"]))
    db.add(SalesExecutive(tenant_id=t.id, name="Divya", phone="9000000002", localities=["Vadavalli", "OMR Thoraipakkam"]))

    # --- Hospital (fictional) ---
    t2, _ = await _tenant(
        db, name="CareWell Multispeciality Hospital", slug="carewell-hospital", industry="healthcare",
        admin_email="admin@carewell.local", agent_name="CareWell Front Desk", persona="Meera", knowledge=HOSPITAL_FAQ,
        profile=dict(description="Multispeciality hospital in Chennai.", phone="044 4000 5678",
                     operating_hours={"OPD Mon-Sat": "9:00 AM - 6:00 PM", "Emergency": "24 x 7"},
                     locations=[{"name": "Main campus", "address": "45 Anna Salai, Teynampet, Chennai"}],
                     services=["Cardiology", "Orthopaedics", "Paediatrics", "General Medicine", "24x7 Emergency"],
                     escalation_contacts=[{"name": "Front desk", "phone": "044 4000 5678"},
                                          {"name": "Emergency", "phone": "044 4000 5600"}]))
    depts = {
        "Cardiology": ("Heart care, ECG, echo and cardiac consultations.", "Block A, 2nd floor"),
        "Orthopaedics": ("Bone, joint and spine care.", "Block B, 1st floor"),
        "Paediatrics": ("Child health and vaccinations.", "Block A, 1st floor"),
        "General Medicine": ("Fever, diabetes, BP and general consultations.", "Block B, ground floor"),
        "Emergency": ("24x7 emergency and trauma care.", "Block A, ground floor"),
    }
    dept_ids = {}
    for dname, (desc, loc) in depts.items():
        d = Department(tenant_id=t2.id, name=dname, description=desc, location=loc, phone="044 4000 5678")
        db.add(d)
        await db.flush()
        dept_ids[dname] = d.id
    doctors = [
        ("Dr. Ramesh Kumar", "Cardiology", "Cardiologist", "MD, DM (Cardiology)", ["en-IN", "ta-IN"], 800),
        ("Dr. Lakshmi Narayanan", "Cardiology", "Cardiologist", "MD, DNB (Cardiology)", ["en-IN", "ta-IN", "hi-IN"], 900),
        ("Dr. Suresh Babu", "Orthopaedics", "Orthopaedic Surgeon", "MS (Ortho)", ["en-IN", "ta-IN"], 700),
        ("Dr. Anitha Raj", "Paediatrics", "Paediatrician", "MD (Paediatrics)", ["en-IN", "ta-IN"], 600),
        ("Dr. Karthik Venkat", "General Medicine", "General Physician", "MD (General Medicine)", ["en-IN", "ta-IN"], 500),
    ]
    for name, dept, spec, qual, langs, fee in doctors:
        doc = Doctor(tenant_id=t2.id, name=name, department_id=dept_ids[dept], specialization=spec,
                     qualifications=qual, languages=langs, consultation_fee=fee)
        db.add(doc)
        await db.flush()
        add_slots(db, t2.id, doc.id, days=10, start_hour=10, end_hour=13, minutes=20)
    await db.commit()
    return True


async def main() -> None:
    await create_all()
    async with SessionLocal() as db:
        created = await seed(db)
    print("Seeded demo data." if created else "Database already has tenants; reference data ensured.")


if __name__ == "__main__":
    asyncio.run(main())
