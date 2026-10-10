"""Documents that the steps of the system exchange."""

from typing import Literal

from pydantic import BaseModel, Field


class Claim(BaseModel):
    """One value stated in a document, with the place it was found."""

    part: str = Field(description="Name of the part, lower case with underscores, e.g. 'crystal'")
    quantity: str = Field(description="What is stated, e.g. 'diameter', 'height', 'material', 'groove_depth'")
    value: float | str = Field(description="The number as written, or text for materials and relations")
    unit: str = Field(default="", description="Unit as written, e.g. 'mm'. Empty if there is none")
    uncertainty: float = Field(default=0.0, description="0 for values stated in text")
    category: Literal["shape", "position", "material", "count", "not_geometry"] = Field(
        description="'not_geometry' for values that are not built: voltages, temperatures, "
                    "concentrations, layers that are not separate volumes")
    relative_to: str = Field(default="", description="For positions: the part or frame it is measured from")
    source: str = Field(description="File name of the document")
    quote: str = Field(description="The exact words from the document that state this value")


class Part(BaseModel):
    name: str
    description: str = Field(description="One sentence: what it is and its basic shape")
    inside: str = Field(description="Name of the part or medium that contains it, e.g. 'world'")


class Gap(BaseModel):
    """A value needed to build a part that the documents do not give."""

    part: str
    quantity: str
    reason: str = Field(description="Why it is needed")


class Reading(BaseModel):
    """What one reader extracted from the documents."""

    parts: list[Part]
    claims: list[Claim]
    gaps: list[Gap] = Field(default_factory=list)


class MoreClaims(BaseModel):
    """Claims added in a second look at the documents."""

    claims: list[Claim]


class Verdict(BaseModel):
    """The reader's decision about one number that no claim covers."""

    item: int = Field(description="Number of the item in the list that was sent")
    verdict: Literal["missed_value", "not_construction"] = Field(
        description="'missed_value' if it describes how the detector is built, otherwise 'not_construction'")
    claim: Claim | None = Field(default=None, description="The claim, only for 'missed_value'")


class Verdicts(BaseModel):
    verdicts: list[Verdict]


class Outline(BaseModel):
    """The parts of a detector, listed before a long document is read in pieces."""

    parts: list[Part]


class Repair(BaseModel):
    item: int
    quote: str = Field(description="Exact wording copied from one of the offered sentences, containing the "
                                   "value. Empty to withdraw the claim")


class Repairs(BaseModel):
    repairs: list[Repair]


class Check(BaseModel):
    item: int
    verdict: Literal["confirmed", "wrong", "not_construction"] = Field(
        description="'confirmed' if the sentence states this about how the detector is built; 'wrong' if the "
                    "sentence does not say this; 'not_construction' if it is not about the construction")


class Checks(BaseModel):
    checks: list[Check]
