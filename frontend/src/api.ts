import type {
  BenchmarkReviewCase,
  BenchmarkReviewDecisionPayload,
  BenchmarkReviewQueue,
  BenchmarkReviewState,
  InsightReport,
} from "./types";

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

export function benchmarkReviewsPath(state?: BenchmarkReviewState): string {
  const path = `${apiBaseUrl}/api/v1/benchmark-reviews/cases`;
  return state ? `${path}?state=${encodeURIComponent(state)}` : path;
}

async function apiError(response: Response, fallback: string): Promise<ApiError> {
  let message = fallback;
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
  return new ApiError(message, response.status, code);
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
    throw await apiError(response, `The report could not be loaded (${response.status}).`);
  }
  return (await response.json()) as InsightReport;
}

export async function fetchBenchmarkReviews(
  state?: BenchmarkReviewState,
  signal?: AbortSignal,
): Promise<BenchmarkReviewQueue> {
  const response = await fetch(benchmarkReviewsPath(state), {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    throw await apiError(
      response,
      `The benchmark review queue could not be loaded (${response.status}).`,
    );
  }
  return (await response.json()) as BenchmarkReviewQueue;
}

export async function submitBenchmarkReviewDecision(
  caseId: string,
  payload: BenchmarkReviewDecisionPayload,
): Promise<BenchmarkReviewCase> {
  const response = await fetch(
    `${apiBaseUrl}/api/v1/benchmark-reviews/cases/${encodeURIComponent(caseId)}/decisions`,
    {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    throw await apiError(
      response,
      `The benchmark review decision could not be saved (${response.status}).`,
    );
  }
  return (await response.json()) as BenchmarkReviewCase;
}
