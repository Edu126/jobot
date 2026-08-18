"""Canonical structured-resume schema. All templates consume this shape;
the tailor LLM produces it. Kept as a plain TypedDict rather than a
dataclass so JSON round-trips are trivial and legacy code that inspects
dict.get(...) still works.

None fields are optional. Empty lists mean the section is absent.
"""
from __future__ import annotations

from typing import TypedDict


class Contact(TypedDict, total=False):
    name: str
    email: str
    phone: str
    location: str
    linkedin: str
    website: str


class ExperienceEntry(TypedDict, total=False):
    title: str
    company: str
    location: str
    start: str        # e.g. "Jan 2022"
    end: str          # e.g. "Present" or "Dec 2024"
    bullets: list[str]


class EducationEntry(TypedDict, total=False):
    degree: str
    school: str
    location: str
    year: str         # e.g. "2019" or "2017 – 2019"
    notes: str        # honors, GPA, coursework highlights


class CertificationEntry(TypedDict, total=False):
    name: str
    issuer: str
    year: str


class ProjectEntry(TypedDict, total=False):
    name: str
    description: str
    bullets: list[str]
    url: str


class StructuredResume(TypedDict, total=False):
    contact: Contact
    summary: str                        # prose paragraph, not a list
    experience: list[ExperienceEntry]
    education: list[EducationEntry]
    skills: list[str]                   # flat list, comma-joined by templates
    certifications: list[CertificationEntry]
    projects: list[ProjectEntry]


SAMPLE: StructuredResume = {
    "contact": {
        "name": "Mehran Ahmadi",
        "email": "mehran.ahmadi@example.com",
        "phone": "+1 613 555 0142",
        "location": "Ottawa, Ontario, Canada",
        "linkedin": "linkedin.com/in/mehranahmadi",
    },
    "summary": (
        "BIM Coordinator with 6 years bridging design intent and constructability on "
        "mid-rise commercial and institutional projects. Fluent in Revit + Navisworks; "
        "run clash-detection cycles that have cut RFI volume 30–40% on last three builds. "
        "Comfortable owning the model across MEP/Arch/Struct trades and driving weekly "
        "coordination meetings with GCs and subs."
    ),
    "experience": [
        {
            "title": "Senior BIM Coordinator",
            "company": "Doran Contractors",
            "location": "Ottawa, ON",
            "start": "Mar 2022",
            "end": "Present",
            "bullets": [
                "Led BIM coordination on 4-storey mixed-use ($42M), running weekly clash sessions across 7 trades and closing 380+ conflicts before construction.",
                "Standardized federated-model workflow in Navisworks; reduced RFI count 38% vs prior project of similar scope.",
                "Trained 3 junior modelers on Revit family creation and view templates; team now self-serves 90% of sheet setup.",
                "Piloted 4D sequencing for structural erection — visualization used in owner review, credited with catching a 2-week logistics gap.",
            ],
        },
        {
            "title": "BIM Modeler",
            "company": "Adjeleian Allen Rubeli",
            "location": "Ottawa, ON",
            "start": "Aug 2019",
            "end": "Feb 2022",
            "bullets": [
                "Produced construction-ready Revit models for 15+ institutional projects (schools, community centres, one hospital wing).",
                "Owned MEP-Struct clash resolution on a $28M community centre; delivered clean federated model 2 weeks ahead of coordination deadline.",
                "Built firm-standard Revit template + shared parameter file — adopted across office, cut model-setup time from 6h to 1h.",
            ],
        },
    ],
    "education": [
        {
            "degree": "Master of Architecture",
            "school": "Carleton University",
            "location": "Ottawa, ON",
            "year": "2019",
        },
        {
            "degree": "BEng, Civil Engineering",
            "school": "Sharif University of Technology",
            "location": "Tehran, Iran",
            "year": "2016",
        },
    ],
    "skills": [
        "Revit", "Navisworks", "AutoCAD", "Dynamo",
        "BIM 360 / ACC", "Bluebeam", "Rhino + Grasshopper",
        "MS Project", "Clash detection", "4D sequencing",
        "IFC coordination", "OAC / GC meetings",
    ],
    "certifications": [
        {"name": "Autodesk Certified Professional — Revit Architecture", "issuer": "Autodesk", "year": "2023"},
        {"name": "LEED Green Associate", "issuer": "USGBC", "year": "2021"},
    ],
    "projects": [],
}
