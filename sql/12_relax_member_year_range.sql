-- 放宽 member 出生/去世年上限（默认曾限制到 2200，CSV 中可出现 2213 等虚构纪年）
-- 在已有库上执行一次后再 \copy。

ALTER TABLE member DROP CONSTRAINT IF EXISTS member_birth_year_check;
ALTER TABLE member DROP CONSTRAINT IF EXISTS member_death_year_check;

ALTER TABLE member ADD CONSTRAINT member_birth_year_check
    CHECK (birth_year IS NULL OR (birth_year >= 800 AND birth_year <= 3000));
ALTER TABLE member ADD CONSTRAINT member_death_year_check
    CHECK (death_year IS NULL OR (death_year >= 800 AND death_year <= 3000));
