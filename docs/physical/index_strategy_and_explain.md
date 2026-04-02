# 物理优化：索引策略与四代查询 EXPLAIN 对比

## 1. 需求与索引策略

### 1.1 按姓名模糊查询

- **场景**：`WHERE full_name ILIKE '%关键词%'`（应用层等价于 `LIKE` 模糊匹配）。
- **策略**：启用 `pg_trgm` 扩展，在 `member.full_name` 上建 **GIN + gin_trgm_ops** 索引，使包含类模糊查询可走 Bitmap Index Scan，避免全表顺序扫描。
- **脚本**：项目内 `sql/02_indexes.sql` 中 `ix_member_fullname_trgm`。

### 1.2 按父节点 ID 查询子节点

- **场景**：`WHERE father_id = :pid OR mother_id = :pid`（树展开、后代递归的基础邻居查询）。
- **策略**：在 `member(father_id)`、`member(mother_id)` 上建 **B-Tree**（可选用部分索引 `WHERE father_id IS NOT NULL` 降低体积）。
- **脚本**：`ix_member_father_id`、`ix_member_mother_id`（见 `sql/02_indexes.sql`）。

## 2. 四代后代查询（性能对比实验）

### 2.1 基准 SQL

见 `sql/03_core_queries.sql` 末尾「自某祖先向下四代血亲后代」递归片段；将 `:ancestor_id` 替换为实测祖先成员 ID（建议选择大族谱中层节点，使结果集足够大）。

### 2.2 无合适索引时（对照）

1. 临时删除或不要创建 `father_id`/`mother_id` 上除主键外的索引（**仅测试环境**）。
2. 执行：`EXPLAIN (ANALYZE, BUFFERS, VERBOSE) <递归查询>;`
3. 将完整输出保存为本文同目录下的 `explain_four_gen_before.txt`。

### 2.3 创建索引后（实验组）

1. 执行 `sql/02_indexes.sql`。
2. 再次执行相同 `EXPLAIN (ANALYZE, BUFFERS, VERBOSE)`。
3. 保存为 `explain_four_gen_after.txt`。

### 2.4 对比要点

- **Planning / Execution time**：总耗时是否下降。
- **Scan 类型**：子查询是否由 `Seq Scan` 变为 `Index Scan` / `Bitmap Index Scan`。
- **Buffers**：共享块命中与读盘是否改善。

> 说明：具体数值与机器、缓存、数据分布有关；提交作业时请粘贴**真实**两次 EXPLAIN 输出并简要文字对比。

## 3. 文件清单（本目录 `docs/physical/`）

| 文件 | 说明 |
|------|------|
| `index_strategy_and_explain.md` | 索引策略与实验步骤（本文件） |
| `explain_four_gen_before.txt` | 无索引（或弱索引）下的 EXPLAIN |
| `explain_four_gen_after.txt` | 创建父/母外键索引后的 EXPLAIN |

若尚未在数据库上跑通，可将 `explain_four_gen_*.txt` 留空，在实验完成后用 psql 输出覆盖。
