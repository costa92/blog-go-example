select(has("task")) |
{protocol, trigger, mode, client_wait_result,
 task: (.task | {has_work_deadline, steps_completed, completed,
                parent_error_at_task_end, work_error, work_context_error_at_task_end})}
