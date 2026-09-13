"""Mapping from plain-language business categories to schema.org types.

Using a specific type (`Plumber`) instead of the generic `LocalBusiness` helps
AI assistants resolve the business as an entity of a known kind, which is what
lets it surface for "who does X near me" style questions. Every value here is
a real schema.org LocalBusiness subtype.
"""
from __future__ import annotations

# keyword -> schema.org type. Keys are matched as substrings of the user's
# category, longest key first, so "emergency plumber" resolves to Plumber.
CATEGORY_TO_SCHEMA: dict[str, str] = {
    # Trades and home services
    "plumb": "Plumber",
    "electric": "Electrician",
    "hvac": "HVACBusiness",
    "heating": "HVACBusiness",
    "air conditioning": "HVACBusiness",
    "roof": "RoofingContractor",
    "lock": "Locksmith",
    "paint": "HousePainter",
    "landscap": "LandscapeService",
    "lawn": "LandscapeService",
    "pest": "PestControlService",
    "clean": "ProfessionalService",
    "moving": "MovingCompany",
    "mover": "MovingCompany",
    "contractor": "GeneralContractor",
    "construction": "GeneralContractor",
    "remodel": "GeneralContractor",
    "handyman": "HomeAndConstructionBusiness",
    "garage door": "GeneralContractor",
    "window": "GeneralContractor",
    "flooring": "GeneralContractor",
    "solar": "HomeAndConstructionBusiness",
    "septic": "ProfessionalService",
    "tree": "LandscapeService",
    "pool": "ProfessionalService",
    "roofing": "RoofingContractor",
    # Health and wellness
    "dent": "Dentist",
    "orthodont": "Dentist",
    "chiroprac": "Physician",
    "physician": "Physician",
    "doctor": "Physician",
    "medical": "MedicalBusiness",
    "clinic": "MedicalClinic",
    "dermatol": "Physician",
    "optometr": "Optician",
    "veterinar": "VeterinaryCare",
    "vet ": "VeterinaryCare",
    "physical therap": "PhysicalTherapy",
    "pharmac": "Pharmacy",
    "med spa": "DaySpa",
    "medspa": "DaySpa",
    "spa": "DaySpa",
    "therap": "MedicalBusiness",
    "counsel": "MedicalBusiness",
    "psycholog": "Psychiatric",
    # Beauty and personal care
    "salon": "HairSalon",
    "hair": "HairSalon",
    "barber": "HairSalon",
    "nail": "NailSalon",
    "beauty": "BeautySalon",
    "tattoo": "TattooParlor",
    "gym": "ExerciseGym",
    "fitness": "ExerciseGym",
    "yoga": "ExerciseGym",
    "pilates": "ExerciseGym",
    "crossfit": "ExerciseGym",
    # Professional services
    "law": "Attorney",
    "attorney": "Attorney",
    "lawyer": "Attorney",
    "legal": "LegalService",
    "account": "AccountingService",
    "bookkeep": "AccountingService",
    "cpa": "AccountingService",
    "tax": "AccountingService",
    "insurance": "InsuranceAgency",
    "real estate": "RealEstateAgent",
    "realtor": "RealEstateAgent",
    "mortgage": "FinancialService",
    "financial": "FinancialService",
    "consult": "ProfessionalService",
    "market": "ProfessionalService",
    "agency": "ProfessionalService",
    "architect": "ProfessionalService",
    "notary": "Notary",
    "staffing": "EmploymentAgency",
    "recruit": "EmploymentAgency",
    # Auto
    "auto repair": "AutoRepair",
    "mechanic": "AutoRepair",
    "auto body": "AutoBodyShop",
    "car wash": "AutoWash",
    "tire": "AutoPartsStore",
    "dealership": "AutoDealer",
    "towing": "AutomotiveBusiness",
    "auto": "AutomotiveBusiness",
    # Food and hospitality
    "restaurant": "Restaurant",
    "cafe": "CafeOrCoffeeShop",
    "coffee": "CafeOrCoffeeShop",
    "bakery": "Bakery",
    "bar": "BarOrPub",
    "pub": "BarOrPub",
    "brewery": "Brewery",
    "caterer": "FoodEstablishment",
    "catering": "FoodEstablishment",
    "pizza": "Restaurant",
    "hotel": "Hotel",
    "food truck": "FoodEstablishment",
    # Retail and other
    "store": "Store",
    "shop": "Store",
    "boutique": "ClothingStore",
    "florist": "Florist",
    "jewel": "JewelryStore",
    "furniture": "FurnitureStore",
    "pet": "PetStore",
    "grocer": "GroceryStore",
    "photograph": "ProfessionalService",
    "school": "EducationalOrganization",
    "tutor": "EducationalOrganization",
    "daycare": "ChildCare",
    "child care": "ChildCare",
    "childcare": "ChildCare",
    "storage": "SelfStorage",
    "travel": "TravelAgency",
    "funeral": "FuneralHome",
    "laundry": "DryCleaningOrLaundry",
    "dry clean": "DryCleaningOrLaundry",
}

# Every schema.org type we may emit, so the schema check can recognize a
# correctly-typed node as a local business even when it is not the generic type.
LOCAL_BUSINESS_TYPES: frozenset[str] = frozenset(
    {"LocalBusiness", "Organization", *CATEGORY_TO_SCHEMA.values()}
    | {
        "HomeAndConstructionBusiness",
        "ProfessionalService",
        "MedicalBusiness",
        "AutomotiveBusiness",
        "FoodEstablishment",
        "HealthAndBeautyBusiness",
        "LodgingBusiness",
        "EntertainmentBusiness",
        "SportsActivityLocation",
        "FinancialService",
        "EmergencyService",
        "ChildCare",
        "Store",
        "Dentist",
    }
)


# Broad words that describe a *kind* of business rather than a trade. They are
# matched only after the specific keywords, so "HVAC contractor" resolves to
# HVACBusiness rather than GeneralContractor purely because "contractor" is the
# longer string.
GENERIC_KEYWORDS: frozenset[str] = frozenset(
    {
        "contractor", "construction", "remodel", "handyman", "agency",
        "consult", "market", "store", "shop", "clean", "service", "professional",
        "medical", "clinic", "therap", "legal", "financial", "auto", "boutique",
    }
)


def schema_type_for(category: str) -> str:
    """Best schema.org type for a plain-language category.

    Specific trade keywords win over broad ones; within a tier, the longest
    keyword wins so "auto repair" beats "auto". Falls back to `LocalBusiness`,
    which is valid but tells assistants less.
    """
    text = (category or "").strip().lower()
    if not text:
        return "LocalBusiness"

    specific = [k for k in CATEGORY_TO_SCHEMA if k not in GENERIC_KEYWORDS]
    generic = [k for k in CATEGORY_TO_SCHEMA if k in GENERIC_KEYWORDS]

    for tier in (specific, generic):
        for keyword in sorted(tier, key=len, reverse=True):
            if keyword in text:
                return CATEGORY_TO_SCHEMA[keyword]
    return "LocalBusiness"


def is_local_business_type(type_name: str) -> bool:
    return type_name in LOCAL_BUSINESS_TYPES
