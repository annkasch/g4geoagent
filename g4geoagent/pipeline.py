"""The run: one function per box of the architecture (architecture.yaml), in the order of its arrows.

    python -m g4geoagent.pipeline <run folder> <starting document> [...] [--name "LEGEND-200"]
                                  [--rounds N] [--searches N] [--seed N]

Writes into the run folder: evidence/ (documents, saved finds), build/ (attempts),
detector.gdml, evidence_report.md and log.jsonl.
"""

import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field

from g4geoagent import report
from g4geoagent.agent import agree, llm, readers
from g4geoagent.agent.builder import build as run_builder
from g4geoagent.agent.compare import check_quotes, match_readings
from g4geoagent.agent.evidence import Evidence
from g4geoagent.agent.llm import call_llm_json
from g4geoagent.agent.research import research as run_research
from g4geoagent.agent.runlog import RunLog
from g4geoagent.architecture import BOXES, check_log, step
from g4geoagent.inspector.claims_check import as_feedback, check_claims, summary
from g4geoagent.inspector.geant4_run import geant4_run

TEAM_MODEL = "lbl/gpt-oss-120b"
BUILD_MODEL = "lbl/gemma-4"
BUILD_ATTEMPTS = 6


@dataclass
class State:
    folder: Path
    name: str                                   # what the detector is called, for searches
    log: RunLog
    evidence: Evidence
    max_rounds: int = 2
    searches_per_round: int = 1
    seed: int | None = None
    # reading
    unread: list = field(default_factory=list)  # documents in the folder that were not read yet
    readings: dict = field(default_factory=dict)
    failing: dict = field(default_factory=dict)
    pairs: list = field(default_factory=list)
    only: dict = field(default_factory=dict)
    confirmed: list = field(default_factory=list)
    rejected: list = field(default_factory=list)
    lost: list = field(default_factory=list)
    # claims
    parts: dict = field(default_factory=dict)   # name: Part
    claims: dict = field(default_factory=dict)  # id (C1, C2, ...): Claim
    origin: dict = field(default_factory=dict)  # id: file the claim comes from
    disputed: list = field(default_factory=list)
    dropped: list = field(default_factory=list)
    # work of the team
    team: dict = field(default_factory=dict)
    searches: list = field(default_factory=list)     # asked for in this round
    research: list = field(default_factory=list)     # everything searched so far, with its outcome
    attempts: list = field(default_factory=list)     # of the current round: {gdml, rows, shown, notes}
    candidate: dict | None = None                    # the build of the current round
    best: dict | None = None                         # the best build of all rounds
    round: int = 0
    new_claims: int = 0                              # in the current round
    stopped: str = ""

    def built_claims(self):
        return {key: claim for key, claim in self.claims.items() if claim.category != "not_geometry"}


# ---------------------------------------------------------------- reading

@step("reader_A", "reader_B")
def read(state):
    """Both readers read the documents that were not read yet."""
    documents = state.evidence.documents(state.unread)
    known = list(state.parts)
    with ThreadPoolExecutor(2) as pool:
        a, b = pool.map(lambda name: readers.read_paper(documents, name, state.log, known_parts=known), "AB")
    state.readings = {"A": a, "B": b}


@step("compare")
def compare_quotes(state):
    """Is every quote in its document, with the value in it?"""
    documents = state.evidence.documents(state.unread)
    state.failing = {name: len(check_quotes(reading, documents)) for name, reading in state.readings.items()}
    state.log.event("check", "compare_quotes", failing=state.failing)


@step("reader_A", "reader_B")
def repair(state):
    """Each reader gets one chance to repair its failing quotes. What still fails is dropped."""
    documents = state.evidence.documents(state.unread)
    state.lost = [claim for name, reading in state.readings.items()
                  for claim in agree.repair_quotes(reading, documents, name, state.log)]


@step("compare")
def compare_pair(state):
    """Pair up the claims of the two readers."""
    documents = state.evidence.documents(state.unread)
    state.pairs, only_a, only_b = match_readings(state.readings["A"], state.readings["B"], documents)
    state.only = {"A": only_a, "B": only_b}
    state.log.event("check", "compare_pair", pairs=len(state.pairs), only_a=len(only_a), only_b=len(only_b))


@step("reader_A", "reader_B")
def cross_check(state):
    """A claim that only one reader has goes to the other reader."""
    documents = state.evidence.documents(state.unread)
    confirmed_a, rejected_a = agree.cross_check(state.only["A"], documents, "B", state.log)
    confirmed_b, rejected_b = agree.cross_check(state.only["B"], documents, "A", state.log)
    state.confirmed, state.rejected = confirmed_a + confirmed_b, rejected_a + rejected_b


@step("compare")
def compare_agree(state):
    """Add what the readers agree on to the agreed claims."""
    result = agree.assemble(state.readings["A"], state.readings["B"], state.pairs, state.confirmed,
                            state.rejected, state.lost, state.log)
    for part in result.reading.parts:
        state.parts.setdefault(part.name, part)
    for claim in result.reading.claims:
        key = f"C{len(state.claims) + 1}"
        state.claims[key], state.origin[key] = claim, claim.source
    state.new_claims += len(result.reading.claims)
    state.disputed += result.disputed
    state.dropped += result.dropped
    state.unread, state.confirmed, state.rejected, state.lost = [], [], [], []


def read_documents(state):
    """Evidence folder → Readers → Compare → agreed claims, with the re-read loops between the two."""
    read(state)
    compare_quotes(state)
    if any(state.failing.values()):
        repair(state)
    compare_pair(state)
    if state.only["A"] or state.only["B"]:
        cross_check(state)
    compare_agree(state)


# ---------------------------------------------------------------- coordination and teams

@step("coordinator")
def coordinator(state):
    """First version: one team gets every part and every claim."""
    state.team = {"name": "team_1", "parts": list(state.parts)}
    state.log.event("plan", "coordinator", teams=1, parts=len(state.parts), claims=len(state.claims))


class Search(BaseModel):
    part: str
    quantity: str = Field(description="The missing value or the missing part, in a few words")
    query: str = Field(description="Search words for a literature database: the detector, the part, what is missing")


class Searches(BaseModel):
    searches: list[Search]


def claims_text(state):
    lines = ["Parts (name: what it is; inside what):"]
    lines += [f"  {p.name}: {p.description}; inside {p.inside}" for p in state.parts.values()]
    start = {s["file"] for s in state.evidence.sources() if s["origin"] == "starting document"}
    lines.append("\nClaims (id | part | quantity | value | kind | measured from | where it comes from | quote):")
    for key, c in state.built_claims().items():
        origin = "from the starting document" if state.origin[key] in start else "found by research"
        lines.append(f"  {key} | {c.part} | {c.quantity} | {c.value} {c.unit} | {c.category} | {c.relative_to} | "
                     f"{origin} | \"{' '.join(c.quote.split())[:160]}\"")
    return "\n".join(lines)


@step("teams")
def team(state):
    """The team decides which missing values are worth a search before it builds."""
    state.searches = []
    budget = state.searches_per_round
    if budget <= 0:
        return
    done = "\n".join(f"  {r['part']}: {r['quantity']} ({r['outcome'][:80]})" for r in state.research) or "  none"
    request = (f"You are about to build a geometry model of this detector for a particle simulation: {state.name}.\n\n"
               f"{claims_text(state)}\n\nSearches already made:\n{done}\n\n"
               f"Which values or parts are still missing to build the detector? Name the {budget} most important "
               "that a design paper, a thesis or a technical report could give: main dimensions, positions and "
               "counts of the large and of the sensitive parts come first. Do not repeat a search already made. "
               "Answer with one JSON object that fits this schema and nothing else:\n"
               + json.dumps(Searches.model_json_schema(), separators=(",", ":")))
    try:
        answer, _ = call_llm_json(TEAM_MODEL, [{"role": "user", "content": request}], Searches,
                                  log=state.log, stage="team_gaps", temperature=0)
        state.searches = answer.searches[:budget]
    except ValueError as error:
        state.log.event("team_gaps_failed", "teams", error=str(error)[:300])


@step("research")
def research(state):
    """Search for what the team asked for. Finds go to the evidence folder and wait to be read."""
    for search in state.searches:
        result = run_research(state.evidence, state.name, search.part, search.quantity, search.query, state.log)
        state.log.event("research", "research", **result)
        state.research.append({**result, "round": state.round})
        if result["file"]:
            state.unread.append(result["file"])
    state.searches = []


# ---------------------------------------------------------------- piece loop

@step("build")
def build(state):
    """Write the geometry from the claims. Each valid geometry is measured against the claims
    (measure_vs_claims), and what is not met goes back to the builder."""
    workdir = state.folder / "build" / f"round{state.round}"
    state.attempts = []

    def check(gdml, report):
        feedback = measure_vs_claims(state, gdml, report)
        if feedback:
            state.log.enter(("build",))       # fail: fix
        return feedback or None

    result = run_builder("Detector: " + state.name + "\n\n" + claims_text(state), BUILD_MODEL, workdir,
                         attempts=BUILD_ATTEMPTS, log=state.log, seed=state.seed,
                         prompt="builder_claims.md", check=check)
    state.log.event("build", "build", attempts=result["attempts"], finished=result["finished"],
                    valid=result["valid"], measured=len(state.attempts))
    # the best of the valid attempts: most claims met
    state.candidate = max(state.attempts, key=lambda a: a["summary"]["met"], default=None)
    if state.log.box == ["build"]:
        measure_vs_claims(state, None, None)        # the builder had the last word: record where the piece stands


@step("measure_vs_claims")
def measure_vs_claims(state, gdml, report):
    """Compare the geometry with the claims it was built from. Returns the feedback for the builder."""
    if gdml is None:
        state.log.event("check", "measure_vs_claims", final=True,
                        **(state.candidate["summary"] if state.candidate else {"valid": False}))
        return ""
    notes_file = gdml.with_suffix(".json")
    try:
        notes = json.loads(notes_file.read_text())
        shown = [e for e in notes.get("shown", []) if isinstance(e, dict)]
    except (OSError, ValueError):
        notes, shown = {}, []
    claims = state.built_claims()
    rows = check_claims(claims, shown, report)
    attempt = {"gdml": gdml, "rows": rows, "notes": notes, "summary": summary(rows), "report": report}
    state.attempts.append(attempt)
    state.log.event("check", "measure_vs_claims", gdml=gdml.name, **attempt["summary"])
    feedback = as_feedback(rows, claims)
    if not shown:
        return "The notes file is missing or has no \"shown\" list, so nothing could be measured against the claims."
    if feedback:
        return ("The file loads in Geant4 without overlaps. A program measured it against the claims. "
                "These claims are not met:\n" + feedback)
    return ""


@step("look")
def look(state):
    state.log.event("stub", "look", note=BOXES["look"]["first"])


# ---------------------------------------------------------------- whole detector

@step("integrate")
def integrate(state):
    state.log.event("stub", "integrate", note=BOXES["integrate"]["first"])


@step("check_whole_detector")
def check_whole_detector(state):
    """The table of all built claims against the geometry of this round."""
    if state.candidate:
        state.log.event("check", "check_whole_detector", **state.candidate["summary"])
    else:
        state.log.event("check", "check_whole_detector", valid=False)


@step("run_geant4")
def run_geant4(state):
    """Geant4's own verdict on the geometry of this round: load, overlaps, lines along the axes."""
    if not state.candidate:
        state.log.event("check", "run_geant4", valid=False)
        return
    report = geant4_run(state.candidate["gdml"], log_path=state.folder / "build" / f"round{state.round}" / "geant4.log")
    state.candidate["report"] = report
    state.log.event("check", "run_geant4", ok=report["ok"], loaded=report["loaded"], overlaps=report["overlaps"],
                    volumes=len(report.get("parts", [])), problems=report["problems"][:5])


@step("final_look")
def final_look(state):
    state.log.event("stub", "final_look", note=BOXES["final_look"]["first"])


@step("round_rule")
def round_rule(state):
    """Keep the best version. Another round if this one brought new claims and rounds are left."""
    def score(build):
        return (build["report"]["ok"], build["summary"]["met"]) if build else (False, -1)
    if score(state.candidate) > score(state.best):
        state.best = {**state.candidate, "round": state.round}
    if state.round >= state.max_rounds:
        state.stopped = f"the limit of {state.max_rounds} rounds was reached"
    elif state.new_claims == 0:
        state.stopped = "a full round brought no new claims"
    state.log.event("round", "round_rule", round=state.round, new_claims=state.new_claims,
                    met=state.candidate["summary"]["met"] if state.candidate else None,
                    another=not state.stopped, stopped=state.stopped)
    return not state.stopped


# ---------------------------------------------------------------- outside the system

@step("evaluator")
def evaluator(state):
    state.log.event("stub", "evaluator", note=BOXES["evaluator"]["first"])


@step("system_audit")
def system_audit(state):
    state.log.event("stub", "system_audit", note=BOXES["system_audit"]["first"])


# ---------------------------------------------------------------- the run

def run(folder, documents, name, max_rounds=2, searches_per_round=1, seed=None):
    """Run the whole system on the starting `documents`. Returns the final state."""
    folder = Path(folder)
    if (folder / "log.jsonl").exists():         # an earlier run in this folder is replaced
        shutil.rmtree(folder)
    log = RunLog(folder / "log.jsonl")
    state = State(folder=folder, name=name, log=log, evidence=Evidence(folder / "evidence", log),
                  max_rounds=max_rounds, searches_per_round=searches_per_round, seed=seed)
    if seed is not None:
        llm.DEFAULT_OPTIONS["seed"] = seed
    state.unread = [state.evidence.add_starting(path) for path in documents]

    read_documents(state)
    coordinator(state)
    while True:
        state.round += 1
        team(state)
        if state.searches:
            research(state)
            if state.unread:
                read_documents(state)
                coordinator(state)
            team_continues(state)
        build(state)
        look(state)
        integrate(state)
        check_whole_detector(state)
        run_geant4(state)
        final_look(state)
        if not round_rule(state):
            break
        state.new_claims = 0

    if state.best:
        shutil.copy(state.best["gdml"], folder / "detector.gdml")
    state.log.box = None
    problems = check_log(log.events())
    (folder / "evidence_report.md").write_text(report.evidence_report(state, problems))
    log.event("output", "output", gdml=bool(state.best), stopped=state.stopped, architecture_problems=problems)
    evaluator(state)
    system_audit(state)
    return state


@step("teams")
def team_continues(state):
    """The team takes up its work again with the claims that research brought."""
    state.log.event("team", "teams", claims=len(state.claims), new_claims=state.new_claims)


if __name__ == "__main__":
    args = sys.argv[1:]

    def option(name, default):
        if name in args:
            value = args[args.index(name) + 1]
            del args[args.index(name):args.index(name) + 2]
            return value
        return default

    name = option("--name", None)
    rounds, searches = int(option("--rounds", 2)), int(option("--searches", 1))
    seed = option("--seed", None)
    folder, documents = Path(args[0]), [Path(a) for a in args[1:]]
    final = run(folder, documents, name or documents[0].stem, rounds, searches, None if seed is None else int(seed))
    print((folder / "evidence_report.md").read_text()[:3000])
