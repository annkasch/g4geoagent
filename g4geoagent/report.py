"""The evidence report of a run: what was built, on which evidence, and what stayed open."""

from g4geoagent.agent import readers
from g4geoagent.architecture import BOXES


def _cell(text, limit=90):
    text = " ".join(str(text).split()).replace("|", "/")
    return text if len(text) <= limit else text[:limit - 1] + "…"


def evidence_report(state, architecture_problems):
    best, lines = state.best, [f"# Evidence report: {state.name}", ""]
    add = lines.append
    add("Mode: documents only. Models: readers " + ", ".join(m for m, _ in readers.READERS.values())
        + "; all models are free LBL-hosted ones.")
    look = (best or {}).get("look") or {}
    if state.stopped.startswith("SAFETY STOP"):
        add("")
        add(f"**The run did not finish by its own rule. {state.stopped}.**")
    add("")
    add(f"Rounds: {state.round}. The run stopped because: {state.stopped}.")
    add("")
    add("## Does it look like the detector?")
    if look:
        add(f"- Verdict of the final look against the figures: **{look['verdict'].replace('_', ' ')}**. {look.get('reason', '')}")
        add(f"- Important differences still open: {len(look.get('high', []))}.")
        for _, finding in look.get("high", []):
            add(f"  - **{finding.part}**: {finding.issue}")
    else:
        add("- No figure was available to compare with, or nothing was built. Nothing can be said." )
    if best and best.get("not_passed"):
        add(f"- Pieces that Look did not pass after all allowed revisions: {len(best['not_passed'])}.")
    add("")
    add("## Result")
    if best:
        s, r, report = best["summary"], best["relations"], best["report"]
        add(f"- Geometry: `detector.gdml`, from round {best['round']}, {len(report.get('parts', [])) - 1} placed volumes.")
        add(f"- Geant4: {'loads without overlaps or warnings' if report['ok'] else 'PROBLEMS: ' + _cell(report['overlaps'] or report['problems'] or report['error'], 200)}.")
        add(f"- Claims that describe the construction: {s['claims']}. Met in the geometry: {s['met']}. Not met: {s['not met']}. "
            f"Shown but not measurable: {s['not measurable']}. Not shown by the builder: {s['not shown']}.")
        add(f"- Statements of the layout plan: {sum(r.values())}. Met: {r['met']}. Not met: {r['not met']}. Not shown: {r['not shown']}.")
        if best.get("left_out"):
            add(f"- **Parts left out** because their piece did not become valid: {', '.join(best['left_out'])}.")
        if best.get("pictures"):
            add("- Pictures: " + ", ".join(f"`{p.relative_to(state.folder)}`" for p in best["pictures"]) + ".")
    else:
        add("- No geometry that loads in Geant4 was produced.")
    add("")
    add("## All differences from the figures")
    for figure, finding in look.get("findings", []):
        add(f"- ({finding.importance}) **{finding.part}**: {finding.issue} Asked for: {finding.fix} [{figure['file']}]")
    if not look.get("findings"):
        add("None listed.")
    add("")
    add("## Important and unconfirmed")
    estimates = [e for e in (best["notes"].get("estimates", []) if best else []) if isinstance(e, dict)]
    if estimates:
        add("Values the builder chose because no claim gives them:")
        add("")
        add("| Part | Quantity | Value | Reason |")
        add("|---|---|---|---|")
        for e in estimates:
            add(f"| {_cell(e.get('part', ''))} | {_cell(e.get('quantity', ''))} | {_cell(e.get('value', ''))} "
                f"{_cell(e.get('unit', ''))} | {_cell(e.get('reason', ''))} |")
    else:
        add("The builder listed no estimates." if best else "Nothing was built.")
    add("")
    if state.plan:
        add("## Layout plan and how the geometry follows it")
        add("")
        add("| Part | Inside | Form | Detail | Team |")
        add("|---|---|---|---|---|")
        for p in state.plan.parts:
            add(f"| {_cell(p.name, 40)} | {_cell(p.inside, 40)} | {p.form} | {p.detail} | {_cell(p.team, 30)} |")
        add("")
        if best:
            add("| Statement | Check |")
            add("|---|---|")
            for row in best["relation_rows"]:
                add(f"| {_cell(row['what'])} | {row['status']}{': ' + _cell(row['why'], 80) if row['why'] else ''} |")
            add("")
    add("## Claims and how the geometry meets them")
    add("")
    add("| Id | Part | Quantity | Value | Source | Check | Expected | Measured |")
    add("|---|---|---|---|---|---|---|---|")
    rows = {r["id"]: r for r in best["rows"]} if best else {}
    for key, claim in state.built_claims().items():
        r = rows.get(key, {})
        number = lambda v: "" if v is None else f"{v:g} {r.get('unit', '')}"
        add(f"| {key} | {_cell(claim.part, 30)} | {_cell(claim.quantity, 30)} | {_cell(claim.value, 30)} {_cell(claim.unit, 10)} | "
            f"{_cell(claim.source, 30)} | {r.get('status', '')}{': ' + _cell(r['why'], 50) if r.get('why') else ''} | "
            f"{number(r.get('expected'))} | {number(r.get('measured'))} |")
    add("")
    add("## Research")
    if not state.research:
        add("No search was made.")
    for r in state.research:
        add(f"- Round {r['round']}, searched for **{_cell(r['quantity'])}** of {_cell(r['part'])} (query: \"{_cell(r['query'])}\"). "
            f"{r['candidates']} new papers offered. Outcome: {_cell(r['outcome'], 200)}"
            + (f" Saved: {', '.join('`' + f + '`' for f in r['files'])}, with {r.get('figures', 0)} figures." if r["file"] else ""))
    add("")
    add("Sources in the evidence folder:")
    for s in state.evidence.sources():
        add(f"- `{s['file']}`: {s['origin']}, {s['date']}" + (f", {s['url']}" if s.get("url") else ""))
    add("")
    add(f"Figures: {len(state.figures_judged)} saved, {len(state.figures)} show how the detector is built:")
    for f in state.figures:
        add(f"- `figures/{f['file']}` ({f['source']}, page {f['page']}): {_cell(f['shows'], 200)}")
    add("")
    add("## Disputed and dropped claims")
    add(f"{len(state.disputed)} claims were made by one reader and rejected by the other. "
        f"{len(state.dropped)} were dropped because their quote could not be verified.")
    for claim in state.disputed[:30]:
        add(f"- disputed: {_cell(claim.part, 30)} / {_cell(claim.quantity, 30)} = {_cell(claim.value, 30)} {claim.unit} ({claim.source})")
    add("")
    add("## What each part of the system does in this version")
    for name, box in BOXES.items():
        if box["kind"] != "data":
            add(f"- **{box['title']}**{' (not built)' if box.get('state') == 'stub' else ''}: {box['first']}")
    add("")
    add("## Did the run follow the architecture?")
    add("Yes." if not architecture_problems else "No:")
    lines += [f"- {problem}" for problem in architecture_problems]
    return "\n".join(lines) + "\n"
