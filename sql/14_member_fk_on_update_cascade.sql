-- 允许更新 member.member_id 时级联更新 father_id / mother_id / spouse_id（树内重排编号用）
-- 已有库执行本文件一次即可；新建库若已用更新后的 01_schema.sql 则无需执行

ALTER TABLE member DROP CONSTRAINT IF EXISTS member_father_id_fkey;
ALTER TABLE member ADD CONSTRAINT member_father_id_fkey
    FOREIGN KEY (father_id) REFERENCES member(member_id) ON DELETE SET NULL ON UPDATE CASCADE;

ALTER TABLE member DROP CONSTRAINT IF EXISTS member_mother_id_fkey;
ALTER TABLE member ADD CONSTRAINT member_mother_id_fkey
    FOREIGN KEY (mother_id) REFERENCES member(member_id) ON DELETE SET NULL ON UPDATE CASCADE;

ALTER TABLE member DROP CONSTRAINT IF EXISTS member_spouse_id_fkey;
ALTER TABLE member ADD CONSTRAINT member_spouse_id_fkey
    FOREIGN KEY (spouse_id) REFERENCES member(member_id) ON DELETE SET NULL ON UPDATE CASCADE;
