You build a Geant4 detector geometry from claims that were extracted from
documents, by writing one Python script that uses pyg4ometry. The script writes
a GDML file and a notes file.

Rules

- Build every part that the claims describe. Each claim has an id (C1, C2, ...).
  Claims marked "from the starting document" win over claims found by research
  when the two contradict each other.
- The claims never state everything. Where a value needed for the build is
  missing, choose a reasonable one and list it under "estimates" in the notes.
  Never leave a part out because a value is missing.
- Parts that repeat (detectors on a string, sensors on a wall) are placed in a
  loop, one physical volume each, named with a common start and a number:
  pmt_0, pmt_1, ...
- Nothing may overlap. A part inside another one is placed in that volume as
  its mother, and must fit inside it.
- The script writes the GDML file to `sys.argv[1]` and the notes, as JSON, to
  `sys.argv[2]`.
- Answer with the complete script in one ```python block.

The notes file. A program uses it to measure your geometry against the claims:

```python
notes = {
  # one entry for each claim that can be measured on a volume
  "shown": [
    {"id": "C1", "volume": "water_tank", "measure": "size_x"},   # a diameter along x
    {"id": "C2", "volume": "water_tank", "measure": "size_z"},   # a height along z
    {"id": "C4", "volume": "pmt", "measure": "count"},           # counts pmt_0, pmt_1, ...
    {"id": "C7", "volume": "argon", "measure": "volume"},
    {"id": "C9", "volume": "detector", "measure": "mass"},       # sum over detector_0, detector_1, ...
  ],
  # values you had to choose because no claim gives them
  "estimates": [{"part": "pmt", "quantity": "diameter", "value": 200, "unit": "mm", "reason": "typical 8 inch tube"}],
  # claims you did not build, and why
  "not_built": [{"id": "C12", "reason": "an operating voltage, not a part"}],
}
json.dump(notes, open(sys.argv[2], "w"), indent=1)
```

"volume" is the name of a physical volume. "measure" is one of: size_x, size_y,
size_z (full size of the solid along its own axis, so the diameter of a tube
along z is size_x), count, mass, volume.

pyg4ometry in brief. All lengths are in mm and are FULL lengths, not
half-lengths. Angles are in radians. Box, Tubs, Cons, Orb and Torus are centred
on their own origin. A placement gives the position of the solid's origin in
the frame of the mother volume.

```python
import json, math, sys
import pyg4ometry.geant4 as g4
import pyg4ometry.gdml as gdml

reg = g4.Registry()

# materials. Use exactly these Geant4 names where they fit: G4_Galactic (vacuum), G4_AIR, G4_WATER, G4_lAr,
# G4_Ar, G4_lXe, G4_lN2, G4_STAINLESS-STEEL, G4_Cu, G4_Pb, G4_Al, G4_Fe, G4_Ge, G4_Si, G4_W, G4_Ti, G4_Au,
# G4_Pyrex_Glass, G4_NYLON-6-6, G4_TEFLON, G4_KAPTON, G4_MYLAR, G4_POLYETHYLENE, G4_POLYSTYRENE,
# G4_PLASTIC_SC_VINYLTOLUENE, G4_PLEXIGLASS, G4_CONCRETE, G4_SILICON_DIOXIDE. Other names do not exist.
# Define every element only once and reuse it. A LogicalVolume needs a material, never an element.
lar = g4.MaterialPredefined("G4_lAr", reg)            # any Geant4 NIST name: G4_AIR, G4_Ge, G4_Cu, G4_Galactic ...
carbon = g4.ElementSimple("Carbon", "C", 6, 12.011, reg)           # name, symbol, Z, molar mass
plastic = g4.MaterialCompound("Plastic", 1.05, 2, reg)             # name, density in g/cm3, number of components
plastic.add_element_natoms(carbon, 8)                              # or add_element_massfraction(element, fraction)
ge76 = g4.Isotope("Ge76", 32, 76, 75.92, reg)                      # name, Z, nucleon number, molar mass
enriched = g4.ElementIsotopeMixture("EnrichedGe", "Ge", 2, reg)    # name, symbol, number of isotopes
enriched.add_isotope(ge76, 0.9)                                    # isotope, fraction of atoms
enriched_ge = g4.MaterialCompound("EnrichedGermanium", 5.55, 1, reg)  # an element is turned into a material like this
enriched_ge.add_element_massfraction(enriched, 1.0)

# solids
g4.solid.Box("name", x, y, z, reg)
g4.solid.Tubs("name", r_min, r_max, length, 0, 2 * math.pi, reg)
g4.solid.Cons("name", r_min1, r_max1, r_min2, r_max2, length, 0, 2 * math.pi, reg)   # 1 is the end at -z
g4.solid.Polycone("name", 0, 2 * math.pi, [z0, z1, z2], [r_min0, r_min1, r_min2], [r_max0, r_max1, r_max2], reg)
g4.solid.Orb("name", r, reg)                                       # full sphere
g4.solid.Sphere("name", r_min, r_max, 0, 2 * math.pi, 0, math.pi, reg)   # start phi, delta phi, start theta, delta theta
g4.solid.Torus("name", r_min, r_max, r_torus, 0, 2 * math.pi, reg)        # tube radii, then radius of the ring
# booleans: the second solid is placed in the frame of the first with [[rx, ry, rz], [x, y, z]]
g4.solid.Subtraction("name", first, second, [[0, 0, 0], [0, 0, dz]], reg)
g4.solid.Union("name", first, second, [[0, 0, 0], [0, 0, dz]], reg)
g4.solid.Intersection("name", first, second, [[0, 0, 0], [0, 0, dz]], reg)

# volumes
world_lv = g4.LogicalVolume(world_solid, lar, "world", reg)
part_lv = g4.LogicalVolume(part_solid, plastic, "part", reg)
g4.PhysicalVolume([0, 0, 0], [x, y, z], part_lv, "part", world_lv, reg)   # rotation, position, volume, name, mother
reg.setWorld(world_lv)

writer = gdml.Writer()
writer.addDetector(reg)
writer.write(sys.argv[1])
```

A solid that cuts into another one should stick out of it a little where it
reaches the surface, so that the two surfaces do not coincide.
