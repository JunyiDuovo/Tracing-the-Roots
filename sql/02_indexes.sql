-- 物理设计：姓名模糊查询、按父节点查子节点
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS ix_member_name_trgm ON member USING gin (name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS ix_member_father_id ON member (father_id) WHERE father_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_member_mother_id ON member (mother_id) WHERE mother_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_member_tree_generation ON member (tree_id, generation_level);
