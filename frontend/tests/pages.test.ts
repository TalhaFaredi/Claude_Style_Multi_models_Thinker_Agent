import { describe, expect, it } from "vitest";
import { parsePageSelection } from "@/domain/pages";
describe("page selection before paid reading", () => {
  it("expands, sorts and deduplicates selected page ranges", () => expect(parsePageSelection("7, 1-3, 2", 10)).toEqual({ pages: [1,2,3,7], error: "" }));
  it("rejects invalid, reversed and out-of-range selections", () => { for (const text of ["0", "3-1", "11", "1,", "one"]) expect(parsePageSelection(text, 10).error).not.toBe(""); });
  it("blank selects the full document without constructing an enormous list", () => expect(parsePageSelection(" ", 100000)).toEqual({ error: "" }));
});
