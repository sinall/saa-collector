SET @queued_at_exists := (
  SELECT COUNT(*)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'collector_collect_plan'
    AND COLUMN_NAME = 'queued_at'
);
SET @queued_at_sql := IF(
  @queued_at_exists = 0,
  'ALTER TABLE collector_collect_plan ADD COLUMN queued_at datetime(6) NULL COMMENT ''入队时间'' AFTER created_at',
  'SELECT 1'
);
PREPARE queued_at_stmt FROM @queued_at_sql;
EXECUTE queued_at_stmt;
DEALLOCATE PREPARE queued_at_stmt;

SET @queue_task_id_exists := (
  SELECT COUNT(*)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'collector_collect_plan'
    AND COLUMN_NAME = 'queue_task_id'
);
SET @queue_task_id_sql := IF(
  @queue_task_id_exists = 0,
  'ALTER TABLE collector_collect_plan ADD COLUMN queue_task_id varchar(100) NULL COMMENT ''队列任务ID'' AFTER queued_at',
  'SELECT 1'
);
PREPARE queue_task_id_stmt FROM @queue_task_id_sql;
EXECUTE queue_task_id_stmt;
DEALLOCATE PREPARE queue_task_id_stmt;
