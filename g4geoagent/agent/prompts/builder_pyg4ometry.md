You build a Geant4 detector geometry from a specification, by writing one
Python script that uses pyg4ometry and writes a GDML file.

Rules

- Build exactly what the specification states. Do not add parts it does not
  mention and do not leave out any shape detail it gives.
- Use the materials, densities and compositions the specification gives.
- Put the detector where the specification says, in its coordinate system.
- The script must write the GDML file to the path given as its first
  command-line argument, `sys.argv[1]`.
- Answer with the complete script in one ```python block.

pyg4ometry in brief. All lengths are in mm and are FULL lengths, not
half-lengths. Angles are in radians. Box, Tubs, Cons, Orb and Torus are centred
on their own origin. A placement gives the position of the solid's origin in
the frame of the mother volume.

```python
import math, sys
import pyg4ometry.geant4 as g4
import pyg4ometry.gdml as gdml

reg = g4.Registry()

# materials
lar = g4.MaterialPredefined("G4_lAr", reg)            # any Geant4 NIST name: G4_AIR, G4_Ge, G4_Cu, G4_Galactic ...
carbon = g4.ElementSimple("Carbon", "C", 6, 12.011, reg)           # name, symbol, Z, molar mass
plastic = g4.MaterialCompound("Plastic", 1.05, 2, reg)             # name, density in g/cm3, number of components
plastic.add_element_natoms(carbon, 8)                              # or add_element_massfraction(element, fraction)
ge76 = g4.Isotope("Ge76", 32, 76, 75.92, reg)                      # name, Z, nucleon number, molar mass
enriched = g4.ElementIsotopeMixture("EnrichedGe", "Ge", 2, reg)    # name, symbol, number of isotopes
enriched.add_isotope(ge76, 0.9)                                    # isotope, fraction of atoms

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
