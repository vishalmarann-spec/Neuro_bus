import type { InsightReport } from "./types";

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim() ?? "";
export const apiBaseUrl = configuredBaseUrl.replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
  ) {
    super(message);
  }
}

export function insightReportPath(insightId: string): string {
  return `${apiBaseUrl}/api/v1/insights/${encodeURIComponent(insightId)}/report`;
}

export function insightExportPath(insightId: string): string {
  return `${apiBaseUrl}/api/v1/insights/${encodeURIComponent(insightId)}/report.md`;
}

export async function fetchInsightReport(
  insightId: string,
  signal?: AbortSignal,
): Promise<InsightReport> {
  const response = await fetch(insightReportPath(insightId), {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    let message = `The report could not be loaded (${response.status}).`;
    let code: string | undefined;
    try {
      const body = (await response.json()) as {
        detail?: string | { code?: string; message?: string };
      };
      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (body.detail) {
        message = body.detail.message ?? message;
        code = body.detail.code;
      }
    } catch {
      // Keep the explicit HTTP fallback when the server did not return JSON.
    }
    throw new ApiError(message, response.status, code);
  }
  return (await response.json()) as InsightReport;
}
