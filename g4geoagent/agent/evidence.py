"""The evidence folder of a run: the starting documents and everything found online.

Every file that comes from outside is listed in sources.jsonl with its URL and
the date it was fetched. Fetching is only possible from the allowed sources.
"""

import datetime
import json
import shutil
from pathlib import Path
from urllib.parse import urlparse

import requests

# Documents-only mode: scientific literature, no code hosts. First version: INSPIRE and arXiv.
ALLOWED_HOSTS = {"inspirehep.net", "arxiv.org", "export.arxiv.org"}
TEXT_SUFFIXES = {".md", ".txt"}


class NotAllowed(Exception):
    pass


class Evidence:
    def __init__(self, folder, log=None):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.log = log

    def add_starting(self, path):
        """Copy a starting document into the folder. A PDF goes through step 1 (agent/documents.py). Returns the name of
        the text file to read."""
        target = self.folder / Path(path).name
        shutil.copy(path, target)
        self._record(target.name, origin="starting document", url="")
        if target.suffix != ".pdf":
            return target.name
        # a PDF goes through step 1: its text is written beside it as <name>.txt, its figures under figures/
        from g4geoagent.agent.documents import read_pdf
        result = read_pdf(target, self.folder)
        self._record(result["text"], origin="starting document", url="", made_from=target.name)
        if self.log:
            self.log.event("step1", "evidence", file=target.name, pages=result["pages"], figures=len(result["figures"]), tables=result["tables"])
        return result["text"]

    def add_figures(self, pdf_name):
        """Save the figures of a PDF of the folder under figures/, with page and caption."""
        from g4geoagent.reviewer.look import extract_figures
        try:
            figures = extract_figures(self.folder / pdf_name, self.folder / "figures")
        except Exception as error:
            figures = []
            if self.log:
                self.log.event("figures_failed", "evidence", file=pdf_name, error=f"{type(error).__name__}: {str(error)[:200]}")
        listing = self.folder / "figures" / "all_figures.jsonl"
        if figures:
            with listing.open("a") as f:
                f.writelines(json.dumps(figure) + "\n" for figure in figures)
        return figures

    def figures(self):
        """Every figure saved so far: [{file, page, caption, source}]."""
        listing = self.folder / "figures" / "all_figures.jsonl"
        return [json.loads(line) for line in listing.read_text().splitlines()] if listing.exists() else []

    def documents(self, names=None):
        """{file name: text} of the text documents, all or only `names`."""
        files = sorted(p for p in self.folder.iterdir() if p.suffix in TEXT_SUFFIXES)
        return {p.name: p.read_text() for p in files if names is None or p.name in names}

    def sources(self):
        file = self.folder / "sources.jsonl"
        return [json.loads(line) for line in file.read_text().splitlines()] if file.exists() else []

    def fetch(self, url, **parameters):
        """GET `url` from an allowed source. Every attempt is written to the run log."""
        host = urlparse(url).hostname or ""
        allowed = host in ALLOWED_HOSTS
        if self.log:
            self.log.event("fetch", "research", url=url, parameters=parameters, allowed=allowed)
        if not allowed:
            raise NotAllowed(f"{host} is not an allowed source")
        response = requests.get(url, params=parameters, timeout=120,
                                headers={"User-Agent": "g4geoagent (research prototype)"})
        response.raise_for_status()
        return response

    def save(self, name, content, url, **details):
        """Save something fetched from `url` under `name` and list it in sources.jsonl."""
        target = self.folder / name
        target.write_bytes(content) if isinstance(content, bytes) else target.write_text(content)
        self._record(name, origin="found by research", url=url, **details)
        return name

    def _record(self, name, **details):
        entry = {"file": name, "date": datetime.date.today().isoformat(), **details}
        with (self.folder / "sources.jsonl").open("a") as f:
            f.write(json.dumps(entry) + "\n")
