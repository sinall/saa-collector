SET @index_exists := (
    SELECT COUNT(*)
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'saa_industry_stocks'
      AND index_name = 'ix_industry_stocks_code_date'
);

SET @statement := IF(
    @index_exists = 0,
    'CREATE INDEX ix_industry_stocks_code_date ON saa_industry_stocks (code, date)',
    'SELECT 1'
);

PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
