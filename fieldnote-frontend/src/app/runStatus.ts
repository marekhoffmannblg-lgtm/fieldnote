export type UiRunStatus =
  | "queued"
  | "leased"
  | "running"
  | "succeeded"
  | "success"
  | "partial"
  | "failed"
  | "timed_out"
  | "cancelled"
  | "interrupted";

export type UiPipelineStatus = "success" | "partial" | "failed" | "preview";

export interface RunStatusLike {
  status: UiRunStatus;
  pipeline_status?: UiPipelineStatus;
  snapshot_updated?: boolean;
}

export interface RunCostLike {
  cost_used?: number | null;
  cost_limit?: number | null;
}

export interface RunCostProgress {
  used: number;
  limit: number;
  percentage: number;
}

export function isRunActive(run: RunStatusLike): boolean {
  return ["queued", "leased", "running"].includes(run.status);
}

export function canCancelRun(run: RunStatusLike): boolean {
  return isRunActive(run);
}

export function isRunSuccess(run: RunStatusLike): boolean {
  return !isRunPartial(run)
    && !isRunFailure(run)
    && (run.pipeline_status === "success" || ["success", "succeeded"].includes(run.status));
}

export function isRunPartial(run: RunStatusLike): boolean {
  return run.pipeline_status === "partial" || run.status === "partial";
}

export function isRunFailure(run: RunStatusLike): boolean {
  return ["failed", "timed_out", "cancelled", "interrupted"].includes(run.status)
    || run.pipeline_status === "failed";
}

/** Returns a display-safe budget progress only when the API supplied a positive limit. */
export function getRunCostProgress(run: RunCostLike): RunCostProgress | null {
  if (typeof run.cost_limit !== "number" || !Number.isFinite(run.cost_limit) || run.cost_limit <= 0) return null;
  const used = typeof run.cost_used === "number" && Number.isFinite(run.cost_used) ? Math.max(0, run.cost_used) : 0;
  return {
    used,
    limit: run.cost_limit,
    percentage: Math.min(100, Math.round((used / run.cost_limit) * 100)),
  };
}

/** Static Vite data may be reloaded only after a terminal result with an exported snapshot. */
export function shouldAutoReloadAfterRun(run: RunStatusLike): boolean {
  return run.snapshot_updated === true
    && ["succeeded", "partial"].includes(run.status)
    && ["success", "partial"].includes(run.pipeline_status || "");
}
