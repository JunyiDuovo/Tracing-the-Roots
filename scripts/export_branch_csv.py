#!/usr/bin/env python3
"""
按祖先 member_id 递归导出同 tree_id 内所有后代为 CSV（PostgreSQL COPY TO STDOUT）。

环境变量：GENEALOGY_DSN

示例：
  python scripts/export_branch_csv.py 1 -o data/branch_from_1.csv
"""
from __future__ import annotations

import argparse
import os
import sys

import psycopg2


def main() -> int:
    p = argparse.ArgumentParser(description="导出某成员子树为 CSV（COPY TO STDOUT）")
    p.add_argument("ancestor_id", type=int, help="祖先成员 member_id")
    p.add_argument(
        "-o",
        "--output",
        default="data/branch_export.csv",
        help="输出 CSV 路径",
    )
    args = p.parse_args()

    dsn = os.environ.get(
        "GENEALOGY_DSN",
        "postgresql://postgres:postgres@127.0.0.1:5432/genealogy_db",
    )
    aid = int(args.ancestor_id)
    out_path = args.output
    parent = os.path.dirname(os.path.abspath(out_path))
    if parent:
        os.makedirs(parent, exist_ok=True)

    copy_sql = f"""COPY (
  WITH RECURSIVE sub AS (
    SELECT member_id, tree_id, name, gender, birth_year, death_year, bio,
           generation_level, father_id, mother_id, spouse_id, created_by
    FROM member WHERE member_id = {aid}
    UNION ALL
    SELECT m.member_id, m.tree_id, m.name, m.gender, m.birth_year, m.death_year, m.bio,
           m.generation_level, m.father_id, m.mother_id, m.spouse_id, m.created_by
    FROM sub s
    JOIN member m
      ON (m.father_id = s.member_id OR m.mother_id = s.member_id)
     AND m.tree_id = s.tree_id
  )
  SELECT member_id, tree_id, name, gender, birth_year, death_year, bio,
         generation_level, father_id, mother_id, spouse_id, created_by
  FROM sub
  ORDER BY member_id
) TO STDOUT WITH (FORMAT CSV, HEADER, ENCODING 'UTF8')"""

    conn = psycopg2.connect(dsn)
    try:
        cur = conn.cursor()
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            cur.copy_expert(copy_sql, f)
        cur.close()
    finally:
        conn.close()

    print(f"已导出至：{os.path.abspath(out_path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
