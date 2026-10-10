"""Variants of the Build box for experiments/build_bench.py: name -> function that sets up the run state."""


def baseline(state):
    pass


def prompt(name, **more):
    def setup(state):
        state.build_prompt = name
        for key, value in more.items():
            setattr(state, key, value)
    return setup


VARIANTS = {
    "v01_baseline": baseline,
    "v02_names": prompt("builder_claims_names.md"),           # valid material names written into the instructions
    "v03_helper": prompt("builder_claims_helper.md"),         # material() from g4geoagent.blueprint
    # Geant4's own overlap messages as feedback: which part sticks out of which, and by how much
    "v04_names_overlap": prompt("builder_claims_names.md", build_overlap_details=True),
    "v05_helper_overlap": prompt("builder_claims_helper.md", build_overlap_details=True),
}
