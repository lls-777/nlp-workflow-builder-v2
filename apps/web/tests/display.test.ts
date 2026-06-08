import { describe, expect, it } from "vitest";
import {
  chartRows,
  localizeText,
  outputLabel,
  publicErrorMessage,
  statusLabel,
  tableRows,
  visibleTextHasInternalTerms
} from "../lib/display";

describe("display helpers", () => {
  it("localizes mock text labels", () => {
    expect(localizeText(`Summary:
Short.

Key points:
- One`)).toContain("总结");
    expect(localizeText(`Summary:
Short.

Key points:
- One`)).toContain("关键要点");
  });

  it("maps output and status labels for user-facing UI", () => {
    expect(outputLabel("Summary and key points")).toBe("总结与要点");
    expect(statusLabel("completed")).toBe("已完成");
  });

  it("extracts table and chart rows from serializable API values", () => {
    const rows = [{ region: "North", total_sales: 2000 }];
    expect(tableRows({ records: rows })).toEqual(rows);
    expect(chartRows({ data: rows })).toEqual(rows);
  });

  it("renders public table errors in plain Chinese", () => {
    expect(publicErrorMessage(new Error("Unsupported table format: .md"))).toContain("CSV 或 XLSX");
  });

  it("detects internal engineering terms in visible copy", () => {
    expect(visibleTextHasInternalTerms("执行详情")).toBe(false);
    expect(visibleTextHasInternalTerms("Workflow JSON")).toBe(true);
  });
});
