You read documents about a particle detector and write down, as claims, what
they say about how the detector is physically built. Someone else will build a
geometry of the detector from your claims alone, without seeing the documents.
A program will check each claim against the documents.

What to extract

- The parts of the detector and what each one sits inside.
- For each part: dimensions, positions, how many there are, what it is made of
  or filled with, and its mass or volume if stated.

What to leave out completely. Write no claim for:

- physics goals and results: event numbers, rates, energies, efficiencies,
  resolutions, sensitivities, half-lives, exposures, backgrounds;
- dates, years, run periods, funding and collaboration facts;
- citation numbers, figure, table, section and page numbers, author details;
- isotopes or materials that are only mentioned as backgrounds or as the
  subject of the physics, not as what a part is made of.

Most of a physics paper is not about construction. If the documents say little
about how the detector is built, return few claims. That is the correct answer.

Rules

1. One claim per stated value. If a sentence states three numbers about the
   hardware, write three claims.
2. Copy the value and unit as written. Do not convert units, round, or calculate.
3. `quote` is the exact wording from the document that states the value, copied
   character by character from one place, and it must contain the value. Keep
   it short. Never join two passages with "..." and never reword. If a count
   is written as a word ("two shrouds"), quote the word and give the number
   as the value. Do not write a claim for a value the text only implies.
4. Use the category `not_geometry` only for properties of the hardware that are
   not built as a volume: operating voltages and temperatures, and the thickness
   of contacts, coatings or dead layers.
5. What a part is made of gets the category `material`.
6. Statements about where a part is (inside, at the bottom, centred on) are
   claims with category `position`. Their value is text.
7. Use one name per part, lower case with underscores, in every claim about it.
8. List in `gaps` the values that are needed to build a part but that the
   documents do not give. Do not guess such values.
9. Do not use anything you know about this detector from elsewhere.

{procedure}

Answer with one JSON object and nothing else. It must fit this schema:

{schema}
