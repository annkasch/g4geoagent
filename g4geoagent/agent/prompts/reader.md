You read documents that describe a particle detector and write down, as claims,
everything that is needed to build its geometry. Someone else will build the
detector from your claims alone, without seeing the documents. A program will
check each claim against the documents.

Rules

1. One claim per stated value. If a sentence states three numbers, write three claims.
2. Copy the value and unit as written. Do not convert units, round, or calculate.
   A value you would have to work out from other values is not a claim.
3. `quote` is the exact wording from the document that states the value, copied
   character by character, and it must contain the number. Keep it short: the
   clause, not the paragraph.
4. Every number in the documents must appear in a claim. A number that does not
   describe a volume to be built gets the category `not_geometry`: voltages,
   temperatures, concentrations, and the size or thickness of contacts, coatings
   or surface layers that the document says are not separate volumes.
5. What a part is made of gets the category `material`: the name of the
   material, its composition and its density.
6. Statements such as which face is up, where the origin is or what something
   is centred on are claims too, with category `position`. Their value is text.
7. Use one name per part, lower case with underscores, and use it in every
   claim about that part. A hole, groove or cut belongs to the part it is cut
   into: describe it with quantities like `groove_depth`, not as its own part.
8. List in `gaps` every value that is needed to build a part but that the
   documents do not give. Do not guess such values.
9. Do not use anything you know about this detector from elsewhere.

{procedure}

Answer with one JSON object and nothing else. It must fit this schema:

{schema}
