#!/usr/bin/env python3
"""
将 members.csv 经 PostgreSQL COPY 批量导入。
支持表头：birth_date / death_date（YYYY-MM-DD，与根目录 import random.py 一致），
或旧版 birth_year / death_year（整数，仅年份时 birth_date/death_date 列为空）。

导入时写入 birth_date、death_date、birth_year、death_year（年与完整日期一致；COPY 期间触发器关闭）。

CSV 列（除出生/去世外）：member_id, tree_id, name, gender, bio,
generation_level, father_id, mother_id, spouse_id

导入前请先运行（确保 genealogy 存在）：
    python scripts/ensure_genealogy_for_members_csv.py [members.csv]

数据库连接（任选其一；会先加载项目根目录 .env UTF-8，与 Flask 一致）：
    GENEALOGY_DB_HOST, GENEALOGY_DB_PORT, GENEALOGY_DB_NAME,
    GENEALOGY_DB_USER, GENEALOGY_DB_PASSWORD
  或一行：GENEALOGY_DATABASE_URL / GENEALOGY_DSN

示例：
    python scripts/import_member_csv.py C:/path/members.csv
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import sys
from datetime import date
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
    for prefix in ("postgresql+psycopg2://", "postgres+psycopg2://"):
        if dsn.strip().startswith(prefix):
            return "postgresql://" + dsn.strip()[len(prefix) :]
    return dsn.strip()


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


def _norm_keys(row: dict) -> dict[str, str]:
    return {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}


def _cell_to_year(cell: str, *, allow_empty: bool) -> str:
    """返回四位年份字符串；去世可空 → ''。"""
    s = (cell or "").strip()
    if not s:
        if allow_empty:
            return ""
        raise ValueError("出生年份/日期不能为空")
    if len(s) >= 4 and s[:4].isdigit():
        y = int(s[:4])
        if 800 <= y <= 3000:
            return str(y)
    raise ValueError(f"无法解析年份：{cell!r}")


def _cell_to_iso_date(cell: str) -> str | None:
    """若 cell 以合法 YYYY-MM-DD 开头则返回 10 字符 ISO，否则 None。"""
    s = (cell or "").strip()
    if len(s) < 10 or s[4] != "-" or s[7] != "-":
        return None
    try:
        d = date(int(s[0:4]), int(s[5:7]), int(s[8:10]))
        if d.year < 800 or d.year > 3000:
            return None
        return f"{d.year:04d}-{d.month:02d}-{d.day:02d}"
    except ValueError:
        return None


def _validate_life_order(
    *,
    birth_iso: str | None,
    death_iso: str | None,
    birth_y: str,
    death_y: str,
) -> None:
    bd: date | None = None
    if birth_iso:
        bd = date.fromisoformat(birth_iso)
    elif birth_y.isdigit():
        bd = date(int(birth_y), 1, 1)
    dd: date | None = None
    if death_iso:
        dd = date.fromisoformat(death_iso)
    elif death_y.isdigit():
        dd = date(int(death_y), 1, 1)
    if bd is not None and dd is not None and dd < bd:
        raise ValueError("存在去世早于出生的行（请检查 birth/death 日期或年份）")


def _birth_death_copy_fields(lo: dict[str, str]) -> tuple[str, str, str, str]:
    """返回 CSV 四列字符串：birth_date, death_date, birth_year, death_year（空表示 NULL COPY）。"""
    bir_raw = (lo.get("birth_date") or lo.get("birth_year") or "").strip()
    dth_raw = (lo.get("death_date") or lo.get("death_year") or "").strip()
    bir_iso = _cell_to_iso_date(bir_raw)
    if bir_iso:
        bir_y = bir_iso[:4]
        bir_d_cell = bir_iso
    else:
        bir_d_cell = ""
        bir_y = _cell_to_year(bir_raw, allow_empty=False)

    death_iso = _cell_to_iso_date(dth_raw) if dth_raw else None
    if not dth_raw:
        dth_y_cell = ""
        death_d_cell = ""
    elif death_iso:
        death_d_cell = death_iso
        dth_y_cell = death_iso[:4]
    else:
        death_d_cell = ""
        dth_y_cell = _cell_to_year(dth_raw, allow_empty=True)

    _validate_life_order(
        birth_iso=bir_iso,
        death_iso=death_iso,
        birth_y=bir_y,
        death_y=dth_y_cell or "",
    )
    return bir_d_cell, death_d_cell, bir_y, dth_y_cell


def _build_copy_stream(raw_text: str) -> io.StringIO:
    reader = csv.DictReader(io.StringIO(raw_text))
    if not reader.fieldnames:
        raise ValueError("CSV 无表头")
    keys = {h.strip().lower() for h in reader.fieldnames}
    if not {"member_id", "tree_id", "name", "gender"} <= keys:
        raise ValueError("CSV 缺少必需列（member_id, tree_id, name, gender）")
    # 至少需提供一种出生/去世列名（可混用新旧）
    birth_ok = ("birth_date" in keys) or ("birth_year" in keys)
    if not birth_ok:
        raise ValueError("CSV 须含 birth_date 或 birth_year")

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            "member_id",
            "tree_id",
            "name",
            "gender",
            "birth_date",
            "death_date",
            "birth_year",
            "death_year",
            "bio",
            "generation_level",
            "father_id",
            "mother_id",
            "spouse_id",
        ]
    )
    for row in reader:
        lo = _norm_keys(row)
        bir_d, death_d, bir_y, dth_y = _birth_death_copy_fields(lo)
        writer.writerow(
            [
                lo["member_id"],
                lo["tree_id"],
                lo["name"],
                lo["gender"],
                bir_d,
                death_d,
                bir_y,
                dth_y,
                lo.get("bio", ""),
                lo.get("generation_level", ""),
                lo.get("father_id", ""),
                lo.get("mother_id", ""),
                lo.get("spouse_id", ""),
            ]
        )
    out.seek(0)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="members.csv → COPY 导入 member")
    p.add_argument("csv_path", help="CSV 路径（首行为表头）")
    args = p.parse_args()

    with open(args.csv_path, "r", encoding="utf-8-sig") as f:
        data = f.read()

    if not data.strip():
        print("文件为空", file=sys.stderr)
        return 1

    try:
        buf = _build_copy_stream(data)
    except ValueError as e:
        print(f"CSV 处理失败：{e}", file=sys.stderr)
        return 1

    copy_sql = (
        "COPY member (member_id, tree_id, name, gender, birth_date, death_date, "
        "birth_year, death_year, bio, "
        "generation_level, father_id, mother_id, spouse_id) FROM STDIN "
        "WITH (FORMAT csv, HEADER true, ENCODING 'UTF8', NULL '')"
    )

    conn = None
    cur = None
    try:
        conn = connect_genealogy_db()
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("ALTER TABLE member DISABLE TRIGGER USER;")
        cur.copy_expert(copy_sql, buf)
        cur.execute("ALTER TABLE member ENABLE TRIGGER USER;")
        cur.execute(
            "SELECT setval(pg_get_serial_sequence('member','member_id'), "
            "(SELECT COALESCE(MAX(member_id),1) FROM member));"
        )
        cur.close()
    except (psycopg2.Error, UnicodeDecodeError, ValueError) as e:
        print(f"导入失败：{e}", file=sys.stderr)
        if isinstance(e, UnicodeDecodeError):
            print(
                "连接串编码错误：请确认 .env 为 UTF-8 且含 GENEALOGY_DB_*；"
                "并删除 Windows 环境变量中乱码的 GENEALOGY_DSN / GENEALOGY_DATABASE_URL，"
                "或 CMD 执行 set GENEALOGY_DSN= 与 set GENEALOGY_DATABASE_URL=。",
                file=sys.stderr,
            )
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
