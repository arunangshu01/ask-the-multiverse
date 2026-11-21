"""Category -> tag mappings, taken from the Marvel Database category tree
(Category:Realities and Category:Dimensions subcategories, Nov 2026)."""

from __future__ import annotations

import re

MEDIA = ("Comics", "Film", "Television", "Animation", "Games", "Prose", "Other media")

# Realities by Type / Status and other Category:Realities subcategories.
REALITY_TYPE_CATEGORIES = {
    "Pocket Universes": "pocket",
    "Unseen Realities": "unseen",
    "Realities Manifested in Dreams": "dream",
    "Realities Manifested in Daydreams": "daydream",
    "Realities Manifested in Illusions and Visions": "illusion_vision",
    "Realities Manifested in Fiction": "fiction",
    "Realities Manifested in Virtual Simulations": "virtual_simulation",
    "Realities created due to Time Travel": "time_travel",
    "Destroyed Realities": "destroyed",
    "Destroyed by Incursions": "destroyed_by_incursion",
    "Realities with Destroyed Earths": "destroyed_earth",
    "Realities from Cancelled Media": "cancelled_media",
    "Realities from Unofficial Marvel Media": "unofficial_media",
    "Realities of External Properties": "external_property",
    "LEGO Realities": "lego",
    "Nazi Victory Universes": "nazi_victory",
    "Animal-Themed Realities": "animal_themed",
    "Protectors Megaverse Realities": "protectors_megaverse",
    "Cosmoses": "cosmos",
}
STATUS_CATEGORIES = {
    "Existing Realities": "existing",
    "Destroyed Realities": "destroyed",
    "Merged Realities": "merged",
}
NEEDS_NUMBER_CATEGORY = "Needs Reality Number"
# Reality Template `Status` field values (lower-cased) -> status.
STATUS_FIELD_VALUES = {"existing": "existing", "active": "existing", "destroyed": "destroyed",
                       "merged": "merged"}

DIVERGED = re.compile(r"^(.+?) Diverged Realities$")
WARPED = re.compile(r"^(.+?) Warped Realities$")
DESTROYED_BY = re.compile(r"^Earths Destroyed by the (.+)$")
DEBUT_YEAR = re.compile(r"^(\d{4}) (?:Reality|Location) Debuts$")

# Category:Dimensions subcategories whose members are themselves dimensions or realms.
DIMENSION_TYPE_CATEGORIES = {
    "Dimensions": None,
    "Destroyed Dimensions": "destroyed",
    "Number-Named Dimensions": "number_named",
    "Pocket Universes": "pocket",
    "God Realms": "god_realm",
    "Cities of the Gods": "god_realm",
    "Heaven": "heaven",
    "Seven Capital Cities of Heaven": "heaven",
    "Hell": "hell",
    "Archipelago of Anguish and Redemption": "archipelago_of_anguish",
    "Qlipphoth Realms": "qlipphoth",
    "Sefirot Realms": "sefirot",
    "Realm of Death": "death_realm",
    "Dream Dimensions": "dream",
    "Dream Dimension": "dream",
    "Inner Planes": "inner_plane",
    "Celestial Concordance": "celestial_concordance",
    "Consecution of Colours": "consecution_of_colours",
}
# Subcategories that group the places *inside* one dimension. Membership alone
# does not make a page a dimension; it names the containing dimension.
DIMENSION_CONTAINER_CATEGORIES = {
    "Dimension Z", "Dreamtime", "Earthspace", "Everinnye", "Hades (Underworld)", "K'un-Lun",
    "Limbo (Otherplace)", "Microverse", "Multiverse", "Negative Zone", "Omniverse", "Underspace",
}
# Subcategories that hold beings or objects, never places.
DIMENSION_NON_PLACE_CATEGORIES = {"Dimensional Rulers", "Interdimensional Races",
                                  "Interdimensional Travelers"}
DIMENSION_PLACE_CATEGORIES = {"Dimensional Gateways", "Dimensional Barriers"}

REALM_TAGS = {"god_realm", "heaven", "hell", "archipelago_of_anguish", "qlipphoth", "sefirot",
              "death_realm", "inner_plane"}

# Infobox templates (Marvel Database:<name>) and what they mean for this index.
REALITY_TEMPLATES = {"Reality Template"}
PLACE_TEMPLATES = {"Location Template"}
REJECT_TEMPLATES = {
    "Character Template": "character", "Team Template": "team",
    "Organization Template": "organization", "Race Template": "race", "Item Template": "item",
    "Event Template": "event", "Story Arc Template": "story arc", "Comic Template": "comic",
    "Vehicle Template": "vehicle", "Gallery Template": "gallery",
}

TAG_LABELS = {
    "diverged": "Diverged", "warped": "Warped", "pocket": "Pocket universe", "unseen": "Unseen",
    "dream": "Dream", "daydream": "Daydream", "illusion_vision": "Illusion or vision",
    "fiction": "Fiction", "virtual_simulation": "Virtual simulation",
    "time_travel": "Created by time travel", "destroyed": "Destroyed",
    "destroyed_by_incursion": "Destroyed by an incursion", "destroyed_earth": "Earth destroyed",
    "cancelled_media": "Cancelled media", "unofficial_media": "Unofficial media",
    "external_property": "External property", "lego": "LEGO", "nazi_victory": "Nazi victory",
    "animal_themed": "Animal-themed", "protectors_megaverse": "Protectors Megaverse",
    "cosmos": "Cosmos", "number_named": "Number-named", "god_realm": "God realm",
    "heaven": "Heaven", "hell": "Hell", "archipelago_of_anguish": "Archipelago of Anguish",
    "qlipphoth": "Qlipphoth realm", "sefirot": "Sefirot realm", "death_realm": "Realm of death",
    "inner_plane": "Inner plane", "celestial_concordance": "Celestial Concordance",
    "consecution_of_colours": "Consecution of Colours", "container": "Contains other dimensions",
}
