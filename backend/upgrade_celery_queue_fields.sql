ALTER TABLE collector_collect_plan
  ADD COLUMN queued_at datetime(6) NULL COMMENT '入队时间' AFTER created_at,
  ADD COLUMN queue_task_id varchar(100) NULL COMMENT '队列任务ID' AFTER queued_at;
