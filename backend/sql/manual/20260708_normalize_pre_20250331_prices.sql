-- Manual-only data repair SQL. Do not place this file under sql/migrations/.
--
-- Normalize historical monthly prices through 2025-03-31 from post-adjusted
-- prices back to unadjusted real prices.
--
-- `saa_prices_ex` is the unadjusted price source. For the pre-2025-04 segment
-- that was loaded as post-adjusted prices, divide OHLC by the Tushare
-- adjustment factor. Keep a row-level backup and only update rows that still
-- match the backed-up values so an interrupted rerun cannot divide twice.

CREATE TABLE IF NOT EXISTS `saa_prices_ex_pre_20250331_hfq_backup` (
    `price_id` bigint NOT NULL,
    `code` varchar(11) NOT NULL,
    `date` date NOT NULL,
    `open` float DEFAULT NULL,
    `close` float DEFAULT NULL,
    `high` float DEFAULT NULL,
    `low` float DEFAULT NULL,
    `adj_factor` double NOT NULL,
    `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`price_id`),
    KEY `idx_prices_ex_hfq_backup_01` (`date`, `code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO `saa_prices_ex_pre_20250331_hfq_backup`
    (`price_id`, `code`, `date`, `open`, `close`, `high`, `low`, `adj_factor`)
SELECT
    `p`.`id`,
    `p`.`code`,
    `p`.`date`,
    `p`.`open`,
    `p`.`close`,
    `p`.`high`,
    `p`.`low`,
    `f`.`adj_factor`
FROM `saa_prices_ex` `p`
JOIN `saa_price_adjust_factors` `f`
  ON `f`.`code` = `p`.`code`
 AND `f`.`date` = `p`.`date`
WHERE `p`.`date` <= DATE('2025-03-31')
  AND `f`.`adj_factor` IS NOT NULL
  AND `f`.`adj_factor` <> 0;

UPDATE `saa_prices_ex` `p`
JOIN `saa_prices_ex_pre_20250331_hfq_backup` `b`
  ON `b`.`price_id` = `p`.`id`
SET
    `p`.`open` = CASE WHEN `b`.`open` IS NULL THEN NULL ELSE `b`.`open` / `b`.`adj_factor` END,
    `p`.`close` = CASE WHEN `b`.`close` IS NULL THEN NULL ELSE `b`.`close` / `b`.`adj_factor` END,
    `p`.`high` = CASE WHEN `b`.`high` IS NULL THEN NULL ELSE `b`.`high` / `b`.`adj_factor` END,
    `p`.`low` = CASE WHEN `b`.`low` IS NULL THEN NULL ELSE `b`.`low` / `b`.`adj_factor` END
WHERE `p`.`date` <= DATE('2025-03-31')
  AND `p`.`open` <=> `b`.`open`
  AND `p`.`close` <=> `b`.`close`
  AND `p`.`high` <=> `b`.`high`
  AND `p`.`low` <=> `b`.`low`;
