"""The run: one function per box of the architecture (architecture.yaml), in the order of its arrows.

    python -m g4geoagent.pipeline <run folder> <starting documents: .txt and .pdf> [--name "LEGEND-200"]
                                  [--rounds N] [--searches N] [--revisions N] [--seed N] [--public-code owner/repository]

Writes into the run folder: evidence/ (documents, figures, saved finds), build/ (attempts),
pictures/, detector.gdml, evidence_report.md, log.jsonl and, with --public-code, evaluation_report.md.
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
from g4geoagent.agent.coordinator import Plan, make_plan, plan_text
from g4geoagent.agent.coordinator import teams as plan_teams
from g4geoagent.audit import audit_run
from g4geoagent.evaluator.grade import grade, grade_report
from g4geoagent.inspector.relations import as_feedback as relations_feedback
from g4geoagent.inspector.relations import check_relations
from g4geoagent.inspector.render3d import render
from g4geoagent.reviewer import look as look_at
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
    max_rounds: int = 5                         # safety stop only; the run ends when a round changes nothing
    searches_per_round: int = 1
    seed: int | None = None
    public_code: str | None = None             # "owner/repository" on GitHub, for the Evaluator only
    build_model: str = BUILD_MODEL
    build_prompt: str = "builder_plan.md"
    build_pieces: int = 2                       # parts added per piece
    build_piece_attempts: int = 4
    max_revisions: int = 10                     # per piece: how often Look may send the piece back
    same_finding_tries: int = 3                 # a difference that survives this many revisions is reported as unresolved
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
    # figures and plan
    figures_judged: list = field(default_factory=list)
    figures: list = field(default_factory=list)      # the ones that show how the detector is built
    plan: Plan | None = None
    # work of the teams
    searches: list = field(default_factory=list)     # asked for in this round
    research: list = field(default_factory=list)     # everything searched so far, with its outcome
    script: str | None = None                        # the valid script so far
    done: list = field(default_factory=list)         # parts built so far
    building: list = field(default_factory=list)     # parts the current piece is to contain
    left_out: list = field(default_factory=list)     # parts whose piece did not become valid
    attempts: list = field(default_factory=list)     # every measured geometry of this round
    candidate: dict | None = None                    # the build of the current round
    hints: str = ""                                  # what the final look of the round before found
    final: dict = field(default_factory=dict)        # verdict and differences of the final look of this round
    open_findings: list = field(default_factory=list)  # important differences that revisions did not remove
    pieces_not_passed: list = field(default_factory=list)
    unchanged_rounds: int = 0
    interfaces: list = field(default_factory=list)
    best: dict | None = None                         # the best build of all rounds
    grade: dict | None = None
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

def claims_text(state, parts=None):
    """The parts and the claims as text for a model, all of them or only those of `parts`."""
    lines = ["Parts (name: what it is; inside what):"]
    lines += [f"  {p.name}: {p.description}; inside {p.inside}" for p in state.parts.values()
              if parts is None or p.name in parts]
    start = {s["file"] for s in state.evidence.sources() if s["origin"] == "starting document"}
    lines.append("\nClaims (id | part | quantity | value | kind | measured from | where it comes from | quote):")
    for key, c in state.built_claims().items():
        if parts is not None and c.part not in parts:
            continue
        origin = "from the starting document" if state.origin[key] in start else "found by research"
        lines.append(f"  {key} | {c.part} | {c.quantity} | {c.value} {c.unit} | {c.category} | {c.relative_to} | "
                     f"{origin} | \"{' '.join(c.quote.split())[:160]}\"")
    return "\n".join(lines)


def construction_figures(state):
    """The figures of the evidence folder that show how the detector is built. New figures are judged once."""
    judged = {f["file"] for f in state.figures_judged}
    new = [f for f in state.evidence.figures() if f["file"] not in judged]
    if new:
        state.figures_judged += new
        state.figures += look_at.construction_figures(new, state.evidence.folder / "figures", state.name, state.log,
                                                      most=len(new))
    return state.figures


@step("graph_builder")
def graph_builder(state):
    """Not called for real yet: the graph is built by g4geoagent.agent.detector_graph as a step of its own."""
    state.log.event("stub", "graph_builder", note=BOXES["graph_builder"]["first"])


@step("coordinator")
def coordinator(state):
    """Settle the layout of the whole detector: nesting, hollow parts, detail levels, arrangement, teams."""
    notes = "\n".join(f"  {f['source']}, page {f['page']}: {f['shows']}" for f in state.figures)
    state.plan = make_plan(state.name, state.parts, claims_text(state), notes, state.log)
    state.log.event("plan", "coordinator", parts=len(state.plan.parts), relations=len(state.plan.relations),
                    teams=[name for name, _ in plan_teams(state.plan)],
                    hollow=[p.name for p in state.plan.parts if p.form == "hollow"])


class Search(BaseModel):
    part: str
    quantity: str = Field(description="The missing value or the missing part, in a few words")
    query: str = Field(description="Search words for a literature database: the detector, the part, what is missing")


class Searches(BaseModel):
    searches: list[Search]


@step("teams")
def team(state):
    """The teams take up the plan. They name the missing values and shapes that are worth a search."""
    state.searches = []
    budget = state.searches_per_round
    if budget <= 0:
        return
    done = "\n".join(f"  {r['part']}: {r['quantity']} ({r['outcome'][:80]})" for r in state.research) or "  none"
    request = (f"You are about to build a geometry model of this detector for a particle simulation: {state.name}.\n\n"
               f"{claims_text(state)}\n\n{plan_text(state.plan)}\n\nSearches already made:\n{done}\n\n"
               f"Which values, shapes or parts are still missing to build the detector? Name the {budget} most important "
               "that a design paper, a thesis or a technical report could give, in words or in a drawing: main "
               "dimensions, shapes, positions and counts of the large and of the sensitive parts come first. Do not "
               "repeat a search already made. Answer with one JSON object that fits this schema and nothing else:\n"
               + json.dumps(Searches.model_json_schema(), separators=(",", ":")))
    try:
        answer, _ = call_llm_json(TEAM_MODEL, [{"role": "user", "content": request}], Searches,
                                  log=state.log, stage="team_gaps", temperature=0)
        state.searches = answer.searches[:budget]
    except ValueError as error:
        state.log.event("team_gaps_failed", "teams", error=str(error)[:300])


@step("teams")
def team_continues(state):
    """The teams take up their work again after research."""
    state.log.event("team", "teams", claims=len(state.claims), new_claims=state.new_claims)


@step("research")
def research(state):
    """Search for what the teams asked for. Texts and figures go to the evidence folder and wait to be read."""
    for search in state.searches:
        # the variant chosen in experiments/notes/research.md (round 10)
        result = run_research(state.evidence, state.name, search.part, search.quantity, search.query, state.log,
                              broaden=True, fulltext=True, select_pages=True, papers=2, max_pages=50)
        figures = sum(len(state.evidence.add_figures(Path(name).with_suffix(".pdf").name)) for name in result["files"])
        state.log.event("research", "research", figures=figures, **result)
        state.research.append({**result, "round": state.round, "figures": figures})
        state.unread += result["files"]
    state.searches = []


# ---------------------------------------------------------------- piece loop

def pieces(state):
    """What is built in which order: [(team, [parts])], teams from the outside in, a few parts at a time."""
    found = []
    for name, parts in plan_teams(state.plan):
        found += [(name, parts[i:i + state.build_pieces]) for i in range(0, len(parts), state.build_pieces)]
    return found


def _builder(state, text, folder, attempts):
    """Run the builder on `text`. Every valid geometry goes through measure_vs_claims."""
    def check(gdml, report):
        feedback = measure_vs_claims(state, gdml, report)
        if feedback:
            state.log.enter(("build",))       # fail: fix
        return feedback or None

    return run_builder(text, state.build_model, folder, attempts=attempts, log=state.log, seed=state.seed,
                       prompt=state.build_prompt, check=check, overlap_details=True)


def _score(attempt):
    """How well a measured geometry meets the claims and the plan: the number of both that are met."""
    return attempt["summary"]["met"] + attempt["relations"]["met"] if attempt else -1


VERDICTS = {"matches": 2, "partly": 1, "does_not_match": 0}


def _rank(build):
    """What decides which build is the best: valid in Geant4, then what Look says about the whole,
    then few important differences left, then claims and plan met."""
    if not build:
        return (False, -1, 0, -1)
    look = build.get("look") or {}
    return (bool(build["report"]["ok"]), VERDICTS.get(look.get("verdict"), 0), -len(look.get("high", [])), _score(build))


@step("build")
def build(state, team_name, parts, number):
    """Add one piece to the geometry: the script so far is extended by `parts`. A piece that does
    not become valid is left out, and the next piece goes on from the last valid script."""
    folder = state.folder / "build" / f"round{state.round}" / f"piece{number:02d}_{team_name}"
    # a part that holds others and was left out is tried again with this piece: what belongs in it cannot be built without it
    holders = {p.name for p in state.plan.parts if p.form != "solid"}
    again = [name for name in state.left_out if name in holders]
    state.left_out = [name for name in state.left_out if name not in again]
    parts = again + parts
    wanted = state.done + parts
    text = ("Detector: " + state.name + "\n\n" + plan_text(state.plan, wanted) + "\n\n" + claims_text(state, wanted))
    if state.hints:
        text += "\n\nA reviewer compared an earlier build with figures of the real detector. Take this into account:\n" + state.hints
    if state.script is None:
        text += ("\n\nBuild only these parts for now: " + ", ".join(parts) + ". The other parts follow later; leave "
                 "room for them where the plan puts them.")
    else:
        text += ("\n\nThe script below builds the parts " + ", ".join(state.done) + " and is valid. Extend it by these "
                 "parts: " + ", ".join(parts) + ". Keep what is there, change it only where the new parts need room, "
                 "and send the complete new script.\n\n```python\n" + state.script + "\n```")
    state.building, before = wanted, len(state.attempts)
    # what other parts will sit in must not be left out: such a piece gets twice the attempts
    holds_others = any(p.form != "solid" for p in state.plan.parts if p.name in parts)
    result = _builder(state, text, folder, state.build_piece_attempts * (2 if holds_others else 1))
    made = state.attempts[before:]
    best = max(reversed(made), key=_score, default=None)
    state.log.event("piece", "build", piece=number, team=team_name, parts=parts, valid=bool(best),
                    attempts=result["attempts"], score=_score(best))
    if best:
        state.script, state.done, state.candidate = best["gdml"].with_suffix(".py").read_text(), wanted, best
    else:
        state.left_out += parts
    if state.log.box == ["build"]:
        measure_vs_claims(state, None, None)      # the builder had the last word: record where the piece stands


@step("build")
def revise(state, blocking, number, revision):
    """Look found important differences from the figures: the builder revises the geometry.
    Returns the new attempt if it is valid and no worse on claims and plan, else None. Whether the
    differences are gone is for Look to say (look_again)."""
    folder = state.folder / "build" / f"round{state.round}" / f"piece{number:02d}_revision{revision:02d}"
    text = ("Detector: " + state.name + "\n\n" + plan_text(state.plan, state.done) + "\n\n" + claims_text(state, state.done)
            + "\n\nThe script below builds these parts and is valid. A reviewer compared pictures of it with figures "
            "of the real detector and found these differences:\n" + look_at.as_feedback(blocking) + "\n\nRevise the "
            "script so that these differences are gone. Keep everything that the claims and the plan fix. Send the "
            "complete new script.\n\n```python\n" + state.script + "\n```")
    before, old, state.building = len(state.attempts), state.candidate, state.done
    _builder(state, text, folder, 3)
    best = max(reversed(state.attempts[before:]), key=_score, default=None)
    usable = bool(best) and _score(best) >= _score(old)
    state.log.event("revision", "build", piece=number, revision=revision, usable=usable, score=_score(best), before=_score(old),
                    asked=[f.part for _, f in blocking])
    if state.log.box == ["build"]:
        measure_vs_claims(state, None, None)
    return best if usable else None


@step("measure_vs_claims")
def measure_vs_claims(state, gdml, report):
    """Compare the geometry with the claims and with the layout plan. Returns the feedback for the builder."""
    if gdml is None:
        best = state.candidate
        state.log.event("check", "measure_vs_claims", final=True,
                        **({**best["summary"], "relations": best["relations"]} if best else {"valid": False}))
        return ""
    try:
        notes = json.loads(gdml.with_suffix(".json").read_text())
        shown = [e for e in notes.get("shown", []) if isinstance(e, dict)]
        volume_of = {str(k): str(v) for k, v in (notes.get("volumes") or {}).items()}
    except (OSError, ValueError, AttributeError):
        notes, shown, volume_of = {}, [], {}
    claims = state.built_claims()
    rows = check_claims(claims, shown, report)
    building = set(state.building)
    part_plan = Plan(parts=[p.model_copy(update={} if p.inside in building else {"inside": "world"})
                            for p in state.plan.parts if p.name in building],
                     relations=[r for r in state.plan.relations if r.part in building and r.other in building])
    relation_rows = check_relations(part_plan, volume_of, report)
    relations = {status: sum(r["status"] == status for r in relation_rows) for status in ("met", "not met", "not shown")}
    attempt = {"gdml": gdml, "rows": rows, "notes": notes, "summary": summary(rows), "report": report,
               "relation_rows": relation_rows, "relations": relations, "volume_of": volume_of}
    state.attempts.append(attempt)
    state.log.event("check", "measure_vs_claims", gdml=gdml.name, relations=relations, **attempt["summary"])
    missing = [p for p in state.building if p not in volume_of]
    problems = []
    if as_feedback(rows, claims):
        problems.append("These claims are not met:\n" + as_feedback(rows, claims))
    if relations_feedback(relation_rows):
        problems.append("The layout plan is not followed here:\n" + relations_feedback(relation_rows))
    if missing:
        problems.append("The notes do not name a volume under \"volumes\" for these parts of the plan: "
                        + ", ".join(missing) + ". Build them and name their volumes.")
    if not problems:
        return ""
    return ("The file loads in Geant4 without overlaps. A program measured it against the claims and the layout "
            "plan.\n" + "\n".join(problems))


def _built_parts_text(state, attempt):
    volume_of = attempt["volume_of"]
    inside = {p.name: p.inside for p in state.plan.parts}
    lines = [f"  {name} (in {inside.get(name, 'world')})" for name in state.done if name in volume_of]
    rest = [p.name for p in state.plan.parts if p.name not in state.done]
    return "\n".join(lines) + ("\nNot built yet, so do not report them as missing: " + ", ".join(rest) if rest else "")


def _pictures(state, attempt, folder):
    """3D pictures of a measured geometry with the front half cut away, made once."""
    if "pictures" not in attempt:
        try:
            attempt["pictures"] = sorted(render(attempt["gdml"], folder, state.name))
        except Exception as error:
            state.log.event("render_failed", state.log.box[0], error=f"{type(error).__name__}: {str(error)[:200]}")
            attempt["pictures"] = []
    return [p for p in attempt["pictures"] if p.name.endswith("_cut.png")][:3]


def _compare_with_figures(state, attempt, folder, most):
    """Compare a geometry with the construction figures. Returns {"verdict", "reason", "findings": [(figure, Finding)],
    "high": [...]} or {} if there is no figure or no picture. The worst verdict over the figures counts."""
    figures = construction_figures(state)[:most]
    pictures = _pictures(state, attempt, folder) if attempt else []
    if not figures or not pictures:
        return {}
    result = {"verdict": None, "reason": "", "findings": []}
    for figure in figures:
        answer = look_at.compare(pictures, figure, state.evidence.folder / "figures", state.name,
                                 _built_parts_text(state, attempt), state.log)
        if answer is None:
            continue
        if result["verdict"] is None or VERDICTS[answer.verdict] < VERDICTS[result["verdict"]]:
            result["verdict"], result["reason"] = answer.verdict, answer.reason
        result["findings"] += [(figure, finding) for finding in answer.findings]
        for finding in answer.findings:
            state.log.event("finding", state.log.box[0], figure=figure["file"], **finding.model_dump())
    result["high"] = [(figure, f) for figure, f in result["findings"] if f.importance == "high"]
    return result if result["verdict"] else {}


@step("look")
def look(state, number, revision=0, most=1):
    """Compare pictures of what is built so far with the figures. The result is kept with the geometry."""
    folder = state.folder / "build" / f"round{state.round}" / f"look{number:02d}_{revision:02d}"
    result = _compare_with_figures(state, state.candidate, folder, most)
    if state.candidate is not None:
        state.candidate["look"] = result
    state.log.event("check", "look", piece=number, revision=revision, verdict=result.get("verdict"),
                    reason=result.get("reason", ""), findings=len(result.get("findings", [])),
                    high=len(result.get("high", [])), figures=len(state.figures))
    return result


@step("look")
def look_again(state, attempt, blocking, number, revision):
    """After a revision: are the differences that were sent back gone? Returns the ones that are."""
    folder = state.folder / "build" / f"round{state.round}" / f"look{number:02d}_{revision:02d}"
    pictures, gone = _pictures(state, attempt, folder), []
    for figure, finding in blocking:
        answer = look_at.resolved(pictures, figure, state.evidence.folder / "figures", state.name, finding, state.log) \
            if pictures else None
        state.log.event("resolved", "look", piece=number, revision=revision, part=finding.part, issue=finding.issue,
                        resolved=bool(answer and answer.resolved), now=answer.now if answer else "no answer")
        if answer and answer.resolved:
            gone.append((figure, finding))
    return gone


def look_loop(state, number, most=1):
    """Look is part of the piece's loop: while it reports an important difference on what is built,
    the piece goes back to the builder, up to max_revisions times. A revision replaces the geometry
    only if Look confirms that at least one of the differences is gone. A difference that survives
    same_finding_tries revisions is recorded as unresolved and no longer sent back.
    Returns True if Look ends without an important difference."""
    tried, revision = {}, 0
    result = look(state, number, 0, most)
    while True:
        blocking = [(figure, f) for figure, f in result.get("high", []) if tried.get(f.part, 0) < state.same_finding_tries]
        if not blocking or revision >= state.max_revisions:
            break
        revision += 1
        for _, finding in blocking:
            tried[finding.part] = tried.get(finding.part, 0) + 1
        attempt = revise(state, blocking, number, revision)
        if attempt is None:
            result = look(state, number, revision, most)          # nothing usable came back: look at what stands
            continue
        gone = look_again(state, attempt, blocking, number, revision)
        state.log.event("revision_checked", "look", piece=number, revision=revision, accepted=bool(gone),
                        gone=[f.part for _, f in gone], asked=[f.part for _, f in blocking])
        if gone:
            state.script, state.candidate = attempt["gdml"].with_suffix(".py").read_text(), attempt
        result = look(state, number, revision, most)
    still = result.get("high", [])
    passed = not still
    state.log.event("piece_look", "look", piece=number, passed=passed, revisions=revision, verdict=result.get("verdict"),
                    open=[f"{f.part}: {f.issue}" for _, f in still])
    return passed, still


# ---------------------------------------------------------------- whole detector

@step("integrate")
def integrate(state):
    """Do the subsystems of the teams sit where the plan puts them? Checked on the joined geometry."""
    if not state.candidate:
        state.log.event("check", "integrate", valid=False)
        return
    team_of = {p.name: p.team for p in state.plan.parts}
    between = [r for r in state.candidate["relation_rows"]
               if (lambda a, b: team_of.get(a) != team_of.get(b))(r["what"].split(" ")[0], r["what"].split(" ")[-1])]
    state.interfaces = between
    state.log.event("check", "integrate", teams=len(plan_teams(state.plan)), interfaces=len(between),
                    met=sum(r["status"] == "met" for r in between), left_out=state.left_out,
                    not_met=[r["what"] for r in between if r["status"] == "not met"])


@step("check_whole_detector")
def check_whole_detector(state):
    """The table of all claims and all statements of the plan against the geometry of this round."""
    if state.candidate:
        state.log.event("check", "check_whole_detector", relations=state.candidate["relations"], **state.candidate["summary"])
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
    """Compare pictures of the whole geometry with every construction figure. The verdict and the
    differences decide whether the run goes on, and go to the teams of the next round."""
    folder = state.folder / "pictures" / f"round{state.round}"
    state.final = _compare_with_figures(state, state.candidate, folder, most=3)
    if state.candidate:
        state.candidate["pictures"] = sorted(folder.glob("*.png")) or state.candidate.get("pictures", [])
        state.candidate["look"] = state.final
    state.log.event("check", "final_look", verdict=state.final.get("verdict"), reason=state.final.get("reason", ""),
                    findings=len(state.final.get("findings", [])), high=len(state.final.get("high", [])),
                    figures=len(state.figures))


@step("round_rule")
def round_rule(state):
    """Keep the best version. The run ends when a full round changed nothing: no new claims, no
    important difference from the figures left, no piece that Look did not pass, nothing left out.
    Two safety stops: the result did not get better for two rounds, or max_rounds is reached."""
    improved = _rank(state.candidate) > _rank(state.best)
    if improved:
        state.best = {**state.candidate, "round": state.round, "left_out": list(state.left_out),
                      "not_passed": list(state.pieces_not_passed)}
    state.unchanged_rounds = 0 if improved else state.unchanged_rounds + 1
    open_now = bool(state.final.get("high")) or bool(state.pieces_not_passed) or bool(state.left_out)
    if state.new_claims == 0 and not open_now:
        state.stopped = "a full round changed nothing: no new claims and no important difference from the figures left"
    elif state.unchanged_rounds >= 2:
        state.stopped = "SAFETY STOP: the result did not get better for two rounds, with differences still open"
    elif state.round >= state.max_rounds:
        state.stopped = f"SAFETY STOP: the limit of {state.max_rounds} rounds was reached, with differences still open"
    state.log.event("round", "round_rule", round=state.round, new_claims=state.new_claims, improved=improved,
                    rank=list(_rank(state.candidate)), open=open_now, another=not state.stopped, stopped=state.stopped)
    return not state.stopped


# ---------------------------------------------------------------- outside the system

@step("evaluator")
def evaluator(state):
    """Grade the finished run against the public code, if a repository is given. Never part of the run."""
    if not state.public_code or not state.best:
        state.log.event("check", "evaluator", graded=False, why="no public code given" if state.best else "nothing was built")
        return
    state.grade = grade(state.name, state.public_code, state.best, state.plan, state.folder / "evaluation", state.log)
    (state.folder / "evaluation_report.md").write_text(grade_report(state.name, state.public_code, state.grade))
    state.log.event("check", "evaluator", graded=True, findings=len(state.grade["findings"]),
                    files_read=len(state.grade["files"]))


@step("system_audit")
def system_audit(state):
    """One line per run for the tables across runs (python -m g4geoagent.audit)."""
    state.log.box = None
    (state.folder / "audit.json").write_text(json.dumps(audit_run(state.folder), indent=1))


# ---------------------------------------------------------------- the run

def build_round(state):
    """Teams → Build → Measure → Look, piece by piece, then the checks of the whole detector.

    The first round builds everything. A later round goes on from the best geometry: it builds what
    was left out and takes up the differences that the final look found."""
    if state.round == 1 or state.script is None:
        state.script, state.done, state.left_out, state.candidate = None, [], [], None
    state.attempts, state.pieces_not_passed, state.open_findings = [], [], []
    state.hints = look_at.as_feedback(state.final.get("findings", []))        # what the final look of the round before found
    todo = [(team_name, [p for p in parts if p not in state.done]) for team_name, parts in pieces(state)]
    todo = [(team_name, parts) for team_name, parts in todo if parts]
    state.left_out = []
    for number, (team_name, parts) in enumerate(todo, 1):
        build(state, team_name, parts, number)
        if not state.candidate:
            look(state, number)                         # nothing to look at yet: the step says so
            continue
        passed, still = look_loop(state, number)
        if not passed:
            state.pieces_not_passed.append(number)
            state.open_findings += [f"{f.part}: {f.issue}" for _, f in still]
    if state.round > 1 and state.candidate:
        # the differences of the last final look, against every figure
        state.log.enter(("build",))
        measure_vs_claims(state, None, None)
        passed, still = look_loop(state, 90, most=3)
        if not passed:
            state.open_findings = [f"{f.part}: {f.issue}" for _, f in still]
    integrate(state)
    check_whole_detector(state)
    run_geant4(state)
    final_look(state)


def run(folder, documents, name, max_rounds=5, searches_per_round=1, seed=None, public_code=None, max_revisions=10):
    """Run the whole system on the starting `documents` (text files and PDFs). Returns the final state."""
    folder = Path(folder)
    if (folder / "log.jsonl").exists():         # an earlier run in this folder is replaced
        shutil.rmtree(folder)
    log = RunLog(folder / "log.jsonl")
    state = State(folder=folder, name=name, log=log, evidence=Evidence(folder / "evidence", log),
                  max_rounds=max_rounds, searches_per_round=searches_per_round, seed=seed, public_code=public_code,
                  max_revisions=max_revisions)
    if seed is not None:
        llm.DEFAULT_OPTIONS["seed"] = seed
    names = [state.evidence.add_starting(path) for path in documents]
    state.unread = [n for n in names if Path(n).suffix in (".txt", ".md")]

    read_documents(state)
    construction_figures_step(state)
    graph_builder(state)
    coordinator(state)
    while True:
        state.round += 1
        team(state)
        if state.searches:
            research(state)
            if state.unread:
                read_documents(state)
                construction_figures_step(state)
                graph_builder(state)
                coordinator(state)
            team_continues(state)
        build_round(state)
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


def construction_figures_step(state):
    """Have the figures of the evidence folder judged before the Coordinator plans. Part of the reading."""
    if [f for f in state.evidence.figures() if f["file"] not in {j["file"] for j in state.figures_judged}]:
        read_figures(state)


@step("reader_A", "reader_B")
def read_figures(state):
    """The readers look at the new figures and say which ones show how the detector is built."""
    construction_figures(state)
    compare_figures(state)


@step("compare")
def compare_figures(state):
    state.log.event("check", "compare_figures", figures=len(state.figures_judged), construction=len(state.figures))


if __name__ == "__main__":
    args = sys.argv[1:]

    def option(name, default):
        if name in args:
            value = args[args.index(name) + 1]
            del args[args.index(name):args.index(name) + 2]
            return value
        return default

    name = option("--name", None)
    rounds, searches = int(option("--rounds", 5)), int(option("--searches", 1))
    revisions = int(option("--revisions", 10))
    seed, code = option("--seed", None), option("--public-code", None)
    folder, documents = Path(args[0]), [Path(a) for a in args[1:]]
    final = run(folder, documents, name or documents[0].stem, rounds, searches, None if seed is None else int(seed), code,
                revisions)
    print((folder / "evidence_report.md").read_text()[:3000])
