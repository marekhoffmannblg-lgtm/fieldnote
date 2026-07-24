export type UiRunStatus =
  | "queued"
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

export function isRunSuccess(run: RunStatusLike): boolean {
  return run.pipeline_status === "success";
}

export function isRunPartial(run: RunStatusLike): boolean {
  return run.pipeline_status === "partial" || run.status === "partial";
}

export function isRunFailure(run: RunStatusLike): boolean {
  return ["failed", "timed_out", "cancelled", "interrupted"].includes(run.status)
    || run.pipeline_status === "failed";
}

/** Static Vite data may be reloaded only after a terminal result with an exported snapshot. */
export function shouldAutoReloadAfterRun(run: RunStatusLike): boolean {
  return run.snapshot_updated === true
    && ["succeeded", "partial"].includes(run.status)
    && ["success", "partial"].includes(run.pipeline_status || "");
}
