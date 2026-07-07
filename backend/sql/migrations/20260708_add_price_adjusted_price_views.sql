-- Add adjustment factors and expose post-adjusted prices for mfactor.

CREATE TABLE IF NOT EXISTS `saa_price_adjust_factors` (
    `id` bigint NOT NULL AUTO_INCREMENT,
    `code` varchar(11) NOT NULL,
    `date` date NOT NULL,
    `adj_factor` double DEFAULT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_price_adjust_factors_01` (`code`, `date`),
    KEY `idx_price_adjust_factors_01` (`date`, `code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

DROP VIEW IF EXISTS `saa_monthly_prices`;
CREATE OR REPLACE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `saa_monthly_prices` AS
select
    `p`.`code` AS `symbol`,
    `p`.`close` AS `price`,
    (`p`.`close` * `f`.`adj_factor`) AS `post_adjusted_price`,
    `f`.`adj_factor` AS `adj_factor`,
    `p`.`date` AS `date`,
    last_day(`p`.`date`) AS `report_date`
from `saa_prices_ex` `p`
left join `saa_price_adjust_factors` `f`
  on `f`.`code` = `p`.`code`
 and `f`.`date` = `p`.`date`
join (
    select
        `code`,
        year(`date`) AS `year_value`,
        month(`date`) AS `month_value`,
        max(`date`) AS `max_date`
    from `saa_prices_ex`
    group by `code`, year(`date`), month(`date`)
) `latest`
  on `latest`.`code` = `p`.`code`
 and `latest`.`max_date` = `p`.`date`
 and `latest`.`year_value` = year(`p`.`date`)
 and `latest`.`month_value` = month(`p`.`date`);

DROP VIEW IF EXISTS `saa_quarterly_prices`;
CREATE OR REPLACE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `saa_quarterly_prices` AS
select
    `p`.`code` AS `symbol`,
    `p`.`close` AS `price`,
    (`p`.`close` * `f`.`adj_factor`) AS `post_adjusted_price`,
    `f`.`adj_factor` AS `adj_factor`,
    `p`.`date` AS `date`,
    ((makedate(year(`p`.`date`), 1) + interval quarter(`p`.`date`) quarter) - interval 1 day) AS `report_date`
from `saa_prices_ex` `p`
left join `saa_price_adjust_factors` `f`
  on `f`.`code` = `p`.`code`
 and `f`.`date` = `p`.`date`
join (
    select
        `code`,
        year(`date`) AS `year_value`,
        quarter(`date`) AS `quarter_value`,
        max(`date`) AS `max_date`
    from `saa_prices_ex`
    group by `code`, year(`date`), quarter(`date`)
) `latest`
  on `latest`.`code` = `p`.`code`
 and `latest`.`max_date` = `p`.`date`
 and `latest`.`year_value` = year(`p`.`date`)
 and `latest`.`quarter_value` = quarter(`p`.`date`);
