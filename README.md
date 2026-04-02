# 寻根溯源 — 族谱管理系统（课程设计）

## 技术栈

- **应用**：Python 3 + Flask + Flask-Login + SQLAlchemy + PostgreSQL
- **脚本**：`psycopg2` 批量 `COPY` 导入模拟数据

## 环境准备

1. 安装 PostgreSQL，创建数据库：

```sql
CREATE DATABASE genealogy_db;
```

2. 执行 SQL（按顺序）：

- `sql/01_schema.sql`
- `sql/02_indexes.sql`（需 `CREATE EXTENSION pg_trgm;` 权限）

3. Python 依赖：

```bash
cd C:\Users\Admin\genealogy-project
pip install -r requirements.txt
copy .env.example .env
```

编辑 `.env`：推荐按 `.env.example` 使用 **`GENEALOGY_DB_HOST` 等分项**填写密码（支持中文密码）；**勿**在一行 URL 里写中文密码。`.env` 请在 VS Code 右下角选 **UTF-8** 保存。批量脚本仍可用 `GENEALOGY_DSN=postgresql://...`。

4. 启动 Web：

```bash
set FLASK_APP=app.py
flask run
```

浏览器访问 `http://127.0.0.1:5000`。**请先使用「注册」创建账户**（`scripts/generate_bulk_data.py` 中的 `admin` 密码哈希为占位，不能直接登录）。

## 批量模拟数据（作业 3：数据工程）

满足：**≥10 个族谱**、**至少一个族谱 ≥50,000 成员**、**全系统 ≥100,000 成员**、成员在同谱内通过父母或婚配与旁人相连、**每个族谱均 ≥30 代**（大谱 32 代）；使用 **`COPY` 批量导入** CSV。

### 为何网站仪表盘全是 0？

批量脚本会 `TRUNCATE` 清空族谱与成员后重建数据。若未指定所有者，数据挂在占位用户 **`admin`**（密码为占位哈希，**不能用于网站登录**），你用自己的账号登录时看不到任何族谱。

**请先在网站注册一个账号**，生成数据时把用户名交给环境变量 **`GENEALOGY_OWNER_USERNAME`**，则所有族谱的 `created_by` 都是你的用户，登录后即可看到统计与列表。

### 一键生成 CSV 并 COPY 入库（PowerShell 示例）

```powershell
cd C:\Users\Admin\genealogy-project
$env:GENEALOGY_DSN="postgresql://postgres:postgres@127.0.0.1:5432/genealogy_db"
$env:GENEALOGY_OWNER_USERNAME="你的注册用户名"
python scripts\generate_bulk_data.py
```

生成 CSV：`data/member_bulk.csv`、`data/marriage_bulk.csv`；脚本内使用 `psycopg2` 的 `copy_expert` 执行与 **`COPY ... FROM`** 等价的批量导入（导入前临时 `DISABLE TRIGGER USER`，导入后恢复）。

### 导出某分支备份（COPY 演示）

- **SQL 说明**：`sql/06_export_branch.sql`（含服务端 `COPY TO`、客户端 `\copy`、与脚本三种方式说明）。
- **推荐本机落盘**：`python scripts\export_branch_csv.py 1 -o data\branch_export.csv`（将 `1` 换成你要导出的祖先 `member.id`）。

```powershell
$env:GENEALOGY_DSN="postgresql://postgres:postgres@127.0.0.1:5432/genealogy_db"
python scripts\export_branch_csv.py 1 -o data\branch_export.csv
```

## 文档与作业交付物

| 内容 | 路径 |
|------|------|
| ER 与范式说明 | `docs/数据库设计说明.md` |
| 核心 SQL（含递归 CTE） | `sql/03_core_queries.sql` |
| 索引与 EXPLAIN 实验说明 | `docs\physical\index_strategy_and_explain.md` |
| EXPLAIN 对照占位 | `docs\physical\explain_four_gen_before.txt`、`explain_four_gen_after.txt` |
| 分支导出示例 | `sql/06_export_branch.sql` |

在数据库中跑通四代查询后，将两次 `EXPLAIN (ANALYZE, BUFFERS, VERBOSE)` 输出分别粘贴到上述 `explain_*.txt`。
