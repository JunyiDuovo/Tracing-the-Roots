-- 允许父母 member 属其他族谱（异姓通婚）；与更新后的 01_schema.sql 中触发器一致
-- 已有库执行本文件一次即可

CREATE OR REPLACE FUNCTION trg_member_parent_checks()
RETURNS TRIGGER AS $$
DECLARE
    fy INTEGER; my INTEGER; fg VARCHAR(16); mg VARCHAR(16);
BEGIN
    IF NEW.father_id IS NOT NULL THEN
        SELECT birth_year, gender INTO fy, fg FROM member WHERE member_id = NEW.father_id;
        IF NOT FOUND THEN RAISE EXCEPTION 'father row not found'; END IF;
        IF upper(trim(fg)) NOT IN ('M', 'MALE', U&'\7537') THEN
            RAISE EXCEPTION 'father must be male'; END IF;
        IF fy IS NOT NULL AND NEW.birth_year IS NOT NULL AND fy >= NEW.birth_year THEN
            RAISE EXCEPTION 'father birth_year must be before child';
        END IF;
    END IF;
    IF NEW.mother_id IS NOT NULL THEN
        SELECT birth_year, gender INTO my, mg FROM member WHERE member_id = NEW.mother_id;
        IF NOT FOUND THEN RAISE EXCEPTION 'mother row not found'; END IF;
        IF upper(trim(mg)) NOT IN ('F', 'FEMALE', U&'\5973') THEN
            RAISE EXCEPTION 'mother must be female'; END IF;
        IF my IS NOT NULL AND NEW.birth_year IS NOT NULL AND my >= NEW.birth_year THEN
            RAISE EXCEPTION 'mother birth_year must be before child';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
