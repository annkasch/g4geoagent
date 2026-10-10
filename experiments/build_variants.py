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
    # from round 4 (names + overlap messages), one change each
    "v06_nesting": prompt("builder_claims_nesting.md", build_overlap_details=True),   # how to nest; merge huge repetitions
    "v07_attempts10": prompt("builder_claims_names.md", build_overlap_details=True, build_attempts=10),
    "v08_gpt_oss": prompt("builder_claims_names.md", build_overlap_details=True, build_model="lbl/gpt-oss-120b"),
}
