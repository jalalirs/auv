// The places this platform is for, whether or not they exist yet.
//
// Listed so the shape of the product is visible before the whole of it is
// built, and so that nobody mistakes a catalogue with four entries for the
// product. Each says what it is for, what building it takes, and what it
// stands on — real data or constructed — because those are the questions a
// person asks before deciding whether to wait for it.
//
// Nothing here is a place. A place is founded on the platform, published as a
// package, and granted; these are intentions, and the page shows them as such.

export type Standing = "surveyed" | "constructed" | "mixed";

export interface Environment {
  key: string;
  name: string;
  where: string;
  /** What a dive there is for. */
  purpose: string;
  /** What it takes to build, in a sentence. */
  takes: string;
  standing: Standing;
  /** The public data it would be built from, so the claim can be checked. */
  sources: string[];
  /** The slug of the platform place it will become, when one exists. */
  becomes?: string;
}

export const ENVIRONMENTS: Environment[] = [
  {
    key: "looe-key-full",
    name: "Looe Key, the whole square",
    where: "Florida Keys, United States",
    purpose: "Reef survey and station-keeping over real spur and groove, with the sand, rubble and seagrass around it.",
    takes: "Colonies drawn to the monitoring densities outside the surveyed strip, scanned coral shapes, and fish.",
    standing: "surveyed",
    sources: ["USGS SQUID-5 2022 orthomosaic and 1 cm DEM", "NOAA NCEI bathymetry", "FWC CREMP and Unified Reef Map"],
    becomes: "looe-key",
  },
  {
    key: "kaneohe-reef",
    name: "Kāneʻohe Bay patch reefs",
    where: "Oʻahu, Hawaiʻi",
    purpose: "Navigation between patch reefs in turbid water; transects across a lagoon.",
    takes: "Coral placed from the Allen Coral Atlas habitat classes over the lidar; no centimetre survey exists here yet.",
    standing: "mixed",
    sources: ["NOAA topobathy lidar", "Allen Coral Atlas"],
    becomes: "kaneohe",
  },
  {
    key: "red-sea-surveyed",
    name: "A surveyed Red Sea fringing reef",
    where: "Saudi Arabian coast",
    purpose: "The reef the platform was named for: steep fore-reef slope, spur and groove, a terrace at twenty-four metres.",
    takes: "A photogrammetry survey of a real kilometre; the constructed one stands in until then.",
    standing: "constructed",
    sources: ["Constructed morphology; awaiting a survey"],
    becomes: "red-sea",
  },
  {
    key: "wreck",
    name: "A wreck",
    where: "Florida Keys or the Red Sea",
    purpose: "Inspection: approach a structure, circle it, keep it in frame from many bearings.",
    takes: "A photogrammetry model of a real wreck with a permissive licence, on surveyed seabed.",
    standing: "surveyed",
    sources: ["Public photogrammetry archives; licences checked per model"],
  },
  {
    key: "offshore-platform",
    name: "An offshore platform",
    where: "Gulf of Mexico",
    purpose: "Jacket-leg inspection, marine growth survey, riser following.",
    takes: "A jacket structure to drawing, mooring lines, and the bathymetry under it.",
    standing: "constructed",
    sources: ["BOEM platform records", "NOAA bathymetry"],
  },
  {
    key: "port",
    name: "A port",
    where: "A harbour with public multibeam",
    purpose: "Quay wall and hull inspection in low visibility; sonar-led navigation.",
    takes: "Multibeam bathymetry of a harbour, quay walls and piles, and turbid water.",
    standing: "surveyed",
    sources: ["Port authority multibeam surveys, where public"],
  },
  {
    key: "wind-farm",
    name: "An offshore wind farm",
    where: "North Sea",
    purpose: "Monopile and scour-protection inspection; cable route following.",
    takes: "Monopiles and scour protection on EMODnet bathymetry.",
    standing: "mixed",
    sources: ["EMODnet bathymetry (CC BY 4.0)"],
  },
  {
    key: "kelp-forest",
    name: "A kelp forest",
    where: "California",
    purpose: "Navigation and survey inside a moving canopy that occludes sonar and camera alike.",
    takes: "Animated kelp, on lidar bathymetry, with the light that filters through it.",
    standing: "mixed",
    sources: ["NOAA topobathy lidar", "Kelp canopy from satellite"],
  },
];
