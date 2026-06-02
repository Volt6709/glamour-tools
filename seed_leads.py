"""Run once to seed the initial lead list."""
import db

db.init_db()

leads = [
    ("Dee Bergen",      "A-Jay Interiors by Dee",  "office@ajayinteriorsbydee.com", "",             "Paramus, NJ"),
    ("Noel Gatts",      "Beam & Bloom",             "info@beamandbloom.com",         "917-267-8016", "Bloomfield, NJ"),
    ("Compitello",      "Compitello Interiors",     "",                              "914-282-8273", "Saddle Brook, NJ"),
    ("Marie Burgos",    "Marie Burgos Design",      "marie@marieburgosdesign.com",   "917-353-9149", "NYC"),
    ("Brittany Bromley","Brittany Bromley Interiors","info@bbromleyinteriors.com",   "914-205-3460", "Bedford, NY"),
    ("Nitzan Design",   "Nitzan Design",            "info@nitzandesign.com",         "646-209-3246", "NYC"),
    ("Tara Benet",      "Tara Benet Designs",       "info@tarabenet.com",            "917-510-7210", "NYC"),
    ("Chango",          "Chango & Co.",             "questions@chango.com",          "",             "Brooklyn, NY"),
    ("Noha Hassan",     "Noha Hassan Designs",      "info@nohahassandesigns.com",    "646-291-9839", "NYC"),
    ("Betty Wasserman", "Betty Wasserman Art & Interiors", "info@bettywasserman.com","212-352-8476", "NYC"),
]

for name, firm, email, phone, location in leads:
    db.add_lead(name, firm, email, phone, location)

print(f"Seeded {len(leads)} leads.")
