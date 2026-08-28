import { describe, expect, it } from "vitest";

import { match } from "./router";

describe("reading a screen out of a path", () => {
  it("recognises a screen and reads its parameters", () => {
    expect(match("/cities/:cityId", "/cities/city_01ABC")).toEqual({ cityId: "city_01ABC" });
    expect(
      match("/layers/:layerId/versions/:versionId", "/layers/layer_1/versions/ver_2"),
    ).toEqual({ layerId: "layer_1", versionId: "ver_2" });
  });

  it("does not confuse one screen for another", () => {
    expect(match("/cities/:cityId", "/layers/layer_1")).toBeUndefined();
    expect(match("/cities/:cityId", "/cities")).toBeUndefined();
    expect(match("/cities/:cityId", "/cities/a/b")).toBeUndefined();
  });

  it("reads an identifier that was escaped in the address", () => {
    expect(match("/work/:jobId", "/work/job%2F1")).toEqual({ jobId: "job/1" });
  });
});
