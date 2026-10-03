import { describe, expect, it } from "vitest";
import { DICTIONARIES } from "../i18n/dictionaries";
import { friendlySource } from "./display";

describe("friendlySource", () => {
  it("labels the request-driven Datalastic provider explicitly", () => {
    expect(friendlySource("datalastic", DICTIONARIES.en)).toBe("Datalastic Live AIS");
    expect(friendlySource("datalastic", DICTIONARIES["zh-Hant"])).toBe(
      "Datalastic Live AIS",
    );
  });

  it("preserves the existing localized label for other live providers", () => {
    expect(friendlySource("open_waters", DICTIONARIES.en)).toBe("Live AIS");
  });
});
