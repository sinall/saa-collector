SET @stocks_listing_time_exists := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'saa_stocks'
      AND COLUMN_NAME = 'listing_time'
);
SET @stocks_listing_date_exists := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'saa_stocks'
      AND COLUMN_NAME = 'listing_date'
);
SET @stocks_listing_sql := CASE
    WHEN @stocks_listing_date_exists = 1 THEN 'SELECT 1'
    WHEN @stocks_listing_time_exists = 1 THEN 'ALTER TABLE saa_stocks CHANGE COLUMN listing_time listing_date date DEFAULT NULL'
    ELSE 'ALTER TABLE saa_stocks ADD COLUMN listing_date date DEFAULT NULL'
END;
PREPARE stocks_listing_stmt FROM @stocks_listing_sql;
EXECUTE stocks_listing_stmt;
DEALLOCATE PREPARE stocks_listing_stmt;

SET @stocks_delisting_date_exists := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'saa_stocks'
      AND COLUMN_NAME = 'delisting_date'
);
SET @stocks_delisting_sql := IF(
    @stocks_delisting_date_exists = 0,
    'ALTER TABLE saa_stocks ADD COLUMN delisting_date date NOT NULL DEFAULT ''2200-01-01'' AFTER listing_date',
    'SELECT 1'
);
PREPARE stocks_delisting_stmt FROM @stocks_delisting_sql;
EXECUTE stocks_delisting_stmt;
DEALLOCATE PREPARE stocks_delisting_stmt;

UPDATE saa_stocks stocks
JOIN saa_securities securities
  ON securities.code = stocks.symbol
SET stocks.listing_date = COALESCE(securities.start_date, stocks.listing_date),
    stocks.delisting_date = COALESCE(securities.end_date, stocks.delisting_date)
WHERE securities.type = 'stock';

SET @cache_listing_time_exists := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'saa_stock_descriptions_cache'
      AND COLUMN_NAME = 'listing_time'
);
SET @cache_listing_date_exists := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'saa_stock_descriptions_cache'
      AND COLUMN_NAME = 'listing_date'
);
SET @cache_listing_sql := CASE
    WHEN @cache_listing_date_exists = 1 THEN 'SELECT 1'
    WHEN @cache_listing_time_exists = 1 THEN 'ALTER TABLE saa_stock_descriptions_cache CHANGE COLUMN listing_time listing_date date DEFAULT NULL'
    ELSE 'ALTER TABLE saa_stock_descriptions_cache ADD COLUMN listing_date date DEFAULT NULL'
END;
PREPARE cache_listing_stmt FROM @cache_listing_sql;
EXECUTE cache_listing_stmt;
DEALLOCATE PREPARE cache_listing_stmt;

SET @cache_delisting_date_exists := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'saa_stock_descriptions_cache'
      AND COLUMN_NAME = 'delisting_date'
);
SET @cache_delisting_sql := IF(
    @cache_delisting_date_exists = 0,
    'ALTER TABLE saa_stock_descriptions_cache ADD COLUMN delisting_date date NOT NULL DEFAULT ''2200-01-01'' AFTER listing_date',
    'SELECT 1'
);
PREPARE cache_delisting_stmt FROM @cache_delisting_sql;
EXECUTE cache_delisting_stmt;
DEALLOCATE PREPARE cache_delisting_stmt;

UPDATE saa_stock_descriptions_cache cache
JOIN saa_stocks stocks
  ON stocks.symbol = cache.symbol
SET cache.listing_date = stocks.listing_date,
    cache.delisting_date = stocks.delisting_date;

CREATE OR REPLACE VIEW saa_stock_descriptions_impl AS
SELECT
    ss.symbol AS symbol,
    ss.name AS name,
    ss.type AS type,
    ss.market AS market,
    ss.exchange AS exchange,
    ss.board AS board,
    ss.industry_classification_id AS industry_classification_id,
    ss.company_name AS company_name,
    ss.english_name AS english_name,
    ss.registered_address AS registered_address,
    ss.company_referred AS company_referred,
    ss.legal_representative AS legal_representative,
    ss.secretary AS secretary,
    ss.registered_capital AS registered_capital,
    ss.zip_code AS zip_code,
    ss.tel AS tel,
    ss.fax AS fax,
    ss.website AS website,
    ss.listing_date AS listing_date,
    ss.delisting_date AS delisting_date,
    ss.prospectus_time AS prospectus_time,
    ss.issue_quantity AS issue_quantity,
    ss.issue_price AS issue_price,
    ss.issue_pe AS issue_pe,
    ss.issue_method AS issue_method,
    ss.lead_underwriter AS lead_underwriter,
    ss.listing_recommender AS listing_recommender,
    ss.sponsor AS sponsor,
    CONCAT(saa_str2py(ss.name), ' | ', ss.symbol, ' | ', ss.name) AS `desc`,
    ic.name AS industry_classification_name
FROM saa_stocks ss
LEFT JOIN saa_industry_classifications ic
  ON ss.industry_classification_id = ic.id;

CREATE OR REPLACE VIEW saa_stock_descriptions_interface AS
SELECT
    sd.symbol AS symbol,
    sd.name AS name,
    sd.type AS type,
    sd.market AS market,
    sd.exchange AS exchange,
    sd.board AS board,
    sd.industry_classification_id AS industry_classification_id,
    sd.company_name AS company_name,
    sd.english_name AS english_name,
    sd.registered_address AS registered_address,
    sd.company_referred AS company_referred,
    sd.legal_representative AS legal_representative,
    sd.secretary AS secretary,
    sd.registered_capital AS registered_capital,
    sd.zip_code AS zip_code,
    sd.tel AS tel,
    sd.fax AS fax,
    sd.website AS website,
    sd.listing_date AS listing_date,
    sd.delisting_date AS delisting_date,
    sd.prospectus_time AS prospectus_time,
    sd.issue_quantity AS issue_quantity,
    sd.issue_price AS issue_price,
    sd.issue_pe AS issue_pe,
    sd.issue_method AS issue_method,
    sd.lead_underwriter AS lead_underwriter,
    sd.listing_recommender AS listing_recommender,
    sd.sponsor AS sponsor,
    sd.`desc` AS `desc`,
    sd.industry_classification_name AS industry_classification_name
FROM saa_stock_descriptions_cache sd;
