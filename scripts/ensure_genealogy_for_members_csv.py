#!/usr/bin/env python3
"""
扫描 members.csv 中出现的所有 tree_id，在库中插入/更新 genealogy，使 id 与 tree_id 一致，
便于随后 \\copy member 不违反 member_tree_id_fkey。

surname / title：对每个 tree_id，取 generation_level=1 的男性成员中 member_id 最小者，
以其姓名首字为 genealogy.surname（单字姓），title 为「{全名}支（树{n}）」。
若无符合条件者则 surname 为「—」，title 为「CSV-树{n}」。

环境变量：GENEALOGY_DSN

示例：
  python scripts/ensure_genealogy_for_members_csv.py
  python scripts/ensure_genealogy_for_members_csv.py C:\\path\\other.csv
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict

import psycopg2


def _is_male(gender: str) -> bool:
    g = gender.strip()
    return g.upper() in ("M", "MALE") or g == "男"


def scan_tree_ids_and_genealogy_meta(
    path: str,
) -> tuple[set[int], dict[int, tuple[str, str]]]:
    """返回 (所有 tree_id 集合, tree_id -> (surname, title))。"""
    tree_ids: set[int] = set()
    gen1_males: dict[int, list[tuple[int, str]]] = defaultdict(list)

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "tree_id" not in {
            h.strip().lower() for h in reader.fieldnames
        }:
            raise ValueError("CSV 缺少 tree_id 列")

        for row in reader:
            km = {k.strip().lower(): (v or "").strip() for k, v in row.items()}
            raw_tid = km.get("tree_id")
            if not raw_tid:
                continue
            try:
                tid = int(raw_tid)
            except ValueError as e:
                raise ValueError(f"非法 tree_id：{raw_tid!r}") from e
            tree_ids.add(tid)

            gen = km.get("generation_level")
            name = km.get("name")
            mid_s = km.get("member_id")
            if gen != "1" or not name or not mid_s or not _is_male(km.get("gender", "")):
                continue
            try:
                mid = int(mid_s)
            except ValueError:
                continue
            gen1_males[tid].append((mid, name))

    meta: dict[int, tuple[str, str]] = {}
    for tid in tree_ids:
        cands = gen1_males.get(tid, [])
        if cands:
            cands.sort(key=lambda x: x[0])
            _, root_name = cands[0]
            surname = root_name[0]
            title = f"{root_name}支（树{tid}）"
        else:
            surname = "—"
            title = f"CSV-树{tid}"
        meta[tid] = (surname, title)

    return tree_ids, meta


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "csv_path",
        nargs="?",
        default=os.path.join(os.path.dirname(__file__), "..", "members.csv"),
        help="members.csv 路径",
    )
    args = p.parse_args()
    path = os.path.abspath(args.csv_path)

    if not os.path.isfile(path):
        print(f"找不到文件：{path}", file=sys.stderr)
        return 1

    try:
        tree_ids, meta = scan_tree_ids_and_genealogy_meta(path)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    if not tree_ids:
        print("未发现任何 tree_id", file=sys.stderr)
        return 1

    dsn = os.environ.get(
        "GENEALOGY_DSN",
        "postgresql://postgres:postgres@127.0.0.1:5432/genealogy_db",
    )

    try:
        conn = psycopg2.connect(dsn)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT id FROM app_user ORDER BY id LIMIT 1")
        row = cur.fetchone()
        if not row:
            print("app_user 为空：请先注册或插入用户", file=sys.stderr)
            return 1
        uid = row[0]

        for tid in sorted(tree_ids):
            surname, title = meta[tid]
            cur.execute(
                """
                INSERT INTO genealogy (id, title, surname, revision_date, created_by)
                VALUES (%s, %s, %s, CURRENT_DATE, %s)
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    surname = EXCLUDED.surname,
                    revision_date = EXCLUDED.revision_date,
                    created_by = EXCLUDED.created_by
                """,
                (tid, title, surname, uid),
            )

        cur.execute(
            "SELECT setval(pg_get_serial_sequence('genealogy','id'), "
            "(SELECT COALESCE(MAX(id),1) FROM genealogy))"
        )
        cur.close()
        conn.close()
    except psycopg2.Error as e:
        print(f"数据库错误：{e}", file=sys.stderr)
        return 1

    print(f"已为 tree_id 集合 {sorted(tree_ids)} 写入/更新 genealogy（created_by={uid}）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
