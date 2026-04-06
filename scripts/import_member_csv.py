#!/usr/bin/env python3
"""
将 members.csv（表头与库表 member 一致）经 PostgreSQL COPY 批量导入。
CSV 列：member_id, tree_id, name, gender, birth_year, death_year, bio,
       generation_level, father_id, mother_id, spouse_id
（created_by / created_at 走库默认值：NULL 与 NOW()）

导入前须保证每个 tree_id 在 genealogy 中存在且 id 一致，否则违反外键。
请先运行（会按 CSV 生成 genealogy 的姓氏与「姓名支（树id）」标题）：
    python scripts/ensure_genealogy_for_members_csv.py [members.csv]

环境变量：GENEALOGY_DSN

示例：
  python scripts/import_member_csv.py C:/path/members.csv
"""
from __future__ import annotations

import argparse
import io
import os
import sys

import psycopg2


def main() -> int:
    p = argparse.ArgumentParser(description="members.csv → COPY 导入 member")
    p.add_argument("csv_path", help="CSV 路径（首行为表头）")
    args = p.parse_args()

    dsn = os.environ.get(
        "GENEALOGY_DSN",
        "postgresql://postgres:postgres@127.0.0.1:5432/genealogy_db",
    )

    with open(args.csv_path, "r", encoding="utf-8-sig") as f:
        data = f.read()

    if not data.strip():
        print("文件为空", file=sys.stderr)
        return 1

    buf = io.StringIO(data)
    copy_sql = (
        "COPY member (member_id, tree_id, name, gender, birth_year, death_year, bio, "
        "generation_level, father_id, mother_id, spouse_id) FROM STDIN "
        "WITH (FORMAT csv, HEADER true, ENCODING 'UTF8', NULL '')"
    )

    conn = None
    cur = None
    try:
        conn = psycopg2.connect(dsn)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("ALTER TABLE member DISABLE TRIGGER USER;")
        buf.seek(0)
        cur.copy_expert(copy_sql, buf)
        cur.execute("ALTER TABLE member ENABLE TRIGGER USER;")
        cur.execute(
            "SELECT setval(pg_get_serial_sequence('member','member_id'), "
            "(SELECT COALESCE(MAX(member_id),1) FROM member));"
        )
        cur.close()
    except psycopg2.Error as e:
        print(f"导入失败：{e}", file=sys.stderr)
        if cur is not None:
            try:
                cur.execute("ALTER TABLE member ENABLE TRIGGER USER;")
            except Exception:
                pass
        return 1
    finally:
        if conn is not None:
            conn.close()

    print("COPY 导入完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
