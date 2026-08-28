import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TruthBadge, describeUncertainty } from "./Truth";

describe("presenting what a value is", () => {
  it("says what a truth class means, not only what it is called", () => {
    render(<TruthBadge truthClass="scenario" />);
    const badge = screen.getByText("scenario");
    expect(badge).toHaveAttribute("title", "a hypothetical chosen by a person");
  });

  it("distinguishes a measurement from a hypothesis by class, not only colour", () => {
    const { container: measured } = render(<TruthBadge truthClass="observation" />);
    const { container: supposed } = render(<TruthBadge truthClass="scenario" />);
    expect(measured.firstElementChild?.className).not.toBe(
      supposed.firstElementChild?.className,
    );
  });
});

describe("stating what is not known", () => {
  it("reports an undetermined uncertainty as such rather than as nothing", () => {
    expect(describeUncertainty({ kind: "unknown" })).toBe("not determined");
  });

  it("reports a measured uncertainty with its magnitude", () => {
    expect(describeUncertainty({ kind: "absolute_metres", value: 0.14 })).toBe("±0.14 m");
    expect(describeUncertainty({ kind: "relative_fraction", value: 0.05 })).toBe(
      "±5.0% of value",
    );
  });

  it("reports a described uncertainty in its own words", () => {
    expect(describeUncertainty({ kind: "described", note: "varies with depth" })).toBe(
      "varies with depth",
    );
  });

  it("never renders an absent uncertainty as a confident value", () => {
    expect(describeUncertainty(undefined)).toBe("not reported by this deployment");
  });
});
