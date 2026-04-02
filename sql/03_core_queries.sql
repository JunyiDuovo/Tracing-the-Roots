-- ============================================================
-- 任务 4：核心 SQL（PostgreSQL）；member 列与 members.csv 对齐
-- ============================================================

-- ---------- 基本查询：给定成员 member_id，其配偶及所有子女 ----------
WITH me AS (SELECT member_id, tree_id, spouse_id FROM member WHERE member_id = :member_id)
SELECT 'spouse' AS rel_type, s.member_id, s.name, s.gender, s.birth_year, s.death_year
FROM me
JOIN member s ON s.member_id = me.spouse_id
WHERE me.spouse_id IS NOT NULL
UNION ALL
SELECT 'child' AS rel_type, c.member_id, c.name, c.gender, c.birth_year, c.death_year
FROM me
JOIN member c ON c.father_id = me.member_id OR c.mother_id = me.member_id;

-- ---------- 递归 CTE：成员 A 向上追溯所有祖先 ----------
WITH RECURSIVE anc AS (
    SELECT member_id, name, gender, birth_year, father_id, mother_id, 0 AS hop,
           ARRAY[member_id::bigint] AS path_ids
    FROM member WHERE member_id = :member_a_id
    UNION ALL
    SELECT p.member_id, p.name, p.gender, p.birth_year, p.father_id, p.mother_id, a.hop + 1,
           a.path_ids || p.member_id
    FROM anc a
    JOIN member p ON p.member_id = a.father_id OR p.member_id = a.mother_id
    WHERE NOT (p.member_id = ANY (a.path_ids))
)
SELECT DISTINCT ON (member_id) member_id, name, gender, birth_year, death_year, hop
FROM anc WHERE hop > 0
ORDER BY member_id, hop;

-- ---------- 某 tree_id 平均寿命最长的一代人（generation_level）----------
WITH life AS (
    SELECT generation_level,
           AVG((death_year - birth_year)::numeric) AS avg_lifespan_years
    FROM member
    WHERE tree_id = :genealogy_id
      AND birth_year IS NOT NULL AND death_year IS NOT NULL
    GROUP BY generation_level
)
SELECT generation_level, avg_lifespan_years
FROM life
ORDER BY avg_lifespan_years DESC NULLS LAST
LIMIT 1;

-- ---------- 年龄超过 50 岁且无配偶的男性 ----------
SELECT m.member_id, m.name, m.birth_year,
       (:current_year - m.birth_year) AS age_approx
FROM member m
WHERE (upper(trim(m.gender)) IN ('M', 'MALE', '男'))
  AND m.birth_year IS NOT NULL
  AND (:current_year - m.birth_year) > 50
  AND m.spouse_id IS NULL;

-- ---------- 出生年早于同 tree 同 generation_level 平均出生年的成员 ----------
WITH gen_avg AS (
    SELECT tree_id, generation_level, AVG(birth_year::numeric) AS avg_birth
    FROM member
    WHERE birth_year IS NOT NULL AND generation_level IS NOT NULL
    GROUP BY tree_id, generation_level
)
SELECT m.member_id, m.tree_id, m.name, m.generation_level, m.birth_year, g.avg_birth
FROM member m
JOIN gen_avg g ON g.tree_id = m.tree_id AND g.generation_level = m.generation_level
WHERE m.birth_year IS NOT NULL
  AND m.birth_year < g.avg_birth;

-- ---------- 辅助：自某祖先向下四代（EXPLAIN 实验）----------
WITH RECURSIVE down AS (
    SELECT member_id, name, father_id, mother_id, 0 AS gen
    FROM member WHERE member_id = :ancestor_id
    UNION ALL
    SELECT c.member_id, c.name, c.father_id, c.mother_id, d.gen + 1
    FROM down d
    JOIN member c ON c.father_id = d.member_id OR c.mother_id = d.member_id
    WHERE d.gen < 4
)
SELECT member_id, name, gen FROM down WHERE gen > 0;
