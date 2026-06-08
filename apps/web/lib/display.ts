export type TableLike = {
  records?: Array<Record<string, unknown>>;
};

export type ChartSpec = {
  chart_type?: string;
  title?: string;
  x?: string;
  y?: string;
  data?: Array<Record<string, unknown>>;
};

const LABELS: Record<string, string> = {
  "Offline summary": "总结",
  "Summary": "总结",
  "Summary and key points": "总结与要点",
  "Answer": "回答",
  "Supporting excerpts": "文件依据",
  "Customer answer": "客服回答",
  "FAQ excerpts": "FAQ 依据",
  "Regional sales ranking": "区域销售排行",
  "Regional sales chart": "区域销售图表",
  "Business insights": "业务洞察",
  "Immediate report": "即时报告"
};

const STATUS_LABELS: Record<string, string> = {
  pending: "等待中",
  validated: "已检查",
  running: "处理中",
  completed: "已完成",
  failed: "失败",
  skipped: "未执行"
};

export function outputLabel(label: string): string {
  return LABELS[label] ?? label;
}

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

export function localizeText(value: string): string {
  return value
    .replaceAll("Summary:\n", "总结：\n")
    .replaceAll("\n\nKey points:\n", "\n\n关键要点：\n")
    .replaceAll("Report:\n", "报告：\n")
    .replaceAll("Business insights:\n", "业务洞察：\n")
    .replaceAll("\n\nRecommendation:\n", "\n\n建议：\n")
    .replaceAll("Answer based on the provided files:\n", "根据所提供文件回答：\n");
}

export function tableRows(value: unknown): Array<Record<string, unknown>> {
  if (isRecord(value) && Array.isArray((value as TableLike).records)) {
    return (value as TableLike).records ?? [];
  }
  if (Array.isArray(value) && value.every(isRecord)) {
    return value as Array<Record<string, unknown>>;
  }
  return [];
}

export function chartRows(value: unknown): Array<Record<string, unknown>> {
  if (!isRecord(value)) {
    return [];
  }
  const data = (value as ChartSpec).data;
  return Array.isArray(data) && data.every(isRecord) ? data : [];
}

export function publicErrorMessage(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error ?? "");
  if (message.includes("Unsupported table format")) {
    return "未找到可分析的表格文件，请上传 CSV 或 XLSX 文件。";
  }
  return message.trim() || "暂时无法完成处理，请检查输入后重试。";
}

export function visibleTextHasInternalTerms(text: string): boolean {
  return /\b(Agent|Tool|Step|Registry|Executor|Workflow JSON)\b/i.test(text);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
