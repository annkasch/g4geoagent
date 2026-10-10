"""Geant4 test run on one GDML file. Runs in its own process, started by geant4_run().

    python -m g4geoagent.inspector._geant4_worker request.json result.json

Geant4 can be initialised only once per process and may crash on a bad
geometry, so this module is never imported by the caller.
"""

import json
import sys

from geant4_pybind import *  # noqa: F403

OVERLAP_POINTS = 10000   # surface points sampled per placed volume
OVERLAP_TOL = 1e-6       # mm


class Detector(G4VUserDetectorConstruction):
    def __init__(self, world):
        super().__init__()
        self.world = world

    def Construct(self):
        return self.world


class Gun(G4VUserPrimaryGeneratorAction):
    """Fires one particle per event from the list in `shots`."""

    def __init__(self, state):
        super().__init__()
        self.state = state
        self.gun = G4ParticleGun(1)

    def GeneratePrimaries(self, event):
        particle, energy, start, direction = self.state["shots"][event.GetEventID()]
        table = G4ParticleTable.GetParticleTable()
        self.gun.SetParticleDefinition(table.FindParticle(particle))
        self.gun.SetParticleEnergy(energy * MeV)
        self.gun.SetParticlePosition(G4ThreeVector(*start) * mm)
        self.gun.SetParticleMomentumDirection(G4ThreeVector(*direction))
        self.gun.GeneratePrimaryVertex(event)


class Recorder(G4UserSteppingAction):
    """Scan mode: volumes crossed by each primary. Run mode: energy per volume."""

    def __init__(self, state):
        super().__init__()
        self.state = state

    def UserSteppingAction(self, step):
        pre = step.GetPreStepPoint()
        volume = pre.GetTouchable().GetVolume().GetName()
        if self.state["mode"] == "scan":
            if step.GetTrack().GetParentID() != 0:
                return
            event = G4RunManager.GetRunManager().GetCurrentEvent().GetEventID()
            segments = self.state["scans"][event]
            length = step.GetStepLength() / mm
            if segments and segments[-1]["volume"] == volume:
                segments[-1]["length_mm"] += length
            else:
                segments.append({"volume": volume,
                                 "material": pre.GetMaterial().GetName(),
                                 "length_mm": length})
        else:
            edep = step.GetTotalEnergyDeposit() / MeV
            if edep > 0:
                totals = self.state["edep"]
                totals[volume] = totals.get(volume, 0.0) + edep


class Actions(G4VUserActionInitialization):
    def __init__(self, state):
        super().__init__()
        self.state = state

    def Build(self):
        self.SetUserAction(Gun(self.state))
        self.SetUserAction(Recorder(self.state))


def walk(pv, mother, parts, overlaps, checked=None):
    """Parts report and Geant4's own overlap check for pv and everything below it.

    The daughters of a volume that is placed many times are checked for overlaps only once.
    """
    checked = set() if checked is None else checked
    lv = pv.GetLogicalVolume()
    position = pv.GetTranslation()
    lo, hi = G4ThreeVector(), G4ThreeVector()
    lv.GetSolid().BoundingLimits(lo, hi)
    parts.append({
        "volume": pv.GetName(),
        "logical": lv.GetName(),
        "mother": mother,
        "material": lv.GetMaterial().GetName(),
        "density_g_cm3": lv.GetMaterial().GetDensity() / (g / cm3),
        "solid": lv.GetSolid().GetEntityType(),
        "position_mm": [position.x / mm, position.y / mm, position.z / mm],
        # full size of the solid along its own axes
        "size_mm": [(hi.x - lo.x) / mm, (hi.y - lo.y) / mm, (hi.z - lo.z) / mm],
        "solid_volume_cm3": lv.GetSolid().GetCubicVolume() / cm3,
        # daughters are subtracted, so this is the material actually in this part
        "mass_g": lv.GetMass(True, False) / g,
    })
    first = id(pv) not in checked
    checked.add(id(pv))
    if mother is not None and first and pv.CheckOverlaps(OVERLAP_POINTS, OVERLAP_TOL, True):
        overlaps.append(pv.GetName())
    for i in range(lv.GetNoDaughters()):
        walk(lv.GetDaughter(i), pv.GetName(), parts, overlaps, checked)


def default_scans(world):
    """One line along each axis through the origin, starting just inside the world."""
    lo, hi = G4ThreeVector(), G4ThreeVector()
    world.GetLogicalVolume().GetSolid().BoundingLimits(lo, hi)
    hi = [hi.x / mm, hi.y / mm, hi.z / mm]
    scans = []
    for axis in range(3):
        start, direction = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
        start[axis] = 0.999 * hi[axis]
        direction[axis] = -1.0
        scans.append({"start": start, "direction": direction})
    return scans


def main(request_path, result_path):
    with open(request_path) as f:
        request = json.load(f)
    result = {"loaded": False}

    def save():
        with open(result_path, "w") as f:
            json.dump(result, f, indent=1)

    save()
    parser = G4GDMLParser()
    parser.Read(request["gdml"], False)   # no schema validation: it needs internet
    world = parser.GetWorldVolume()
    result["loaded"] = True
    save()

    state = {"mode": "scan", "shots": [], "scans": [], "edep": {}}
    run_manager = G4RunManagerFactory.CreateRunManager(G4RunManagerType.Serial)
    run_manager.SetUserInitialization(Detector(world))
    run_manager.SetUserInitialization(FTFP_BERT())
    run_manager.SetUserInitialization(Actions(state))
    run_manager.Initialize()

    parts, overlaps = [], []
    walk(world, None, parts, overlaps)
    result["parts"] = parts
    result["overlaps"] = overlaps
    save()

    scans = request.get("scans") or default_scans(world)
    state["shots"] = [("geantino", 1.0, s["start"], s["direction"]) for s in scans]
    state["scans"] = [[] for _ in scans]
    run_manager.BeamOn(len(scans))
    result["scans"] = [dict(s, segments=seg) for s, seg in zip(scans, state["scans"])]
    save()

    real = request.get("real_run")
    if real:
        state["mode"] = "run"
        state["shots"] = [(real["particle"], real["energy_MeV"],
                           real["start"], real["direction"])] * real["n"]
        run_manager.BeamOn(real["n"])
        result["real_run"] = dict(real, completed=True, edep_MeV=state["edep"])
        save()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
