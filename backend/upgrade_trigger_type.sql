-- 为 CollectPlan 添加 trigger_type 字段
-- 用于区分定时任务的手动触发和自动触发

ALTER TABLE collector_collect_plan 
ADD COLUMN trigger_type VARCHAR(20) NULL;

COMMENT 添加注释说明
COMMENT trigger_type 字段含义：
COMMENT - AUTO: 定时任务自动触发
COMMENT - MANUAL: 定时任务手动触发（用户在定时任务页面点击"执行"按钮）
COMMENT 
COMMENT 注意：
COMMENT 1. trigger_type 只在 source='SCHEDULE' 时有意义
COMMENT 2. 现有的 SCHEDULE 计划， trigger_type 默认为 NULL
COMMENT 3. 新创建的 SCHEDULE 计划，如果是手动点击"执行"，则 trigger_type='MANUAL'

-- 可选：为现有 SCHEDULE 计划设置默认值
UPDATE collector_collect_plan 
SET trigger_type = 'MANUAL' 
WHERE source = 'SCHEDULE' 
  AND trigger_type IS NULL;
