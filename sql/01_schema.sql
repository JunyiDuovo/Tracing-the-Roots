-- Genealogy DB schema (UTF-8 server). Source file ASCII-only where possible so Windows psql (GBK) can \i safely.
-- member columns align with members.csv; see repo docs for Chinese notes.
-- Fresh DB: sql/00_reset_before_reimport.sql -> this file -> 02_indexes.sql

CREATE TABLE app_user (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(64) NOT NULL UNIQUE,
    password_hash   VARCHAR(256) NOT NULL,
    email           VARCHAR(128),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE genealogy (
    id              SERIAL PRIMARY KEY,
    title           VARCHAR(200) NOT NULL,
    surname         VARCHAR(64) NOT NULL,
    revision_date   DATE,
    created_by      INTEGER NOT NULL REFERENCES app_user(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE genealogy_collaborator (
    genealogy_id    INTEGER NOT NULL REFERENCES genealogy(id) ON DELETE CASCADE,
    user_id         INTEGER NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    invited_by      INTEGER REFERENCES app_user(id),
    joined_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (genealogy_id, user_id)
);

CREATE TABLE member (
    member_id         BIGSERIAL PRIMARY KEY,
    tree_id           INTEGER NOT NULL REFERENCES genealogy(id) ON DELETE CASCADE,
    name              VARCHAR(100) NOT NULL,
    gender            VARCHAR(16) NOT NULL,
    birth_year        INTEGER CHECK (birth_year IS NULL OR (birth_year >= 800 AND birth_year <= 3000)),
    death_year        INTEGER CHECK (death_year IS NULL OR (death_year >= 800 AND death_year <= 3000)),
    bio               TEXT,
    generation_level  INTEGER CHECK (generation_level IS NULL OR generation_level >= 0),
    father_id         BIGINT REFERENCES member(member_id) ON DELETE SET NULL ON UPDATE CASCADE,
    mother_id         BIGINT REFERENCES member(member_id) ON DELETE SET NULL ON UPDATE CASCADE,
    spouse_id         BIGINT REFERENCES member(member_id) ON DELETE SET NULL ON UPDATE CASCADE,
    created_by        INTEGER REFERENCES app_user(id),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_member_life CHECK (
        death_year IS NULL OR birth_year IS NULL OR death_year >= birth_year
    ),
    CONSTRAINT ck_member_gender_csv CHECK (
        gender IN ('M', 'F', 'Male', 'Female', U&'\7537', U&'\5973')
    )
);

CREATE INDEX ix_member_tree ON member (tree_id);
CREATE INDEX ix_member_father ON member (father_id);
CREATE INDEX ix_member_mother ON member (mother_id);
CREATE INDEX ix_member_spouse ON member (spouse_id) WHERE spouse_id IS NOT NULL;

-- Parent checks: 父母可属任意族谱（异姓通婚）；性别、出生年序仍校验
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

CREATE TRIGGER tg_member_parent_checks
    BEFORE INSERT OR UPDATE ON member
    FOR EACH ROW EXECUTE PROCEDURE trg_member_parent_checks();
