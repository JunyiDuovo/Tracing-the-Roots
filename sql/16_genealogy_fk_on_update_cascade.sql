-- 允许更新 genealogy.id 时级联更新 member.tree_id 与 genealogy_collaborator.genealogy_id（删除族谱后全表 id 重排为 1..n）
-- 已有库执行本文件一次即可；新建库若已用更新后的 01_schema.sql 则无需执行

ALTER TABLE genealogy_collaborator DROP CONSTRAINT IF EXISTS genealogy_collaborator_genealogy_id_fkey;
ALTER TABLE genealogy_collaborator ADD CONSTRAINT genealogy_collaborator_genealogy_id_fkey
    FOREIGN KEY (genealogy_id) REFERENCES genealogy(id) ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE member DROP CONSTRAINT IF EXISTS member_tree_id_fkey;
ALTER TABLE member ADD CONSTRAINT member_tree_id_fkey
    FOREIGN KEY (tree_id) REFERENCES genealogy(id) ON DELETE CASCADE ON UPDATE CASCADE;