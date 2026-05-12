"""总览 CSV 批量导入成员：校验表头与导出严格一致；替换涉及族谱的成员数据。"""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import IO

import regex
from sqlalchemy.engine import Engine

from member_csv_format import MEMBER_CSV_HEADERS

_BIO_MAX_LEN = 500
_GENDER_ALLOWED = frozenset(("M", "F", "Male", "Female", "男", "女"))


def _name_ok(nm: str) -> bool:
    return bool(regex.fullmatch(r"\p{Han}{2,4}", nm.strip()))


def _cell_strip(cell: str) -> str:
    return (cell or "").strip()


def _cell_to_year(
    cell: str, *, allow_empty: bool, row_hint: str, label: str
) -> str:
    s = _cell_strip(cell)
    if not s:
        if allow_empty:
            return ""
        raise ValueError(
            f"{row_hint}缺少{label}信息：请在 birth_date 或 birth_year 中填写生日或等价年份。"
        )
    if len(s) >= 4 and s[:4].isdigit():
        y = int(s[:4])
        if 800 <= y <= 3000:
            return str(y)
    raise ValueError(
        f"{row_hint}{label}字段无法解析为日期或年份：{cell!r}（可用 YYYY-MM-DD 或 800–3000 间的四位年份）。"
    )


def _cell_to_iso_date(cell: str, row_hint: str) -> str | None:
    s = _cell_strip(cell)
    if len(s) < 10 or s[4] != "-" or s[7] != "-":
        return None
    try:
        d = date(int(s[0:4]), int(s[5:7]), int(s[8:10]))
        if d.year < 800 or d.year > 3000:
            return None
        return f"{d.year:04d}-{d.month:02d}-{d.day:02d}"
    except ValueError:
        raise ValueError(f"{row_hint}日期格式非法：{cell!r}（须为 YYYY-MM-DD）。")


def _validate_life_order(
    *,
    birth_iso: str | None,
    death_iso: str | None,
    birth_y: str,
    death_y: str,
    row_hint: str,
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
        raise ValueError(f"{row_hint}去世日期/年份须不早于出生（请检查 birth_* 与 death_*）。")


def _birth_death_copy_fields(lo: dict[str, str], row_hint: str) -> tuple[str, str, str, str]:
    bir_raw = (lo.get("birth_date") or lo.get("birth_year") or "").strip()
    dth_raw = (lo.get("death_date") or lo.get("death_year") or "").strip()
    if not bir_raw:
        raise ValueError(f"{row_hint}须填写 birth_date 或 birth_year（出生不可为空）。")

    bir_iso = _cell_to_iso_date(bir_raw, row_hint)
    if bir_iso:
        bir_y = bir_iso[:4]
        bir_d_cell = bir_iso
    else:
        bir_d_cell = ""
        bir_y = _cell_to_year(
            bir_raw, allow_empty=False, row_hint=row_hint, label="出生"
        )

    death_iso = _cell_to_iso_date(dth_raw, row_hint) if dth_raw else None
    if not dth_raw:
        dth_y_cell = ""
        death_d_cell = ""
    elif death_iso:
        death_d_cell = death_iso
        dth_y_cell = death_iso[:4]
    else:
        death_d_cell = ""
        dth_y_cell = _cell_to_year(
            dth_raw, allow_empty=True, row_hint=row_hint, label="去世"
        )

    _validate_life_order(
        birth_iso=bir_iso,
        death_iso=death_iso,
        birth_y=bir_y,
        death_y=dth_y_cell or "",
        row_hint=row_hint,
    )
    return bir_d_cell, death_d_cell, bir_y, dth_y_cell


def _parse_opt_ref_id(raw: str, label: str, row_hint: str) -> str:
    """父母/配偶 ID：留空或正整数。"""
    s = _cell_strip(raw)
    if not s:
        return ""
    try:
        v = int(s)
    except ValueError:
        raise ValueError(f"{row_hint}列「{label}」须为整数或留空，当前为 {raw!r}。")
    if v <= 0:
        raise ValueError(f"{row_hint}列「{label}」须为正整数或留空。")
    return str(v)


def _parse_opt_int(raw: str, label: str, row_hint: str) -> str:
    s = _cell_strip(raw)
    if not s:
        return ""
    try:
        v = int(s)
    except ValueError:
        raise ValueError(f"{row_hint}列「{label}」须为整数或留空，当前为 {raw!r}。")
    if label == "generation_level":
        if v < 1:
            raise ValueError(
                f"{row_hint}辈分(generation_level)须为不小于 1 的自然数，或留空。"
            )
    return str(v)


def _parse_member_id(raw: str, row_hint: str) -> int:
    s = _cell_strip(raw)
    if not s:
        raise ValueError(f"{row_hint}member_id 不能为空。")
    try:
        v = int(s)
    except ValueError:
        raise ValueError(f"{row_hint}member_id 须为整数，当前为 {raw!r}。")
    if v <= 0:
        raise ValueError(f"{row_hint}member_id 须为正整数。")
    return v


def _parse_tree_id(raw: str, row_hint: str) -> int:
    s = _cell_strip(raw)
    if not s:
        raise ValueError(f"{row_hint}tree_id 不能为空。")
    try:
        v = int(s)
    except ValueError:
        raise ValueError(f"{row_hint}tree_id 须为整数，当前为 {raw!r}。")
    if v <= 0:
        raise ValueError(f"{row_hint}tree_id 须为正整数。")
    return v


def format_required_header_help() -> str:
    return "第一行表头必须与导出文件完全一致如下（英文字段名与顺序缺一不可）：「" + "，".join(MEMBER_CSV_HEADERS) + "」。"


def validate_headers(row: list[str]) -> list[str]:
    errs: list[str] = []
    got = [_cell_strip(c) for c in row]
    if len(got) != len(MEMBER_CSV_HEADERS):
        errs.append(
            f"表头列数为 {len(got)}，应为 {len(MEMBER_CSV_HEADERS)}。"
            + format_required_header_help()
        )
        if len(got) <= len(MEMBER_CSV_HEADERS):
            exp = list(MEMBER_CSV_HEADERS)
            for i in range(min(len(exp), len(got))):
                if exp[i] != got[i]:
                    errs.append(f"表头第 {i + 1} 列：应为 «{exp[i]}»，当前为 «{got[i]}»；请修改为与导出文件一致后再导入。")
            return errs
        for i in range(len(MEMBER_CSV_HEADERS)):
            if MEMBER_CSV_HEADERS[i] != got[i]:
                errs.append(f"表头第 {i + 1} 列：应为 «{MEMBER_CSV_HEADERS[i]}»，当前为 «{got[i]}»；请修改。")
        return errs
    for i, (e, g) in enumerate(zip(MEMBER_CSV_HEADERS, got, strict=True)):
        if e != g:
            errs.append(
                f"表头第 {i + 1} 列必须为 «{e}»，检测到 «{g}»。"
                + "请勿增删列、改英文名或调换顺序。"
            )
    return errs


def validate_and_build_copy_buffer(
    text: str,
    allowed_tree_ids: set[int],
    existing_tree_ids: set[int],
) -> tuple[list[str], io.StringIO | None, set[int], int]:
    """
    返回：(错误信息列表（空则表示通过）, 供 COPY 的 CSV 缓冲区, CSV 中出现的 tree_id 集合, 成员行数)。
    COPY 缓冲区首行为列名 HEADER true。
    """
    errs: list[str] = []
    if not text or not text.strip():
        errs.append("文件内容为空（请上传含表头和数据行的 UTF-8 CSV）。")
        return errs, None, set(), 0

    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        errs.append("CSV 无表头行。")
        return errs, None, set(), 0

    header_errs = validate_headers(header)
    if header_errs:
        errs.extend(header_errs)
        errs.append("请用总览「导出族谱」生成的文件为模板，勿改表头。")
        return errs, None, set(), 0

    seen_member_ids: dict[int, int] = {}
    rows_out: list[tuple[int, list[str]]] = []
    tree_ids_in_csv: set[int] = set()
    line_no = 1

    for cols in reader:
        line_no += 1
        row_hint = f"第 {line_no} 行（表头为第 1 行）："
        if len(cols) != len(MEMBER_CSV_HEADERS):
            errs.append(
                f"{row_hint}本行有 {len(cols)} 列，应为 {len(MEMBER_CSV_HEADERS)} 列；"
                "请检查是否有多余逗号、未加引号的换行或未闭合的引号。"
            )
            continue
        lo = dict(zip(MEMBER_CSV_HEADERS, (_cell_strip(c) for c in cols), strict=True))
        try:
            mid = _parse_member_id(lo["member_id"], row_hint)
            tid = _parse_tree_id(lo["tree_id"], row_hint)
            nm = lo["name"]
            if not nm:
                raise ValueError(f"{row_hint}姓名不能为空。")
            if len(nm) > 100:
                raise ValueError(f"{row_hint}姓名过长（最多 100 个字符）。")
            if not _name_ok(nm):
                raise ValueError(
                    f"{row_hint}姓名「{nm}」须为 2～4 个汉字（与网站录入规则一致），不可含字母、数字或符号。"
                )
            gen = _cell_strip(lo["gender"])
            if gen not in _GENDER_ALLOWED:
                raise ValueError(
                    f"{row_hint}性别须为 M、F、Male、Female、男、女 之一，当前为 «{gen}»。"
                )
            bio = lo.get("bio", "")
            if len(bio) > _BIO_MAX_LEN:
                raise ValueError(f"{row_hint}生平(bio)不得超过 {_BIO_MAX_LEN} 字。")

            glm = _parse_opt_int(lo.get("generation_level", ""), "generation_level", row_hint)
            fid = _parse_opt_ref_id(lo.get("father_id", ""), "father_id", row_hint)
            moth = _parse_opt_ref_id(lo.get("mother_id", ""), "mother_id", row_hint)
            spid = _parse_opt_ref_id(lo.get("spouse_id", ""), "spouse_id", row_hint)

            bir_d, death_d, bir_y, dth_y = _birth_death_copy_fields(lo, row_hint)

            writer_row = [
                str(mid),
                str(tid),
                nm,
                gen,
                bir_d,
                death_d,
                bir_y,
                dth_y,
                bio.replace("\r\n", "\n"),
                glm,
                fid,
                moth,
                spid,
            ]

            if tid not in allowed_tree_ids:
                errs.append(
                    f"{row_hint}tree_id={tid} 不在您有权管理的族谱范围内；仅能导入您有权访问的族谱数据。"
                )
                continue

            if tid not in existing_tree_ids:
                errs.append(
                    f"{row_hint}tree_id={tid} 在数据库中不存在；请先创建该族谱或核对导出的 tree_id。"
                )
                continue

            if mid in seen_member_ids:
                errs.append(
                    f"{row_hint}member_id={mid} 在本文件中重复（另见于第 {seen_member_ids[mid]} 行）；"
                    "同一成员 ID 只能出现一次。"
                )
                continue
            seen_member_ids[mid] = line_no

            tree_ids_in_csv.add(tid)
            rows_out.append((line_no, writer_row))
        except ValueError as e:
            errs.append(str(e))

    if not errs and not rows_out:
        errs.append("除表头外没有任何数据行；请至少包含一条成员记录。")
        return errs, None, set(), 0

    if errs:
        return errs, None, set(), 0

    all_ids = set(seen_member_ids.keys())
    for line_no_csv, row in rows_out:
        row_hint = f"第 {line_no_csv} 行（表头为第 1 行）："
        for label, idx in (("father_id", 10), ("mother_id", 11), ("spouse_id", 12)):
            cell = row[idx]
            if not cell:
                continue
            rid = int(cell)
            if rid not in all_ids:
                errs.append(
                    f"{row_hint}{label}={rid} 在本 CSV 中未定义；"
                    "父母/配偶的成员 ID 必须出现在同一文件内（请先导出完整族谱再编辑）。"
                )

    if errs:
        return errs, None, set(), 0

    rows_out.sort(key=lambda pair: (int(pair[1][1]), int(pair[1][0])))

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(list(MEMBER_CSV_HEADERS))
    for _csv_ln, row in rows_out:
        w.writerow(row)
    out.seek(0)
    return [], out, tree_ids_in_csv, len(rows_out)


COPY_SQL = (
    "COPY member (member_id, tree_id, name, gender, birth_date, death_date, "
    "birth_year, death_year, bio, "
    "generation_level, father_id, mother_id, spouse_id) FROM STDIN "
    "WITH (FORMAT csv, HEADER true, ENCODING 'UTF8', NULL '')"
)


def execute_replace_members_copy(
    engine: Engine, copy_buf: IO[str], tree_ids_to_clear: list[int]
) -> None:
    """在事务中：删除指定族谱全部成员，再 COPY 新数据；失败则回滚并抛出底层异常。"""
    copy_buf.seek(0)
    conn = engine.raw_connection()
    cur = conn.cursor()
    try:
        conn.autocommit = False
        cur.execute("ALTER TABLE member DISABLE TRIGGER USER;")
        for tid in tree_ids_to_clear:
            cur.execute("DELETE FROM member WHERE tree_id = %s", (tid,))
        cur.copy_expert(COPY_SQL, copy_buf)
        cur.execute("ALTER TABLE member ENABLE TRIGGER USER;")
        cur.execute(
            "SELECT setval(pg_get_serial_sequence('member','member_id'), "
            "(SELECT COALESCE(MAX(member_id),1) FROM member));"
        )
        conn.commit()
    except Exception:
        conn.rollback()
        try:
            cur.execute("ALTER TABLE member ENABLE TRIGGER USER;")
            conn.commit()
        except Exception:
            pass
        raise
    finally:
        cur.close()
        conn.close()
