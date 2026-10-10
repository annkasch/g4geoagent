"""The claim template for the knowledge graph: parts, their properties, and the relations between parts.

Every record carries the words of the document it comes from. Fixed lists are used
wherever a program has to act on the entry.
"""

from typing import Literal

from pydantic import BaseModel, Field

SHAPES = ("cylinder", "tube", "box", "sphere", "plate", "other", "not_stated")
QUANTITIES = ("diameter", "radius", "height", "length", "width", "thickness", "mass", "volume", "count",
              "material", "density", "enrichment", "other")
RELATIONS = ("contains", "surrounds", "encloses", "concentric_with", "at_bottom_of", "at_top_of", "centred_in",
             "mounted_on", "attached_to", "outside", "consists_of", "next_to")


class PartRecord(BaseModel):
    name: str = Field(description="Short name in lower case with underscores, singular: 'water_tank', 'pmt'")
    also_called: list[str] = Field(default_factory=list, description="Other names and abbreviations used for it")
    what: str = Field(description="One sentence: what it is")
    shape: Literal["cylinder", "tube", "box", "sphere", "plate", "other", "not_stated"] = "not_stated"
    features: list[str] = Field(default_factory=list, description="Descriptive words of the document about how it is "
                                "built: 'hollow', 'double-walled', 'vacuum-insulated', 'domed ends', 'encapsulated', ...")
    detail: Literal["sensitive", "main_structure", "small_part"] = Field(
        description="'sensitive' for the detectors that measure; 'main_structure' for vessels, shields and large "
                    "structures; 'small_part' for supports, cables, electronics")
    about: str = Field(description="Which detector or experiment this part belongs to, as the document names it")
    quote: str = Field(description="Exact words of the document that introduce this part")


class Property(BaseModel):
    of: str = Field(description="Name of the part or material the value belongs to. The amount of a liquid belongs to the liquid, not to its vessel")
    quantity: Literal["diameter", "radius", "height", "length", "width", "thickness", "mass", "volume", "count",
                      "material", "density", "enrichment", "other"]
    quantity_other: str = Field(default="", description="What it is, if quantity is 'other'")
    which: Literal["outer", "inner", "total", "each", "not_stated"] = Field(
        default="not_stated", description="'each' for one item of a repeated part, 'total' for all of them together")
    value: float | str = Field(description="The number as written, or text for a material")
    unit: str = ""
    wording: Literal["exact", "about", "at_least", "at_most", "up_to"] = Field(
        default="exact", description="'about' for approximately or ~, 'at_least' for more than, 'up_to' for up to")
    built: bool = Field(default=True, description="false for values that are not part of the geometry: voltages, temperatures, rates")
    about: str = Field(description="Which detector or experiment the value describes")
    quote: str = Field(description="Exact words of the document that state the value")


class Relation(BaseModel):
    subject: str
    relation: Literal["contains", "surrounds", "encloses", "concentric_with", "at_bottom_of", "at_top_of", "centred_in",
                      "mounted_on", "attached_to", "outside", "consists_of", "next_to"]
    object: str
    count: int | None = Field(default=None, description="For 'consists_of' and repeated parts: how many, if stated")
    about: str = Field(description="Which detector or experiment the statement describes")
    quote: str = Field(description="Exact words of the document that state this relation")


class Extraction(BaseModel):
    """What one reader takes from a document."""

    parts: list[PartRecord]
    properties: list[Property]
    relations: list[Relation]
