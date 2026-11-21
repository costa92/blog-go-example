(["protocol", "trigger", "mode", "deadline", "steps", "client", "actual"],
 (inputs | select(has("task")) |
  select((.trigger == "deadline" and (.mode == "ignore" or .mode == "cooperate"))
         or (.trigger == "wait-only" and .mode == "cooperate")) |
  [.protocol, .trigger, .mode, .task.has_request_deadline,
   .task.steps_completed, .client_wait_result, .actual_call_result])) | @tsv
