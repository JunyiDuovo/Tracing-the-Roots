-- 删除本项目相关表（婚配信息在 member.spouse_id，无 marriage 表）
DROP TABLE IF EXISTS member CASCADE;
DROP TABLE IF EXISTS genealogy_collaborator CASCADE;
DROP TABLE IF EXISTS genealogy CASCADE;
DROP TABLE IF EXISTS app_user CASCADE;

DROP FUNCTION IF EXISTS trg_member_parent_checks();
