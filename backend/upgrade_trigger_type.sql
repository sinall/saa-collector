SET @trigger_type_exists := (
  SELECT COUNT(*)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'collector_collect_plan'
    AND COLUMN_NAME = 'trigger_type'
);
SET @trigger_type_sql := IF(
  @trigger_type_exists = 0,
  'ALTER TABLE collector_collect_plan ADD COLUMN trigger_type VARCHAR(20) NULL COMMENT ''任务触发类型''',
  'SELECT 1'
);
PREPARE trigger_type_stmt FROM @trigger_type_sql;
EXECUTE trigger_type_stmt;
DEALLOCATE PREPARE trigger_type_stmt;

UPDATE collector_collect_plan
SET trigger_type = 'MANUAL'
WHERE source = 'SCHEDULE'
  AND trigger_type IS NULL;
