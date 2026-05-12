-- 辈分 generation_level：可空；若有值须为 >= 1 的自然数（与网页表单、CSV 导入一致）。
-- 旧库若为 generation_level >= 0，请先备份后执行本脚本。

BEGIN;

UPDATE member SET generation_level = NULL WHERE generation_level IS NOT NULL AND generation_level < 0;
UPDATE member SET generation_level = 1 WHERE generation_level = 0;

ALTER TABLE member DROP CONSTRAINT IF EXISTS member_generation_level_check;

ALTER TABLE member ADD CONSTRAINT ck_member_generation_min_1
    CHECK (generation_level IS NULL OR generation_level >= 1);

COMMIT;
