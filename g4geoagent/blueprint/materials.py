"""One function for materials, so that a build script does not define elements and compounds by hand.

    material(reg, "stainless steel")                         a common name or a Geant4 name (G4_...)
    material(reg, "PEN", density=1.35, formula={"C": 14, "H": 10, "O": 4})      atoms per molecule
    material(reg, "enriched germanium", density=5.55, isotopes={"Ge": {76: 0.9, 74: 0.1}})

Asking twice for the same name gives the same material.
"""

import re

import pyg4ometry.geant4 as g4

NIST = g4.getNistMaterialDict()
# common names -> Geant4 names. Elements are found by their symbol or English name without this table.
COMMON = {
    "vacuum": "G4_Galactic", "air": "G4_AIR", "water": "G4_WATER", "ice": "G4_WATER",
    "liquid argon": "G4_lAr", "lar": "G4_lAr", "argon gas": "G4_Ar", "gaseous argon": "G4_Ar",
    "liquid xenon": "G4_lXe", "lxe": "G4_lXe", "liquid nitrogen": "G4_lN2",
    "stainless steel": "G4_STAINLESS-STEEL", "steel": "G4_STAINLESS-STEEL",
    "glass": "G4_Pyrex_Glass", "borosilicate glass": "G4_Pyrex_Glass", "pyrex": "G4_Pyrex_Glass",
    "nylon": "G4_NYLON-6-6", "teflon": "G4_TEFLON", "ptfe": "G4_TEFLON", "kapton": "G4_KAPTON", "mylar": "G4_MYLAR",
    "polyethylene": "G4_POLYETHYLENE", "polystyrene": "G4_POLYSTYRENE", "polypropylene": "G4_POLYPROPYLENE",
    "plastic scintillator": "G4_PLASTIC_SC_VINYLTOLUENE", "scintillator": "G4_PLASTIC_SC_VINYLTOLUENE",
    "acrylic": "G4_PLEXIGLASS", "pmma": "G4_PLEXIGLASS", "plexiglass": "G4_PLEXIGLASS",
    "concrete": "G4_CONCRETE", "rock": "G4_SILICON_DIOXIDE", "quartz": "G4_SILICON_DIOXIDE",
    "fused silica": "G4_SILICON_DIOXIDE", "sodium iodide": "G4_SODIUM_IODIDE", "bgo": "G4_BGO",
    "lead tungstate": "G4_PbWO4", "paraffin": "G4_PARAFFIN", "brass": "G4_BRASS", "bronze": "G4_BRONZE",
}
ELEMENT_NAMES = {"hydrogen": "H", "helium": "He", "lithium": "Li", "beryllium": "Be", "boron": "B", "carbon": "C",
                 "nitrogen": "N", "oxygen": "O", "fluorine": "F", "neon": "Ne", "sodium": "Na", "magnesium": "Mg",
                 "aluminium": "Al", "aluminum": "Al", "silicon": "Si", "phosphorus": "P", "sulfur": "S", "chlorine": "Cl",
                 "argon": "Ar", "potassium": "K", "calcium": "Ca", "titanium": "Ti", "chromium": "Cr", "manganese": "Mn",
                 "iron": "Fe", "nickel": "Ni", "copper": "Cu", "zinc": "Zn", "germanium": "Ge", "molybdenum": "Mo",
                 "silver": "Ag", "cadmium": "Cd", "tin": "Sn", "xenon": "Xe", "gadolinium": "Gd", "tungsten": "W",
                 "gold": "Au", "lead": "Pb", "bismuth": "Bi", "uranium": "U"}


def _cached(reg, key, make):
    cache = reg.__dict__.setdefault("_blueprint_materials", {})
    if key not in cache:
        cache[key] = make()
    return cache[key]


def _nist_name(name):
    """The Geant4 name for `name`, or None."""
    if name in NIST:
        return name
    plain = " ".join(re.sub(r"[_\-]+", " ", name).lower().split())
    if plain in COMMON:
        return COMMON[plain]
    symbol = ELEMENT_NAMES.get(plain, name.strip())
    if "G4_" + symbol in NIST:
        return "G4_" + symbol
    lowered = {key.lower(): key for key in NIST}
    return lowered.get(("g4_" + plain.replace(" ", "_")), lowered.get(name.lower()))


def _element(reg, symbol):
    def make():
        entry = NIST["G4_" + symbol]
        mass = sum(a * fraction for _, a, fraction in entry["isotopes"])
        return g4.ElementSimple("element_" + symbol, symbol, entry["z"], mass, reg)
    return _cached(reg, ("element", symbol), make)


def material(reg, name, density=None, formula=None, isotopes=None):
    """A material in registry `reg`.

    name      a common name ("water", "stainless steel", "liquid argon", "copper", "Ge") or a Geant4 name
    density   in g/cm3, needed together with `formula` or `isotopes`
    formula   {element symbol: atoms per molecule} for a compound that Geant4 does not know
    isotopes  {element symbol: {nucleon number: share of atoms}} for one element with a changed isotope mix
    """
    def make():
        safe = re.sub(r"\W+", "_", name)
        if isotopes:
            (symbol, mix), = isotopes.items()
            z = NIST["G4_" + symbol]["z"]
            element = g4.ElementIsotopeMixture("element_" + safe, symbol, len(mix), reg)
            for a, share in mix.items():
                element.add_isotope(g4.Isotope(f"{symbol}{a}_{safe}", z, int(a), float(a), reg), share)
            compound = g4.MaterialCompound(safe, density, 1, reg)
            compound.add_element_massfraction(element, 1.0)
            return compound
        if formula:
            compound = g4.MaterialCompound(safe, density, len(formula), reg)
            for symbol, atoms in formula.items():
                compound.add_element_natoms(_element(reg, ELEMENT_NAMES.get(symbol.lower(), symbol)), int(atoms))
            return compound
        known = _nist_name(name)
        if known is None:
            raise ValueError(f"'{name}' is not a known material. Use a Geant4 name (G4_...), a common name such as "
                             "'stainless steel', or give density (g/cm3) and formula={'C': 2, 'H': 4}.")
        return g4.MaterialPredefined(known, reg)
    if (formula or isotopes) and density is None:
        raise ValueError(f"material '{name}': density (g/cm3) is needed together with formula or isotopes")
    return _cached(reg, ("material", name), make)
