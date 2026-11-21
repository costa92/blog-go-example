(["run", "mode", "active", "completed", "canceled", "after_cpu_ms"],
 (inputs | select(has("mode")) |
  [.run, .mode, .active_at_return, .full_work_completed,
   .work_canceled, .after_return_cpu_ms])) | @tsv
