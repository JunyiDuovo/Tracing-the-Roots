-- Add member.birth_date / member.death_date (与网页、CSV 一致)；从 birth_year/death_year 回填；
-- 统一 BEFORE 触发器：写入日期则同步年份，并保留父母出生年校验。

ALTER TABLE member ADD COLUMN IF NOT EXISTS birth_date DATE;
ALTER TABLE member ADD COLUMN IF NOT EXISTS death_date DATE;

UPDATE member
SET birth_date = make_date(birth_year, 1, 1)
WHERE birth_year IS NOT NULL AND birth_date IS NULL;

UPDATE member
SET death_date = make_date(death_year, 1, 1)
WHERE death_year IS NOT NULL AND death_date IS NULL;

ALTER TABLE member DROP CONSTRAINT IF EXISTS ck_member_life_dates;
ALTER TABLE member ADD CONSTRAINT ck_member_life_dates CHECK (
    death_date IS NULL OR birth_date IS NULL OR death_date >= birth_date
);

DROP TRIGGER IF EXISTS tg_member_parent_checks ON member;
DROP TRIGGER IF EXISTS tg_member_before_row ON member;
DROP FUNCTION IF EXISTS trg_member_parent_checks();

CREATE OR REPLACE FUNCTION trg_member_before_row()
RETURNS TRIGGER AS $$
DECLARE
    fy INTEGER;
    my INTEGER;
    fg VARCHAR(16);
    mg VARCHAR(16);
BEGIN
    IF NEW.birth_date IS NOT NULL THEN
        NEW.birth_year := EXTRACT(YEAR FROM NEW.birth_date)::INTEGER;
    END IF;
    IF NEW.death_date IS NOT NULL THEN
        NEW.death_year := EXTRACT(YEAR FROM NEW.death_date)::INTEGER;
    END IF;

    IF NEW.father_id IS NOT NULL THEN
        SELECT birth_year, gender INTO fy, fg FROM member WHERE member_id = NEW.father_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'father row not found';
        END IF;
        IF upper(trim(fg)) NOT IN ('M', 'MALE', U&'\7537') THEN
            RAISE EXCEPTION 'father must be male';
        END IF;
        IF fy IS NOT NULL AND NEW.birth_year IS NOT NULL AND fy >= NEW.birth_year THEN
            RAISE EXCEPTION 'father birth_year must be before child';
        END IF;
    END IF;
    IF NEW.mother_id IS NOT NULL THEN
        SELECT birth_year, gender INTO my, mg FROM member WHERE member_id = NEW.mother_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'mother row not found';
        END IF;
        IF upper(trim(mg)) NOT IN ('F', 'FEMALE', U&'\5973') THEN
            RAISE EXCEPTION 'mother must be female';
        END IF;
        IF my IS NOT NULL AND NEW.birth_year IS NOT NULL AND my >= NEW.birth_year THEN
            RAISE EXCEPTION 'mother birth_year must be before child';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tg_member_before_row
    BEFORE INSERT OR UPDATE ON member
    FOR EACH ROW EXECUTE PROCEDURE trg_member_before_row();
