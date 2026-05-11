#!/usr/bin/env python3
"""
扫描 members.csv 中出现的所有 tree_id，在库中插入/更新 genealogy，使 id 与 tree_id 一致，
便于随后 \\copy member 不违反 member_tree_id_fkey。

surname / title：对每个 tree_id，取 generation_level=1 的男性成员中 member_id 最小者，
以其姓名首字为 genealogy.surname（单字姓），title 为「{全名}支」。
若无符合条件者则 surname 为「—」，title 为「CSV-树{n}」。

数据库连接（任选其一；会先加载项目根目录 .env UTF-8，与 Flask 一致）：
    GENEALOGY_DB_HOST, GENEALOGY_DB_PORT, GENEALOGY_DB_NAME,
    GENEALOGY_DB_USER, GENEALOGY_DB_PASSWORD
  或一行：GENEALOGY_DATABASE_URL（app 默认）/ GENEALOGY_DSN
若仍 UnicodeDecodeError：检查 Windows「用户/系统环境变量」里是否留有乱码的一行式 DSN，删除或在 CMD 临时清掉：
    set GENEALOGY_DSN=

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
from pathlib import Path

import psycopg2


def _load_project_dotenv() -> None:
    """与 app.py 一致：按 UTF-8 加载根目录 .env，仅补足当前环境中未设的变量。"""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = Path(__file__).resolve().parent.parent
    env_path = root / ".env"
    if env_path.is_file():
        load_dotenv(env_path, encoding="utf-8")


def _strip_sqlalchemy_driver_prefix(dsn: str) -> str:
    """libpq 不接受 postgresql+psycopg2://。"""
    s = dsn.strip()
    for prefix in ("postgresql+psycopg2://", "postgres+psycopg2://"):
        if s.startswith(prefix):
            return "postgresql://" + s[len(prefix) :]
    return s


def connect_genealogy_db():
    """先加载项目 .env；优先分项变量，其次一行式 URL。"""
    _load_project_dotenv()
    if os.environ.get("GENEALOGY_DB_HOST", "").strip():
        return psycopg2.connect(
            host=os.environ["GENEALOGY_DB_HOST"].strip(),
            port=int(os.environ.get("GENEALOGY_DB_PORT", "5432")),
            dbname=os.environ.get("GENEALOGY_DB_NAME", "genealogy_db"),
            user=os.environ.get("GENEALOGY_DB_USER", "postgres"),
            password=os.environ.get("GENEALOGY_DB_PASSWORD", ""),
            client_encoding="UTF8",
        )
    raw = (os.environ.get("GENEALOGY_DSN") or "").strip() or (
        os.environ.get("GENEALOGY_DATABASE_URL") or ""
    ).strip()
    if not raw:
        raw = "postgresql://postgres:postgres@127.0.0.1:5432/genealogy_db"
    dsn = _strip_sqlalchemy_driver_prefix(raw)
    return psycopg2.connect(dsn, client_encoding="UTF8")


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
            title = f"{root_name}支"
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

    try:
        conn = connect_genealogy_db()
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
    except (psycopg2.Error, UnicodeDecodeError) as e:
        print(f"数据库错误：{e}", file=sys.stderr)
        print(
            "若出现 UnicodeDecodeError：1）确认项目根目录 .env 为 UTF-8 且含 GENEALOGY_DB_* "
            "（脚本会自动加载）；2）打开 Windows「环境变量」删除乱码的 GENEALOGY_DSN/"
            "GENEALOGY_DATABASE_URL；或在当前 CMD 执行 set GENEALOGY_DSN= 后再运行。",
            file=sys.stderr,
        )
        return 1

    print(f"已为 tree_id 集合 {sorted(tree_ids)} 写入/更新 genealogy（created_by={uid}）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
