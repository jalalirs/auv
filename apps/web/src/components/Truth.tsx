import type { TruthClass, Uncertainty, Version } from "@coral-city/client";

/**
 * How a value is presented depends on what kind of claim it is.
 *
 * The platform refuses to let a truth class strengthen down lineage; the
 * interface refuses to let one look like another. Photorealism must never imply
 * certainty, and neither must typography.
 */
const truthDescriptions: Record<TruthClass, string> = {
  observation: "measured",
  analysis: "derived from measurements by a documented method",
  forecast: "a statement about a time that has not happened",
  scenario: "a hypothetical chosen by a person",
  simulation: "the output of a model run",
};

export function TruthBadge({ truthClass }: { truthClass: TruthClass }) {
  return (
    <span className={`truth truth-${truthClass}`} title={truthDescriptions[truthClass]}>
      {truthClass.replace("_", " ")}
    </span>
  );
}

export function StateBadge({ version }: { version: Version }) {
  return (
    <span className={`state state-${version.state}`}>
      {version.state.replace("_", " ")}
      {version.visibility === "canonical" ? " · shared record" : " · restricted"}
    </span>
  );
}

/** Uncertainty is always stated. "Unknown" is an answer; absence is not. */
export function describeUncertainty(uncertainty: Uncertainty | undefined): string {
  if (!uncertainty) return "not reported by this deployment";
  switch (uncertainty.kind) {
    case "unknown":
      return "not determined";
    case "absolute_metres":
      return `±${uncertainty.value} m`;
    case "relative_fraction":
      return `±${((uncertainty.value ?? 0) * 100).toFixed(1)}% of value`;
    case "described":
      return uncertainty.note ?? "described, but no description was recorded";
    default:
      return String(uncertainty.kind);
  }
}
