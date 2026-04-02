# pgAdmin 4 操作说明（连接数据库与查询 `app_user`）

本文说明如何用 **pgAdmin 4** 连接本地 PostgreSQL、打开业务库，并查询用户表（例如确认 `3377673546` 是否存在）。

> **说明**：网站「全库可见账号」由项目根目录 **`.env`** 中的 **`FULL_ACCESS_USERNAMES`** 配置，修改后需**重启 Flask**。该配置**不是**在 pgAdmin 里设置；pgAdmin 仅用于连接数据库、执行 SQL、浏览表数据。

---

## 1. 打开并登录服务器

1. 启动 **pgAdmin 4**（浏览器或桌面版均可）。
2. 左侧 **Browser** 中展开 **Servers**。
3. 若已有本地服务器：单击服务器名，输入 pgAdmin 的**主密码**（安装 pgAdmin 时设置，不是数据库用户密码）。
4. 若尚未添加服务器：右键 **Servers → Register → Server**
   - **General** → **Name**：任意填写，例如 `Local PostgreSQL`。
   - **Connection**
     - **Host**：`127.0.0.1` 或 `localhost`
     - **Port**：`5432`（若安装时改过端口，填实际端口）
     - **Maintenance database**：`postgres`
     - **Username**：`postgres`（或你的超级用户）
     - **Password**：数据库用户密码，可勾选 **Save password**
   - 单击 **Save** 保存。

---

## 2. 打开业务数据库

1. 展开：**Servers → 你的服务器 → Databases**。
2. 单击你的业务库（例如 **`genealogy_db`**；若与 `.env` 中 `GENEALOGY_DB_NAME` 不一致，以实际库名为准）。

---

## 3. 使用 Query Tool 执行 SQL

1. 选中目标数据库（单击使其高亮）。
2. 菜单 **Tools → Query Tool**（或右键该数据库 → **Query Tool**）。
3. 在查询编辑区输入：

```sql
SELECT id, username FROM app_user WHERE username = '3377673546';
```

4. 单击工具栏 **Execute**（或按 **F5**）。
5. 在下方 **Data Output** 面板查看结果：
   - 有行：表示该用户已存在，可用该用户名在网站登录。
   - 无行：表示尚未创建该用户，可在网站**注册**，或按下方「插入用户」自行插入（不推荐优先于网页注册）。

---

## 4. 浏览表（可选）

在左侧树中展开：**genealogy_db → Schemas → public → Tables**。

找到 **`app_user`**，右键 **View/Edit Data → All Rows** 可浏览数据（**请勿随意修改**，避免破坏登录与关联）。

---

## 5. 网站「全库可见」与 `.env`（提醒）

在**项目根目录**的 **`.env`**（可参考 `.env.example`）中配置，例如：

```env
FULL_ACCESS_USERNAMES=3377673546
```

多个用户名用逗号分隔。保存后**重启**运行 `app.py` 的进程，网站权限才会生效。

---

## 6. 在 pgAdmin 中插入用户（可选，不推荐优先于网页注册）

密码需为 **Werkzeug** 生成的哈希，**不要**手写明文密码。

在项目目录下执行（需已安装 Python 与项目依赖）：

```powershell
cd C:\Users\Admin\genealogy-project
python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('你的密码'))"
```

将输出的整串哈希复制到下面 SQL 的引号中，在 **Query Tool** 中执行：

```sql
INSERT INTO app_user (username, password_hash, email)
VALUES ('3377673546', '这里粘贴完整哈希字符串', NULL);
```

---

## 7. 推荐做法小结

| 步骤 | 操作 |
|------|------|
| 查用户 | 使用 **Query Tool** 执行 `SELECT ... FROM app_user WHERE username = '...'` |
| 新建用户 | 优先在网站 **注册** 该用户名，再在 pgAdmin 中 `SELECT` 确认 |
| 全库可见 | 在 **`.env`** 中设置 `FULL_ACCESS_USERNAMES`，并重启网站 |
