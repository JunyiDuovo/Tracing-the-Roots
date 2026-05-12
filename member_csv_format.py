"""成员 CSV 导入/导出共用：表首行必须与导出文件完全一致（列名与顺序）。"""

from __future__ import annotations

# 须与 Flask 导出、数据库 COPY 成员列语义一致。
MEMBER_CSV_HEADERS: tuple[str, ...] = (
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
)
