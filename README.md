# 寻根溯源 — 项目说明

本文为 **「寻根溯源」族谱 Web 系统** 的主文档，与仓库内全部代码、`sql/` 迁移及 **`docs/`** 下专题文档保持一致。若有冲突，**以数据库实际 `sql/01_schema.sql` 与当前脚本行为为准**。

---

## 1. 项目是什么

**寻根溯源**是一个基于 **Flask + PostgreSQL** 的族谱管理应用：注册登录后，用户可创建多部 **族谱（genealogy）**、维护 **成员（member）** 的姓名与生卒信息、双亲与配偶指针、协作编辑；并提供成员列表（含检索与大批量下的分段加载）、树形预览、祖先递归查询、两地成员间 **无向图最短亲缘通路** 等功能。业务数据全部落在 PostgreSQL；婚配 **不设独立婚姻表**，由 **`member.spouse_id`** 对称引用实现。

---

## 2. 技术栈

| 组件 | 技术 |
|------|------|
| 语言 | Python 3 |
| Web | Flask 3、Flask-Login、Werkzeug（密码哈希） |
| ORM | SQLAlchemy 2.x（`models.py`） |
| 数据库 | PostgreSQL，驱动 **psycopg2**（应用经 SQLAlchemy；批量脚本直接使用 psycopg2） |
| 配置 | `python-dotenv`（`.env`，**UTF-8** 保存） |
| 其他库 | **`regex`**：成员姓名等业务校验 |

依赖列表见 **`requirements.txt`**。

---

## 3. 功能一览（路由级）

均需登录访问（首页落地页 `/` 可公开）。主要端点：

| URL 模式 | 说明 |
|-----------|------|
| `/`、`/register`、`/login`、`/logout` | 落地、注册、登录、退出 |
| `/dashboard` | 总览与入口 |
| `/genealogies`、`/genealogy/new` | 族谱列表、新建 |
| `/genealogy/<gid>/edit` | 编辑谱名、主姓、修订日；列出协作者（**仅创建者**可在此处提交邀请） |
| `/genealogy/<gid>/invite` | **POST**：创建者邀请协作者（表单提交至该 URL） |
| `/genealogy/<gid>/delete` | 删除族谱（POST） |
| `/genealogy/<gid>/members` | **成员列表**：人名模糊查（`?q=`）、`take` 分页、底部「再展开 500 / 全部」；**`partial=1`** 时返回 JSON 供 AJAX |
| `/genealogy/<gid>/member/new`、`.../member/<mid>/edit` | 新增 / 编辑成员；编辑页可 **删除成员**（内部会树内重排 `member_id` 等，见 `app.py`） |
| `/genealogy/<gid>/tree` | 树形文本预览（可选根 `member_id`） |
| `/genealogy/<gid>/ancestors` | 向上递归祖先（内置 `WITH RECURSIVE`） |
| `/genealogy/<gid>/api/member-hint` | JSON：校验本谱 `member_id` 与姓名提示 |
| `/genealogy/<gid>/kinship` | 亲缘通路（图论 BFS 于「父/母/配偶/子女」邻接） |

**权限：** 普通用户仅可操作自己 **创建** 或 **被邀请协作** 的族谱。环境变量 **`FULL_ACCESS_USERNAMES`**（逗号分隔用户名）中的账号对上述校验 **直接放行**（可打开任意族谱，含他人创建者；用于管理或课程演示）。

**「模拟族谱」标题限制：** 标题匹配 **`^模拟族谱\d+$`**（如 `generate_bulk_data.py` 生成）的族谱，对 **非 `FULL_ACCESS_USERNAMES` 列表中的用户** **不可访问**（`user_can_access_genealogy` 恒为假），且在可访问族谱列表中会被过滤；全权限账号不受此限。见 `app.py` 中 **`_BULK_MOCK_TITLE`**。

---

## 4. 仓库目录结构（核心）

```
genealogy-project/
├── README.md              # 本文件（项目主说明）
├── app.py                 # Flask 应用入口（含成员列表分页、partial JSON、祖先 SQL 等）
├── models.py              # SQLAlchemy 模型（与 DDL 对齐）
├── requirements.txt
├── .env.example           # 环境变量模板（勿提交真实密码）
├── members.csv            # 示例/导入用 CSV（可选）
├── import random.py       # 单谱随机树数据生成脚本（文件名含空格；生成与网站列一致的 CSV 逻辑）
├── sql/                   # DDL、索引、示例查询、迁移与基准脚本
├── scripts/               # COPY 导入、造数、分支导出、确保 genealogy 行存在等
├── templates/             # Jinja2（含 members.html、members_table_rows.html、members_expand_bar.html 等）
├── static/
│   ├── css/style.css
│   └── js/
│       ├── back-nav.js
│       └── members-expand.js   # 成员列表「展开更多」无刷新加载
├── docs/                  # 设计、实验与操作等专题文档（见下文 §11）
└── data/                  # 运行 generate_bulk_data 等时生成（如 member_bulk.tsv），可 gitignore
```

**说明：** 若仓库中未提交 `data/`，首次运行造数脚本后会自动创建。

---

## 5. 数据库设计摘要

- **表：** `app_user`、`genealogy`、`genealogy_collaborator`、`member`（**无** `marriage` 表）。
- **成员外键：** `tree_id` → `genealogy`（删谱级联删成员）；`father_id` / `mother_id` / `spouse_id` → `member`（自引用，删除语义以库内 FK 定义及 `sql/14_*.sql` 为准）。
- **完整性：** `CHECK`（性别、生卒先后、年份区间等）+ **`BEFORE` 触发器 `tg_member_before_row`**：同步 `birth_date`→`birth_year`、校验父母性别与父母出生年 **早于** 子女（在均有年份时）；父母 **可跨族谱**（与 `app.py` 中 `_validate_parent_refs` 一致）。
- **索引：** `sql/01_schema.sql` 已含 `ix_member_tree` 与双亲等基础索引；**`sql/02_indexes.sql`** 再建 **`pg_trgm` GIN** 与带 `WHERE IS NOT NULL` 的双亲索引等。若先后都执行，可能 **名称相近的索引并存**；生产环境可用 `\di member*` 审视后合并冗余。

**完整 ER、范式、约束与迁移清单**见 **`docs/数据库设计说明.md`**。

---

## 6. 环境与安装

### 6.1 前置条件

- **PostgreSQL**（建议与本机 `.env` 中库一致；执行 `CREATE DATABASE …`）。
- **Python 3**，`pip`。

### 6.2 克隆与依赖

```bash
cd genealogy-project
pip install -r requirements.txt
copy .env.example .env    # Windows；Linux/macOS: cp .env.example .env
```

用编辑器将 **`.env` 保存为 UTF-8**（Windows 下避免 GBK 损破中文密码）。推荐 **分项变量**：

- `GENEALOGY_DB_HOST`、`GENEALOGY_DB_PORT`、`GENEALOGY_DB_NAME`、`GENEALOGY_DB_USER`、`GENEALOGY_DB_PASSWORD`

若未设置 `GENEALOGY_DB_HOST`，则回退到 **`GENEALOGY_DATABASE_URL`**（`postgresql+psycopg2://…`）；批量脚本还支持 **`GENEALOGY_DSN`**。**中文密码慎用一行 URL**，易编码出错。

其他常用变量：**`SECRET_KEY`**、**`FULL_ACCESS_USERNAMES`**。

### 6.3 初始化数据库（推荐顺序）

1. 建库（若尚无）：`CREATE DATABASE genealogy_db;`
2. 执行（按序）：
   - **`sql/01_schema.sql`** — 表、主外键、CHECK、索引（基础）、触发器  
   - **`sql/02_indexes.sql`** — 需 **`CREATE EXTENSION pg_trgm;`**（需库级权限）

**已有库的增量修复**（按需执行一次，详见各文件头注释）：

| 脚本 | 作用 |
|------|------|
| `sql/12_relax_member_year_range.sql` | 年份上下限放宽 |
| `sql/14_member_fk_on_update_cascade.sql` | 成员自引用 FK 级联更新等 |
| `sql/15_allow_cross_genealogy_parents.sql` | 父母跨谱场景的触发器对齐 |
| `sql/16_genealogy_fk_on_update_cascade.sql` | `genealogy.id` 更新时级联 |
| `sql/17_member_birth_death_date.sql` | `birth_date`/`death_date` 列及触发器收口 |

开发与教学可用 Flask CLI：**`flask init-db`**（`app.py` 中注册），但 **仅根据 ORM 建表且无触发器**；生产或课程完整性演示 **务必执行 `sql/01_schema.sql`**。

---

## 7. 运行 Web

方式一：

```bash
# Windows CMD
set FLASK_APP=app.py
flask run

# Linux / macOS
export FLASK_APP=app.py
flask run
```

方式二：**`python app.py`** —— 等价于 **`debug=True`、`port=5000`**。

亦可用（Flask 2.3+）：**`flask --app app.py run`**，效果与设置 `FLASK_APP` 类似。

浏览器访问 **`http://127.0.0.1:5000`**。**须先注册账号**再创建族谱。若成员页提示缺少 `birth_date` 等列，请在目标库执行 **`sql/17_member_birth_death_date.sql`**（及 `01` 基线）。

---

## 8. 成员列表与性能（大批量）

- 默认仅按谱内排序展示 **前 500 行**（减轻 HTML 与浏览器渲染压力）；查询参数 **`take`** 可增大上界，**`take=all`** 表示不截断。
- 底部 **「再展开 500 / 展开全部」**：通过 **`fetch`** 请求 **`partial=1`**，服务端 **`jsonify`** 返回 **`tbody_html` / `expand_html` / `history_url`**（`templates` 片段渲染），前端 **`members-expand.js`** 替换表格与按钮区并用 **`history.replaceState`** + **保持滚动位置**，避免整页刷新跳顶。
- **注意：** 服务端仍为 **加载本谱（或搜索结果）全体成员并排序**，仅在 **响应/HTML** 层面切片；极限数据量下的下一步优化需在 DB 或服务端排序分页策略上改进。

排序规则见 **`app.py`** 中 **`_members_list_display_order`**（辈分、主线夫妻成组、生日次序等）。

---

## 9. 数据载入与生成工具

### 9.1 网站表单

单条或小批量录入：**新增成员 / 编辑**；服务端校验生辰、生平长度（约 **500 字**，见 **`_BIO_MAX_LEN`**）、父母性别与引用合法性等。

### 9.2 `members.csv` + `import_member_csv.py`

- **先**运行 **`python scripts/ensure_genealogy_for_members_csv.py [csv路径]`**，按 CSV 中 **`tree_id`** 确保 **`genealogy`** 行存在（`id` 与 `tree_id` 对齐），避免违反 **`member_tree_id_fkey`**。
- **再**运行 **`python scripts/import_member_csv.py <path/to/members.csv>`**。  
  支持表头含 **`birth_date` / `death_date`**（与根目录生成脚本一致）或旧版仅年份；导入过程可 **临时关闭触发器** 以加速 **COPY**（详见脚本内说明），导入后应 **`ANALYZE member`**（建议）。

连接配置与 Flask 相同：优先 **分项 `GENEALOGY_DB_*`**，或 **`GENEALOGY_DATABASE_URL` / `GENEALOGY_DSN`**。

### 9.3 `scripts/generate_bulk_data.py`（超大规模演示数据）

- **破坏性：** 脚本内对 **`member`、`genealogy`、`genealogy_collaborator`** 执行 **`TRUNCATE … RESTART IDENTITY CASCADE`**，会 **清空所有族谱与成员行**；**不会** 删除 **`app_user`**，故已注册账号仍保留，但需在跑完后用 **`GENEALOGY_OWNER_USERNAME`** 把新数据挂回你的用户下。
- 目标：多谱、单谱可达数万级成员、深世代等；使用 **`COPY`** 写入 **`member`**。
- 输出：**`data/member_bulk.tsv`**（制表符分隔）；数据库连接 **仅读取环境变量 `GENEALOGY_DSN`**（默认 `postgresql://postgres:postgres@127.0.0.1:5432/genealogy_db`），与 Flask 分项 `GENEALOGY_DB_*` **不自动共用**——若只用 `.env` 里的分项变量，请在 shell 中 **额外设置 `GENEALOGY_DSN`**，或把连接串导出后再运行脚本。
- 写入成员时 **`ALTER TABLE member DISABLE TRIGGER USER`**，结束后 **ENABLE**（与 `import_member_csv.py` 策略类似）。
- **重要：** 若未设置 **`GENEALOGY_OWNER_USERNAME`**，数据可能挂在占位用户 **`admin`**（脚本内密码哈希为占位），**无法用于网站登录**。应先在网站 **注册**，再将你的用户名设入该环境变量后再运行脚本，登录后即可在总览看到自己名下的族谱与统计。

PowerShell 示例：

```powershell
cd C:\path\to\genealogy-project
$env:GENEALOGY_DSN = "postgresql://postgres:postgres@127.0.0.1:5432/genealogy_db"
$env:GENEALOGY_OWNER_USERNAME = "你的注册用户名"
python scripts\generate_bulk_data.py
```

### 9.4 `import random.py`（根目录，文件名含空格）

独立 **Python 数据生成器**（非 Flask 模块）：按统计与谱系规则随机生成 **多部族谱** 的成员行，写出 **`members.csv`**，供 **`scripts/import_member_csv.py`** 与 **`ensure_genealogy_for_members_csv.py`** 入库。文件顶部 **模块 docstring** 概括了设计意图（公历日期、不晚于运行当日、婚龄与夫妻年龄差等与库触发器相容）。

#### 入口与输出

- **`if __name__ == "__main__"`** 调用 **`generate_genealogy_csv(filename="members.csv")`**，在 **当前工作目录** 生成 **`members.csv`**（UTF-8）。
- 表头：  
  `member_id, tree_id, name, gender, birth_date, death_date, bio, generation_level, father_id, mother_id, spouse_id`  
  与 **`import_member_csv.py`** 对齐；**无 `created_by`**（库中该列可空）。

#### 规模与族谱数量（`random_tree_sizes`）

- 以固定 **多组基准人数** 为权重，经抖动与缩放，使 **全体成员总目标** 约为 **27 万～30 万**（每次运行略有不同）；再为每部谱分配 **`tree_id = 1, 2, …`** 与轮转主姓。
- 可通过文件顶部 **`_SEED`**：设为 **整数** 可复现随机序列，**`None`** 则每次不同。

#### 单谱结构（`generate_one_tree`）

- 先建 **30 代** **主线夫妻**（代代一男一女、互指配偶）；再 **扩谱**：从已有夫妇中抽父母生子女，按比例补 **外姓配偶**、配偶行等，直到该 **`tree_id`** 行数达到本谱配额。
- 单谱先用 **局部 `member_id`**；全部谱生成完后由 **`assign_global_ids_by_generation`**：按 **`generation_level` 升序**，再按 **`tree_id` 分组**，组内 **男在前女在后**（同性别再随机打散），赋值 **全局连续 `member_id`**，并重映射 **`father_id` / `mother_id` / `spouse_id`**，避免跨谱 ID 冲突。

#### 日期、婚配与库端约束

- 出生 / 去世为 **`YYYY-MM-DD`**；去世大致在出生后 **45～92 年**，且 **≤ 脚本运行当日**；近代若无法得到满足「早于今天」的去世日则 **去世留空**。
- **子女出生年严格大于双亲出生年**，以适配触发器对父母 / 子女 **`birth_year`** 的比较。
- **中国大陆法定婚龄**（相对运行日）：男 **22** 周岁、女 **20** 周岁；主线夫妻出生年多在 **±5 年** 内可调；不满足时循环重抽样直至合法。

#### 生平 `bio`（`_bio_parent_line`、`_bio_spouse_role_line`、`_join_bio_parts`）

根据 **`id_to_name`** 拼中文句，多句用 **`；`**、末 **`。`**，例如：第几代传人、嫁入某姓、**父母之名 + 之子/女**、**配偶之名 + 之夫/之妻**、「与某某结为伴侣」等；长度通常远低于网站 **`_BIO_MAX_LEN`（500）**。

#### 入库命令（勿与 `generate_bulk_data` 同库混跑，除非接受 TRUNCATE）

```powershell
cd C:\path\to\genealogy-project
python "import random.py"
python scripts\ensure_genealogy_for_members_csv.py members.csv
python scripts\import_member_csv.py members.csv
```

改输出文件名、总人数据或最早出生年等：编辑 **`generate_genealogy_csv`**、**`random_tree_sizes`**、**`generate_one_tree`** 及常量 **`_EARLIEST_BIRTH_YEAR`** 等。

### 9.5 分支导出：`export_branch_csv.py`

按某 **`member_id` 祖先** 导出同 **`tree_id`** 后代子树为 CSV（服务端 **`COPY TO STDOUT`**）。默认依赖环境变量 **`GENEALOGY_DSN`**：

```powershell
$env:GENEALOGY_DSN = "postgresql://postgres:postgres@127.0.0.1:5432/genealogy_db"
python scripts\export_branch_csv.py 1 -o data\branch_export.csv
```

---

## 10. SQL 与实验脚本索引

| 路径 | 说明 |
|------|------|
| `sql/01_schema.sql` | 核心 DDL + 触发器 |
| `sql/02_indexes.sql` | `pg_trgm`、双亲、谱+辈分索引 |
| `sql/03_core_queries.sql` | 配偶子女、递归上下代、统计示例 |
| `sql/04_bulk_disable_triggers.sql` | **`ALTER TABLE member DISABLE TRIGGER USER`**：大批量 COPY 前可执行（须权限） |
| `sql/05_bulk_enable_triggers.sql` | **`ENABLE TRIGGER USER`**：导入结束后务必执行 |
| `sql/21_benchmark_indexes_four_gen.sql` | 四代向下 + `EXPLAIN`、事务内临时 `DROP INDEX` 对照 |
| `sql/00_reset_before_reimport.sql` | 清空表（**高危**） |

---

## 11. `docs/` 下专题文档

| 文件 | 内容 |
|------|------|
| **`docs/数据库设计说明.md`** | ER、关系模式、范式、约束、索引、迁移与载入（与实现一致） |
| **`docs/实验报告_数据库建模与规范化设计.md`** | 课程用长文：概念/逻辑/查询/个人陈述模板等 |
| **`docs/pgadmin-操作说明.md`** | pgAdmin 操作备忘 |
| **`docs/physical/index_strategy_and_explain.md`** | 索引策略与执行计划作业说明 |
| **`docs/physical/explain_four_gen_*.txt`** | EXPLAIN 输出归档占位 |

---

## 12. 常见问题（FAQ）

**Q：`generate_bulk_data.py` 运行后网站里原来的族谱都没了？**  
A：脚本会 **TRUNCATE** `genealogy` / `member` / `genealogy_collaborator`，属预期行为；**用户表保留**。需要先用 **`GENEALOGY_OWNER_USERNAME`** 绑定账号，或改脚本 / 用手工备份。

**Q：明明生成了「模拟族谱1」但登录后看不到？**  
A：标题符合 **`模拟族谱\d+`** 的族谱对 **非全权限用户不可见、不可点**；请将账号加入 **`FULL_ACCESS_USERNAMES`**，或改用网站手工创建的族谱标题。

**Q：网站提示 member 表缺列 / 无法加载成员？**  
A：在连接到的 **同一数据库** 上执行 **`sql/17_member_birth_death_date.sql`**，并确认 **`sql/01_schema.sql`** 已执行；Flask 终端中的 SQLAlchemy 报错可辅助确认缺哪一列。

**Q：批量导入后登录总览全是 0？**  
A：族谱 **`created_by`** 不是你的用户。使用 **`GENEALOGY_OWNER_USERNAME`** 指向你的注册名后重新生成，或用手工 SQL 更新 `genealogy.created_by`（需理解外键与权限）。

**Q：`CREATE EXTENSION pg_trgm` 失败？**  
A：使用超级用户或为数据库授权 **CREATE** 扩展；或请 DBA 预装该扩展。

**Q：成员列表搜索很慢？**  
A：确认 **`sql/02_indexes.sql`** 已执行；超大数据量时考虑统计信息 **`ANALYZE`** 及未来服务端分页/物化排序策略。

**Q：`import random.py` 无法 import？**  
A：文件名含空格，命令行需加引号，或在资源管理器中于该文件所在目录对解释器传参运行。

---

## 13. 安全与生产提示

- **勿**将含真实密码的 **`.env`** 提交到版本库。
- 修改默认 **`SECRET_KEY`**；生产环境关闭 **`debug`**，使用 WSGI 服务器（如 gunicorn）与 HTTPS。
- **`FULL_ACCESS_USERNAMES`** 相当于全局绕过普通「仅自己的谱」限制，仅授予可信账号。

---

## 14. 许可

若仓库根目录后续增加 **`LICENSE`** 文件，以该文件为准；课程或内部项目请遵循所属单位规定。

---

**文档版本说明：** 本 README 已根据当前 **`sql/01_schema.sql`、`app.py`、`models.py`、`scripts/*.py`** 校验；若你拉取到更新代码，请以对应文件为准并适时修订本页。