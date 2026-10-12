"""Write a hand list of a paper: the construction values and the relations it states.

Used by Claude on 2026-10-12 for 20 further papers. Each list was written from sentences that a program picked
out of the paper's text (those with sizes, counts and words of arrangement), not from reading the whole paper,
in two to three minutes per paper, and BEFORE any reader was run on that paper. Not checked by a detector expert.
"""
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
HEAD_V = ("# Construction values listed by hand (Claude, 2026-10-12; from sentences picked by a program, written before any\n"
          "# reader ran on this paper; not checked by a detector expert).\n"
          "# value: the number (alt: another way it is written). key: a word that must appear in the claim. optional: fine to leave out.\n")
HEAD_R = ("# Relations between parts that the paper states, listed by hand (Claude, 2026-10-12; from sentences picked by a\n"
          "# program, written before any reader ran on this paper; not checked by a detector expert).\n"
          "# family: nest = the object is within the subject; attach = mounted on or attached to, either way round;\n"
          "#         any = any relation between the two, either way round; otherwise the named relation exactly.\n")


def write(name, detector, values, relations):
    """values: [(value, key, what)] or [(value, key, what, alt)]; relations: [(subject, object, family, what)]."""
    lines = [HEAD_V + f"# detector: {detector}"]
    for v in values:
        extra = f", alt: {v[3]}" if len(v) > 3 else ""
        lines.append("- {value: %s%s, key: %s, what: %s}" % (v[0], extra, json.dumps(v[1]), json.dumps(v[2])))
    (ROOT / "experiments/gold" / f"{name}.yaml").write_text("\n".join(lines) + "\n")
    lines = [HEAD_R + f"# detector: {detector}"]
    lines += ["- {subject: %s, object: %s, family: %s, what: %s}" % (json.dumps(s), json.dumps(o), f, json.dumps(w)) for s, o, f, w in relations]
    (ROOT / "experiments/gold_relations" / f"{name}.yaml").write_text("\n".join(lines) + "\n")
    return len(values), len(relations)
