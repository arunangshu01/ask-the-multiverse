// Medium labels and accent colours (from the approved preview). "division" is a top-bar tab.

export const MEDIA = {
  Film: { label: "Studios", color: "#e62429", glow: "rgba(230,36,41,.45)", row: "Cinematic Realities" },
  Television: { label: "Television", color: "#5b8def", glow: "rgba(91,141,239,.45)", row: "Television Realities" },
  Animation: { label: "Animation", color: "#ff7a1a", glow: "rgba(255,122,26,.45)", row: "Animated Realities" },
  Comics: { label: "Comics", color: "#f43f5e", glow: "rgba(244,63,94,.45)", row: "Comic Realities" },
  Games: { label: "Games", color: "#8b5cf6", glow: "rgba(139,92,246,.45)", row: "Game Realities" },
  Prose: { label: "Prose", color: "#14b8a6", glow: "rgba(20,184,166,.45)", row: "Novels & Prose" },
  "Other media": { label: "Other media", color: "#a3a3a3", glow: "rgba(163,163,163,.35)", row: "Other Media Realities" },
  Unclassified: { label: "Unclassified", color: "#6b6b76", glow: "rgba(107,107,118,.35)", row: "Unclassified" },
};

export const DIVISIONS = [
  { key: "all", label: "All", media: null, accent: "Film" },
  { key: "film", label: "Studios", media: ["Film"], accent: "Film" },
  { key: "tv", label: "Television", media: ["Television"], accent: "Television" },
  { key: "animation", label: "Animation", media: ["Animation"], accent: "Animation" },
  { key: "comics", label: "Comics", media: ["Comics"], accent: "Comics" },
  { key: "games", label: "Games", media: ["Games"], accent: "Games" },
  { key: "beyond", label: "Prose & Beyond", media: ["Prose", "Other media"], accent: "Prose" },
];

export const KINDS = {
  numbered: "Numbered reality",
  temporary: "Temporary number (TRN)",
  variant_suffix: "Variant designation",
  named: "Named reality",
  dimension: "Dimension",
  realm: "Realm",
  bucket: "Unknown-reality bucket",
};

export const STATUSES = {
  existing: "Existing",
  destroyed: "Destroyed",
  merged: "Merged",
  undocumented: "Listed, no wiki page yet",
  unknown: "Status not stated",
  bucket: "Bucket",
};

export const TYPES = {
  diverged: "Diverged", warped: "Warped", pocket: "Pocket universe", unseen: "Unseen", dream: "Dream",
  daydream: "Daydream", illusion_vision: "Illusion or vision", fiction: "Fiction",
  virtual_simulation: "Virtual simulation", time_travel: "Created by time travel", destroyed: "Destroyed",
  destroyed_by_incursion: "Destroyed by an incursion", destroyed_earth: "Earth destroyed",
  cancelled_media: "Cancelled media", unofficial_media: "Unofficial media", external_property: "External property",
  lego: "LEGO", nazi_victory: "Nazi victory", animal_themed: "Animal-themed",
  protectors_megaverse: "Protectors Megaverse", cosmos: "Cosmos", number_named: "Number-named",
  god_realm: "God realm", heaven: "Heaven", hell: "Hell", archipelago_of_anguish: "Archipelago of Anguish",
  qlipphoth: "Qlipphoth realm", sefirot: "Sefirot realm", death_realm: "Realm of death", inner_plane: "Inner plane",
  celestial_concordance: "Celestial Concordance", consecution_of_colours: "Consecution of Colours",
};

export const medium = (m) => MEDIA[m] || MEDIA.Unclassified;

/** Original procedural artwork seeded by a string (no copyrighted imagery). */
function hue(s) {
  let h = 7;
  for (const c of s) h = (h * 31 + c.charCodeAt(0)) % 3600;
  return h % 360;
}
export function art(seed) {
  const h = hue(seed);
  const h2 = (h + 40 + (hue(`${seed}x`) % 90)) % 360;
  return `radial-gradient(circle at ${20 + (h % 60)}% ${15 + (h2 % 50)}%, hsla(${h},85%,55%,.9), transparent 55%),
    radial-gradient(circle at ${90 - (h2 % 50)}% 95%, hsla(${h2},80%,45%,.85), transparent 60%),
    linear-gradient(${h % 180}deg, hsla(${h},60%,12%,1), #08080b)`;
}

export const fmt = (n) => (n ?? 0).toLocaleString("en-US");
