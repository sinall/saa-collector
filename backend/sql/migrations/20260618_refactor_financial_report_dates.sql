-- Financial report date semantics:
-- date -> report_date, plus disclosure_date for point-in-time consumers.

SET @table_name := 'saa_raw_balance_sheet';
SET @date_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = @table_name AND COLUMN_NAME = 'date');
SET @report_date_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = @table_name AND COLUMN_NAME = 'report_date');
SET @statement := IF(@date_exists = 1 AND @report_date_exists = 0, 'DELETE FROM saa_raw_balance_sheet WHERE CAST(`date` AS CHAR) = ''0000-00-00''', 'SELECT 1');
PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SET @primary_exists := (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = @table_name AND index_name = 'PRIMARY');
SET @statement := IF(@date_exists = 1 AND @report_date_exists = 0 AND @primary_exists > 0, 'ALTER TABLE saa_raw_balance_sheet DROP PRIMARY KEY', 'SELECT 1');
PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SET @statement := IF(@date_exists = 1 AND @report_date_exists = 0, 'ALTER TABLE saa_raw_balance_sheet CHANGE COLUMN date report_date date NOT NULL', 'SELECT 1');
PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SET @report_date_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = @table_name AND COLUMN_NAME = 'report_date');
SET @primary_exists := (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = @table_name AND index_name = 'PRIMARY');
SET @statement := IF(@report_date_exists = 1 AND @primary_exists = 0, 'ALTER TABLE saa_raw_balance_sheet ADD PRIMARY KEY (symbol, report_date)', 'SELECT 1');
PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SET @disclosure_date_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = @table_name AND COLUMN_NAME = 'disclosure_date');
SET @statement := IF(@disclosure_date_exists = 0, 'ALTER TABLE saa_raw_balance_sheet ADD COLUMN disclosure_date date NULL AFTER report_date', 'SELECT 1');
PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SET @index_exists := (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = @table_name AND index_name = 'ix_balance_sheet_disclosure_date');
SET @statement := IF(@index_exists = 0, 'CREATE INDEX ix_balance_sheet_disclosure_date ON saa_raw_balance_sheet (disclosure_date)', 'SELECT 1');
PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SET @index_exists := (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = @table_name AND index_name = 'ix_balance_sheet_symbol_disclosure_report');
SET @statement := IF(@index_exists = 0, 'CREATE INDEX ix_balance_sheet_symbol_disclosure_report ON saa_raw_balance_sheet (symbol, disclosure_date, report_date)', 'SELECT 1');
PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
UPDATE saa_raw_balance_sheet
SET disclosure_date = CASE
    WHEN MONTH(report_date) = 12 AND DAY(report_date) = 31 THEN DATE_ADD(report_date, INTERVAL 120 DAY)
    WHEN (MONTH(report_date), DAY(report_date)) IN ((3, 31), (6, 30), (9, 30)) THEN DATE_ADD(report_date, INTERVAL 60 DAY)
    ELSE DATE_ADD(report_date, INTERVAL 90 DAY)
END
WHERE disclosure_date IS NULL;

SET @table_name := 'saa_raw_income_statement';
SET @date_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = @table_name AND COLUMN_NAME = 'date');
SET @report_date_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = @table_name AND COLUMN_NAME = 'report_date');
SET @statement := IF(@date_exists = 1 AND @report_date_exists = 0, 'DELETE FROM saa_raw_income_statement WHERE CAST(`date` AS CHAR) = ''0000-00-00''', 'SELECT 1');
PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SET @primary_exists := (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = @table_name AND index_name = 'PRIMARY');
SET @statement := IF(@date_exists = 1 AND @report_date_exists = 0 AND @primary_exists > 0, 'ALTER TABLE saa_raw_income_statement DROP PRIMARY KEY', 'SELECT 1');
PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SET @statement := IF(@date_exists = 1 AND @report_date_exists = 0, 'ALTER TABLE saa_raw_income_statement CHANGE COLUMN date report_date date NOT NULL', 'SELECT 1');
PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SET @report_date_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = @table_name AND COLUMN_NAME = 'report_date');
SET @primary_exists := (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = @table_name AND index_name = 'PRIMARY');
SET @statement := IF(@report_date_exists = 1 AND @primary_exists = 0, 'ALTER TABLE saa_raw_income_statement ADD PRIMARY KEY (symbol, report_date)', 'SELECT 1');
PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SET @disclosure_date_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = @table_name AND COLUMN_NAME = 'disclosure_date');
SET @statement := IF(@disclosure_date_exists = 0, 'ALTER TABLE saa_raw_income_statement ADD COLUMN disclosure_date date NULL AFTER report_date', 'SELECT 1');
PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SET @index_exists := (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = @table_name AND index_name = 'ix_income_statement_disclosure_date');
SET @statement := IF(@index_exists = 0, 'CREATE INDEX ix_income_statement_disclosure_date ON saa_raw_income_statement (disclosure_date)', 'SELECT 1');
PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SET @index_exists := (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = @table_name AND index_name = 'ix_income_statement_symbol_disclosure_report');
SET @statement := IF(@index_exists = 0, 'CREATE INDEX ix_income_statement_symbol_disclosure_report ON saa_raw_income_statement (symbol, disclosure_date, report_date)', 'SELECT 1');
PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
UPDATE saa_raw_income_statement
SET disclosure_date = CASE
    WHEN MONTH(report_date) = 12 AND DAY(report_date) = 31 THEN DATE_ADD(report_date, INTERVAL 120 DAY)
    WHEN (MONTH(report_date), DAY(report_date)) IN ((3, 31), (6, 30), (9, 30)) THEN DATE_ADD(report_date, INTERVAL 60 DAY)
    ELSE DATE_ADD(report_date, INTERVAL 90 DAY)
END
WHERE disclosure_date IS NULL;

SET @table_name := 'saa_raw_cash_flow_statement';
SET @date_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = @table_name AND COLUMN_NAME = 'date');
SET @report_date_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = @table_name AND COLUMN_NAME = 'report_date');
SET @statement := IF(@date_exists = 1 AND @report_date_exists = 0, 'DELETE FROM saa_raw_cash_flow_statement WHERE CAST(`date` AS CHAR) = ''0000-00-00''', 'SELECT 1');
PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SET @primary_exists := (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = @table_name AND index_name = 'PRIMARY');
SET @statement := IF(@date_exists = 1 AND @report_date_exists = 0 AND @primary_exists > 0, 'ALTER TABLE saa_raw_cash_flow_statement DROP PRIMARY KEY', 'SELECT 1');
PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SET @statement := IF(@date_exists = 1 AND @report_date_exists = 0, 'ALTER TABLE saa_raw_cash_flow_statement CHANGE COLUMN date report_date date NOT NULL', 'SELECT 1');
PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SET @report_date_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = @table_name AND COLUMN_NAME = 'report_date');
SET @primary_exists := (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = @table_name AND index_name = 'PRIMARY');
SET @statement := IF(@report_date_exists = 1 AND @primary_exists = 0, 'ALTER TABLE saa_raw_cash_flow_statement ADD PRIMARY KEY (symbol, report_date)', 'SELECT 1');
PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SET @disclosure_date_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = @table_name AND COLUMN_NAME = 'disclosure_date');
SET @statement := IF(@disclosure_date_exists = 0, 'ALTER TABLE saa_raw_cash_flow_statement ADD COLUMN disclosure_date date NULL AFTER report_date', 'SELECT 1');
PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SET @index_exists := (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = @table_name AND index_name = 'ix_cash_flow_statement_disclosure_date');
SET @statement := IF(@index_exists = 0, 'CREATE INDEX ix_cash_flow_statement_disclosure_date ON saa_raw_cash_flow_statement (disclosure_date)', 'SELECT 1');
PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SET @index_exists := (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = @table_name AND index_name = 'ix_cash_flow_statement_symbol_disclosure_report');
SET @statement := IF(@index_exists = 0, 'CREATE INDEX ix_cash_flow_statement_symbol_disclosure_report ON saa_raw_cash_flow_statement (symbol, disclosure_date, report_date)', 'SELECT 1');
PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
UPDATE saa_raw_cash_flow_statement
SET disclosure_date = CASE
    WHEN MONTH(report_date) = 12 AND DAY(report_date) = 31 THEN DATE_ADD(report_date, INTERVAL 120 DAY)
    WHEN (MONTH(report_date), DAY(report_date)) IN ((3, 31), (6, 30), (9, 30)) THEN DATE_ADD(report_date, INTERVAL 60 DAY)
    ELSE DATE_ADD(report_date, INTERVAL 90 DAY)
END
WHERE disclosure_date IS NULL;

SET @table_name := 'saa_raw_main_business';
SET @date_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = @table_name AND COLUMN_NAME = 'date');
SET @report_date_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = @table_name AND COLUMN_NAME = 'report_date');
SET @statement := IF(@date_exists = 1 AND @report_date_exists = 0, 'DELETE FROM saa_raw_main_business WHERE CAST(`date` AS CHAR) = ''0000-00-00''', 'SELECT 1');
PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SET @primary_exists := (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = @table_name AND index_name = 'PRIMARY');
SET @statement := IF(@date_exists = 1 AND @report_date_exists = 0 AND @primary_exists > 0, 'ALTER TABLE saa_raw_main_business DROP PRIMARY KEY', 'SELECT 1');
PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SET @statement := IF(@date_exists = 1 AND @report_date_exists = 0, 'ALTER TABLE saa_raw_main_business CHANGE COLUMN date report_date date NOT NULL', 'SELECT 1');
PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SET @report_date_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = @table_name AND COLUMN_NAME = 'report_date');
SET @primary_exists := (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = @table_name AND index_name = 'PRIMARY');
SET @statement := IF(@report_date_exists = 1 AND @primary_exists = 0, 'ALTER TABLE saa_raw_main_business ADD PRIMARY KEY (symbol, report_date, item_name, category)', 'SELECT 1');
PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SET @disclosure_date_exists := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = @table_name AND COLUMN_NAME = 'disclosure_date');
SET @statement := IF(@disclosure_date_exists = 0, 'ALTER TABLE saa_raw_main_business ADD COLUMN disclosure_date date NULL AFTER report_date', 'SELECT 1');
PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SET @index_exists := (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = @table_name AND index_name = 'ix_main_business_disclosure_date');
SET @statement := IF(@index_exists = 0, 'CREATE INDEX ix_main_business_disclosure_date ON saa_raw_main_business (disclosure_date)', 'SELECT 1');
PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SET @index_exists := (SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = @table_name AND index_name = 'ix_main_business_symbol_disclosure_report');
SET @statement := IF(@index_exists = 0, 'CREATE INDEX ix_main_business_symbol_disclosure_report ON saa_raw_main_business (symbol, disclosure_date, report_date)', 'SELECT 1');
PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
UPDATE saa_raw_main_business
SET disclosure_date = CASE
    WHEN MONTH(report_date) = 12 AND DAY(report_date) = 31 THEN DATE_ADD(report_date, INTERVAL 120 DAY)
    WHEN (MONTH(report_date), DAY(report_date)) IN ((3, 31), (6, 30), (9, 30)) THEN DATE_ADD(report_date, INTERVAL 60 DAY)
    ELSE DATE_ADD(report_date, INTERVAL 90 DAY)
END
WHERE disclosure_date IS NULL;
