#!/usr/bin/env python3
"""
模拟数据生成：>=10 个族谱，>=1 个族谱 >=50000 成员，全系统 >=100000 成员；
成员列与 members.csv 表头一致（另含 created_by）；配偶写入 spouse_id。
使用 PostgreSQL COPY 批量导入。
"""
from __future__ import annotations

import os
import random
import sys

import psycopg2

random.seed(42)

BIG_G_TARGET = 52_000
SMALL_PER_G = 5_500
NUM_GENEALOGIES = 10
BIG_MIN_GENERATIONS = 32
SMALL_MIN_GENERATIONS = 30
ADMIN_USER = "admin"
ADMIN_PASS_HASH = "scrypt:32768:8:1$demo$placeholder"


def resolve_creator_id(cur) -> int:
    owner = os.environ.get("GENEALOGY_OWNER_USERNAME", "").strip()
    if owner:
        cur.execute("SELECT id FROM app_user WHERE username = %s", (owner,))
        row = cur.fetchone()
        if not row:
            print(
                f"错误：未找到用户「{owner}」。请先在网站「注册」，或检查 GENEALOGY_OWNER_USERNAME。",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"数据所有者：{owner} (app_user.id={row[0]})")
        return row[0]
    cur.execute(
        "INSERT INTO app_user (username, password_hash, email) VALUES (%s,%s,%s) "
        "ON CONFLICT (username) DO UPDATE SET email = EXCLUDED.email RETURNING id;",
        (ADMIN_USER, ADMIN_PASS_HASH, "admin@example.com"),
    )
    cid = cur.fetchone()[0]
    print(f"未设置 GENEALOGY_OWNER_USERNAME，使用占位账号 {ADMIN_USER} (id={cid})")
    return cid


def build_tree_fixed_ids(
    tree_id: int,
    start_id: int,
    creator_id: int,
    target: int,
    min_gen: int,
):
    rows: list[dict] = []
    cur_id = start_id
    gen = 0
    root = {
        "member_id": cur_id,
        "tree_id": tree_id,
        "name": f"谱{tree_id}_始祖",
        "gender": "Male",
        "birth_year": 1100,
        "death_year": 1175,
        "bio": "模拟始祖",
        "generation_level": 0,
        "father_id": None,
        "mother_id": None,
        "spouse_id": None,
        "created_by": creator_id,
    }
    rows.append(root)
    cur_id += 1
    frontier = [root["member_id"]]
    by_id = {root["member_id"]: root}

    while len(rows) < target or gen < min_gen:
        gen += 1
        new_frontier: list[int] = []
        if not frontier:
            pool = [r["member_id"] for r in rows if r["generation_level"] >= max(0, gen - 3)]
            if not pool:
                break
            frontier = random.sample(pool, min(100, len(pool)))
            continue
        for pid in frontier:
            parent = by_id[pid]
            need_more = len(rows) < target or gen < min_gen
            n_child = random.randint(1, 3) if need_more else 0
            if need_more and n_child == 0:
                n_child = 1
            base_year = 1050 + gen * 20 + random.randint(-2, 2)
            for _ in range(n_child):
                if len(rows) >= target and gen > min_gen:
                    break
                gstr = "Male" if random.random() < 0.51 else "Female"
                name = f"成员_{tree_id}_{gen}_{cur_id}"
                by = base_year + random.randint(0, 10)
                dy = by + random.randint(48, 90)
                father_id = pid if _is_male(parent["gender"]) else None
                mother_id = pid if _is_female(parent["gender"]) else None
                row = {
                    "member_id": cur_id,
                    "tree_id": tree_id,
                    "name": name,
                    "gender": gstr,
                    "birth_year": by,
                    "death_year": dy,
                    "bio": "",
                    "generation_level": gen,
                    "father_id": father_id,
                    "mother_id": mother_id,
                    "spouse_id": None,
                    "created_by": creator_id,
                }
                rows.append(row)
                by_id[row["member_id"]] = row
                new_frontier.append(cur_id)
                cur_id += 1
        frontier = new_frontier

    return rows, cur_id


def _is_male(g: str) -> bool:
    u = (g or "").strip().upper()
    return u in ("M", "MALE", "男")


def _is_female(g: str) -> bool:
    u = (g or "").strip().upper()
    return u in ("F", "FEMALE", "女")


def add_mothers_and_spouses(rows: list[dict]):
    by_gen: dict[int, list[dict]] = {}
    for r in rows:
        by_gen.setdefault(r["generation_level"], []).append(r)
    for r in rows:
        fid = r["father_id"]
        if not fid or r["mother_id"] is not None:
            continue
        dad = next((x for x in rows if x["member_id"] == fid), None)
        if not dad:
            continue
        females = [
            f
            for f in by_gen.get(dad["generation_level"], [])
            if _is_female(f["gender"]) and f["member_id"] != fid
        ]
        if not females:
            continue
        mom = random.choice(females)
        r["mother_id"] = mom["member_id"]
        if dad.get("spouse_id") is None and mom.get("spouse_id") is None:
            dad["spouse_id"] = mom["member_id"]
            mom["spouse_id"] = dad["member_id"]


def main():
    dsn = os.environ.get(
        "GENEALOGY_DSN",
        "postgresql://postgres:postgres@127.0.0.1:5432/genealogy_db",
    )
    out_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(out_dir, exist_ok=True)

    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute(
        "TRUNCATE member, genealogy_collaborator, genealogy RESTART IDENTITY CASCADE;"
    )
    creator_id = resolve_creator_id(cur)

    gid_list = []
    for i in range(1, NUM_GENEALOGIES + 1):
        cur.execute(
            "INSERT INTO genealogy (title, surname, revision_date, created_by) "
            "VALUES (%s,%s,%s,%s) RETURNING id;",
            (f"模拟族谱{i}", "张" if i % 2 else "李", "2020-01-01", creator_id),
        )
        gid_list.append(cur.fetchone()[0])

    big_tid = gid_list[0]
    all_rows: list[dict] = []
    next_id = 1

    big_rows, next_id = build_tree_fixed_ids(
        big_tid, next_id, creator_id, BIG_G_TARGET, BIG_MIN_GENERATIONS
    )
    all_rows.extend(big_rows)
    add_mothers_and_spouses(big_rows)

    for tid in gid_list[1:]:
        part, next_id = build_tree_fixed_ids(
            tid, next_id, creator_id, SMALL_PER_G, SMALL_MIN_GENERATIONS
        )
        all_rows.extend(part)
        add_mothers_and_spouses(part)

    mpath = os.path.join(out_dir, "member_bulk.tsv")

    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("\t", " ").replace("\n", " ")

    def n(v: int | None) -> str:
        return "\\N" if v is None else str(v)

    all_rows.sort(key=lambda r: (r["generation_level"] or 0, r["member_id"]))
    with open(mpath, "w", encoding="utf-8", newline="") as f:
        for r in all_rows:
            bio_raw = esc(r.get("bio") or "")
            bio_cell = "\\N" if not bio_raw else bio_raw
            parts = [
                str(r["member_id"]),
                str(r["tree_id"]),
                esc(r["name"]),
                r["gender"],
                str(r["birth_year"]) if r["birth_year"] is not None else "\\N",
                str(r["death_year"]) if r["death_year"] is not None else "\\N",
                bio_cell,
                str(r["generation_level"]),
                n(r["father_id"]),
                n(r["mother_id"]),
                n(r["spouse_id"]),
                str(r["created_by"]),
            ]
            f.write("\t".join(parts) + "\n")

    cur.execute("ALTER TABLE member DISABLE TRIGGER USER;")

    copy_sql = (
        "COPY member (member_id, tree_id, name, gender, birth_year, death_year, bio, "
        "generation_level, father_id, mother_id, spouse_id, created_by) FROM STDIN "
        "WITH (FORMAT text, DELIMITER E'\\t', NULL '\\N')"
    )

    with open(mpath, "r", encoding="utf-8") as f:
        cur.copy_expert(copy_sql, f)

    cur.execute("ALTER TABLE member ENABLE TRIGGER USER;")

    cur.execute(
        "SELECT setval(pg_get_serial_sequence('member','member_id'), "
        "(SELECT COALESCE(MAX(member_id),1) FROM member));"
    )

    cur.execute("SELECT COUNT(*) FROM member;")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM member WHERE tree_id=%s;", (big_tid,))
    big_c = cur.fetchone()[0]
    cur.execute("SELECT MAX(generation_level) FROM member WHERE tree_id=%s;", (big_tid,))
    mxg = cur.fetchone()[0]

    print(f"导入完成：总成员 {total}，大族谱 tree_id={big_tid} 成员 {big_c}，最大辈分 {mxg}")
    print(f"TSV：{mpath}")

    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
