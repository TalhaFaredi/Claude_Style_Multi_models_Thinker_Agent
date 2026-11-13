import { describe, expect, it } from "vitest";
import { safeNext } from "@/services/api";

describe("safeNext: where to go after signing in", () => {
  it("keeps paths on this site", () => {
    expect(safeNext("/app")).toBe("/app");
    expect(safeNext("/account?tab=password")).toBe("/account?tab=password");
  });
  it("falls back for empty values", () => {
    expect(safeNext(null)).toBe("/app");
    expect(safeNext("")).toBe("/app");
    expect(safeNext(undefined, "/x")).toBe("/x");
  });
  it("refuses other sites, however they are written", () => {
    const backslash = String.fromCharCode(92);
    for (const evil of ["https://evil.example", "//evil.example", `/${backslash}evil.example`, "javascript:alert(1)", "evil.example/app", "http://localhost:3000"]) {
      expect(safeNext(evil)).toBe("/app");
    }
  });
});
