-- =============================================================================
-- 作业用：物理设计实验 — 四代向下查询 + 有无索引对比 + EXPLAIN
-- 在 pgAdmin 或 psql 中分步执行（按 -- == 区块 -- 分隔复制运行）
-- 数据库：与本项目 .env 中 GENEALOGY_DB_* 相同即可。
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 第 0 步：选一个「同族谱里后代够多」的 ancestor_id（记牢用于后面所有查询）
-- -----------------------------------------------------------------------------
-- 下面子查询：找出「子女数最多」的成员之一，作曾祖父/始祖代测四代
SELECT m.member_id, m.tree_id, m.name, m.generation_level,
       (SELECT COUNT(*) FROM member c
        WHERE c.tree_id = m.tree_id
          AND (c.father_id = m.member_id OR c.mother_id = m.member_id)) AS direct_children
FROM member m
ORDER BY direct_children DESC NULLS LAST, m.member_id
LIMIT 5;

-- 把上一行结果里 member_id 换成变量（下面 :ancestor_id 在 pgAdmin「查询工具」里手动替换成具体数字，例如 1）
-- 例如：SET LOCAL 无效时常用做法 —— 全文搜索替换 :ancestor_id

-- -----------------------------------------------------------------------------
-- 第 1 步：确认扩展与现有索引
-- -----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pg_trgm;

SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'member'
ORDER BY indexname;

-- 若缺少姓名 GIN（模糊查询），可建（与 sql/02_indexes.sql 一致）：
-- CREATE INDEX IF NOT EXISTS ix_member_name_trgm ON member USING gin (name gin_trgm_ops);
-- 父/母方向（查子节点）一般已有：
-- CREATE INDEX IF NOT EXISTS ix_member_father ON member (father_id);
-- CREATE INDEX IF NOT EXISTS ix_member_mother ON member (mother_id);


-- -----------------------------------------------------------------------------
-- 第 2 步：四代向下查询
-- 将 xxxx 换成在「第 0 步」选定的 member_id
-- -----------------------------------------------------------------------------
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
WITH RECURSIVE down AS (
    SELECT member_id, name, tree_id, father_id, mother_id, 0 AS gen
    FROM member
    WHERE member_id = xxxx
    UNION ALL
    SELECT c.member_id, c.name, c.tree_id, c.father_id, c.mother_id, d.gen + 1
    FROM down d
    JOIN member c
      ON (c.father_id = d.member_id OR c.mother_id = d.member_id)
     AND c.tree_id = d.tree_id
    WHERE d.gen < 4
)
SELECT member_id, name, gen
FROM down
WHERE gen > 0;


-- -----------------------------------------------------------------------------
-- 第 3 步：姓名模糊查询（测 GIN/trgm），样例：找姓名含「张」
-- -----------------------------------------------------------------------------
EXPLAIN (ANALYZE, BUFFERS)
SELECT member_id, tree_id, name
FROM member
WHERE name ILIKE '%张%'
LIMIT 100;


-- -----------------------------------------------------------------------------
-- 第 4 步：无索引对照组 —— 用事务删除索引 → 再跑同一 EXPLAIN → 回滚恢复
-- 警告：只在个人实验库执行；确认无其他人同时依赖该库。
-- 索引名以你库中 pg_indexes 结果为准。
-- -----------------------------------------------------------------------------
BEGIN;

DROP INDEX IF EXISTS ix_member_name_trgm;
DROP INDEX IF EXISTS ix_member_father;
DROP INDEX IF EXISTS ix_member_mother;
DROP INDEX IF EXISTS ix_member_father_id;
DROP INDEX IF EXISTS ix_member_mother_id;

-- 再执行第 2 步、第 3 步里同内容的 EXPLAIN (ANALYZE, BUFFERS)，把计划与时间记下来

ROLLBACK;
-- ROLLBACK 后索引会全部回来（若 DROP 前有这些索引）。


-- -----------------------------------------------------------------------------
-- 若第 4 步 DROP 的名字不对：先查准确名字再 DROP
-- -----------------------------------------------------------------------------
-- SELECT indexname FROM pg_indexes WHERE tablename = 'member';
