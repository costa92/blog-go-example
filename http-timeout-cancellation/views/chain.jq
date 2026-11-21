(["frontend", "pass_ctx", "B_deadline", "B_budget_ms", "B_steps", "B_result"],
 (inputs | select(has("backend")) |
  [.frontend_protocol, .passed_request_context, .backend.has_request_deadline,
   (.backend.request_budget_ms // "-"), .backend.steps_completed,
   (if .backend.completed then "completed" else .backend.work_error end)])) | @tsv
