"""
寻根溯源 — Flask Web 应用
"""
from __future__ import annotations

import os
import re
import regex
from collections import deque
from decimal import ROUND_HALF_UP, Decimal
from datetime import date
from dotenv import load_dotenv
from flask import Flask, current_app, flash, redirect, render_template, request, url_for
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from sqlalchemy import create_engine, func, or_, select, text, update
from sqlalchemy.engine.url import URL
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from werkzeug.security import check_password_hash, generate_password_hash

from models import Base, Genealogy, GenealogyCollaborator, Member, User

load_dotenv(encoding="utf-8")

# generate_bulk_data.py 生成的谱名：模拟族谱1 … 模拟族谱10；网站侧不再展示与放行
_BULK_MOCK_TITLE = re.compile(r"^模拟族谱\d+$")


def _is_bulk_mock_genealogy_title(title: str) -> bool:
    return bool(_BULK_MOCK_TITLE.fullmatch(title))


def _full_access_username_set() -> set[str]:
    """登录后可浏览库内全部族谱与成员（含他人创建与批量导入）。逗号分隔，见环境变量 FULL_ACCESS_USERNAMES。"""
    raw = os.environ.get("FULL_ACCESS_USERNAMES", "3377673546")
    return {x.strip() for x in raw.split(",") if x.strip()}


def _user_has_full_access(session: Session, user_id: int) -> bool:
    u = session.get(User, user_id)
    if not u:
        return False
    return u.username in _full_access_username_set()


def _pct_two_decimals(part: int, whole: int) -> str:
    """占比（%），先按高精度比例换算再四舍五入到两位小数。"""
    if whole <= 0:
        return "0.00"
    q = (Decimal(part) / Decimal(whole) * 100).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return format(q, "f")


def _database_connect_arg():
    """
    优先使用分项配置（适合中文密码、避免一行 URL 在 Windows 下编码问题）。
    若设置了 GENEALOGY_DB_HOST,则走 URL.create;否则使用 GENEALOGY_DATABASE_URL 字符串。
    """
    if os.environ.get("GENEALOGY_DB_HOST", "").strip():
        return URL.create(
            drivername="postgresql+psycopg2",
            username=os.environ.get("GENEALOGY_DB_USER", "postgres"),
            password=os.environ.get("GENEALOGY_DB_PASSWORD", ""),
            host=os.environ["GENEALOGY_DB_HOST"].strip(),
            port=int(os.environ.get("GENEALOGY_DB_PORT", "5432")),
            database=os.environ.get("GENEALOGY_DB_NAME", "genealogy_db"),
        )
    return os.environ.get(
        "GENEALOGY_DATABASE_URL",
        "postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/genealogy_db",
    )


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")

engine = create_engine(_database_connect_arg(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


@app.context_processor
def inject_back_nav():
    """各页「返回上一栏目」目标：非浏览器 history.back。"""
    from flask import request, url_for

    ep = request.endpoint
    if not ep or ep == "static":
        return {"back_nav": None}
    va = request.view_args or {}
    gid = va.get("gid")

    if ep == "index":
        return {"back_nav": None}
    if ep == "login":
        return {"back_nav": {"url": url_for("index"), "label": "首页"}}
    if ep == "register":
        return {"back_nav": {"url": url_for("login"), "label": "登录"}}
    if ep == "dashboard":
        return {"back_nav": None}
    if ep == "genealogies":
        return {"back_nav": {"url": url_for("dashboard"), "label": "总览"}}
    if ep == "genealogy_new":
        return {"back_nav": {"url": url_for("genealogies"), "label": "族谱列表"}}
    if ep == "genealogy_edit" and gid is not None:
        return {"back_nav": {"url": url_for("genealogies"), "label": "族谱列表"}}
    if ep == "members_list" and gid is not None:
        return {"back_nav": {"url": url_for("genealogy_edit", gid=gid), "label": "编辑族谱"}}
    if ep in ("member_new", "member_edit") and gid is not None:
        return {"back_nav": {"url": url_for("members_list", gid=gid), "label": "成员列表"}}
    if ep in ("tree_preview", "ancestors_view", "kinship") and gid is not None:
        return {"back_nav": {"url": url_for("members_list", gid=gid), "label": "成员列表"}}
    return {"back_nav": None}


@app.context_processor
def inject_leave_modal_options():
    """注册页离开弹窗不提供「保存并离开」（应使用「创建账户」提交）。"""
    from flask import request

    ep = request.endpoint
    return {"leave_modal_show_save": ep not in ("register", "login")}


@login_manager.user_loader
def load_user(uid: str):
    try:
        uid_i = int(uid)
    except (TypeError, ValueError):
        return None
    with Session(engine) as s:
        return s.get(User, uid_i)


def get_session() -> Session:
    return SessionLocal()


def _parse_revision_date(raw: str) -> date | None:
    """修谱日期：支持 YYYY-MM-DD 与 YYYY/MM/DD。"""
    s = raw.strip().replace("/", "-")
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


# 浏览器提交的「本机今日」若晚于服务器 date.today()（常见于容器/WSL 系统时间未同步），
# 在若干天内采信客户端，使「不能晚于今天」与 Windows/本机日历一致；非数据库时间。
_REVISION_DATE_CLIENT_SYNC_MAX_DAYS = 14


def _effective_revision_date_cap(client_today_raw: str | None) -> date:
    server = date.today()
    if not client_today_raw:
        return server
    client = _parse_revision_date(client_today_raw.strip())
    if client is None:
        return server
    if client > server and (client - server).days <= _REVISION_DATE_CLIENT_SYNC_MAX_DAYS:
        return client
    return server


def _touch_genealogy_revision_date(
    session: Session, genealogy_id: int, client_today_raw: str | None = None
) -> None:
    """族谱有实质变更并保存后，将修谱日期更新为「今日」（与 _effective_revision_date_cap 一致）。"""
    geo = session.get(Genealogy, genealogy_id)
    if geo:
        geo.revision_date = _effective_revision_date_cap(client_today_raw)


def _member_counts_by_tree_ids(session: Session, gid_list: list[int]) -> dict[int, int]:
    """每部族谱内 member 表行数(tree_id = genealogy.id),无成员则为 0。"""
    if not gid_list:
        return {}
    rows = session.execute(
        select(Member.tree_id, func.count(Member.member_id))
        .where(Member.tree_id.in_(gid_list))
        .group_by(Member.tree_id)
    ).all()
    counts = {int(gid): int(c) for gid, c in rows}
    return {gid: counts.get(gid, 0) for gid in gid_list}


def _year_from_form_field(raw: str) -> int | None:
    """从 YYYY-MM-DD(date 控件)或纯数字年份解析为整数年份。"""
    s = raw.strip()
    if not s:
        return None
    if len(s) >= 5 and s[4] == "-":
        try:
            return int(s[:4])
        except ValueError:
            return None
    try:
        return int(s)
    except ValueError:
        return None


def _iso_date_from_form_prefix(raw: str) -> date | None:
    """若 raw 以 YYYY-MM-DD 开头则解析为 date,否则 None。"""
    s = raw.strip()
    if len(s) < 10 or s[4] != "-" or s[7] != "-":
        return None
    try:
        return date(int(s[0:4]), int(s[5:7]), int(s[8:10]))
    except ValueError:
        return None


def _parse_member_years_from_form() -> tuple[int | None, int | None] | None:
    """解析 POST 中的出生年、去世年(date 字段名 birth_date / death_date,与 birth_year/death_year 列一致)"""
    by = request.form.get("birth_date", "").strip() or request.form.get("birth_year", "").strip()
    dy = request.form.get("death_date", "").strip() or request.form.get("death_year", "").strip()
    bi = _year_from_form_field(by) if by else None
    di = _year_from_form_field(dy) if dy else None
    if by and bi is None:
        flash("出生日期格式无效")
        return None
    if dy and di is None:
        flash("去世日期格式无效")
        return None
    today = date.today()
    bd = _iso_date_from_form_prefix(by) if by else None
    dd = _iso_date_from_form_prefix(dy) if dy else None
    if bd is not None and bd > today:
        flash("出生日期不能晚于今天")
        return None
    if dd is not None and dd > today:
        flash("去世日期不能晚于今天")
        return None
    if bd is None and bi is not None and bi > today.year:
        flash("出生年不能晚于当前年份")
        return None
    if dd is None and di is not None and di > today.year:
        flash("去世年不能晚于当前年份")
        return None
    if bi is not None and di is not None and di < bi:
        flash("去世年须不早于出生年")
        return None
    return (bi, di)


def _validate_member_cn_name(raw: str) -> str | None:
    """姓名须为 2～4 个汉字（Unicode Script=Han，含繁体、生僻字及 CJK 各扩展区）。返回错误提示或 None。"""
    name = raw.strip()
    if not name:
        return "姓名不能为空"
    # \p{Han} 与 Unicode Han 脚本一致，覆盖 BMP 与各扩展平面表意文字
    if not regex.fullmatch(r"\p{Han}{2,4}", name):
        return "姓名须为 2～4 个汉字（含繁体、生僻字），不可含字母、数字或符号"
    return None


_BIO_MAX_LEN = 500
_USER_USERNAME_MAX = 64
_USER_EMAIL_MAX = 128
_GENEALOGY_TITLE_MAX = 200
_GENEALOGY_SURNAME_MAX = 64


def _escape_like_pattern(s: str) -> str:
    """转义 ILIKE/LIKE 中的 %、_ 与反斜杠，避免用户搜索被当作通配符。"""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _validate_bio_len(raw: str) -> str | None:
    """生平按字符数计（含汉字、字母、标点、空格等），len(raw) 与 Python 字符串一致。"""
    if len(raw) > _BIO_MAX_LEN:
        return (
            f"生平不超过 {_BIO_MAX_LEN} 字（含汉字、字母、标点、空格等），请核对。"
        )
    return None


def _normalize_form_gender(raw: str | None) -> str | None:
    """表单仅传 Male / Female；非法或空返回 None。"""
    g = (raw or "").strip()
    if g == "Female":
        return "Female"
    if g == "Male":
        return "Male"
    return None


def _is_male_gender(g: str) -> bool:
    u = (g or "").strip().upper()
    return u in ("M", "MALE", "男")


def _is_female_gender(g: str) -> bool:
    u = (g or "").strip().upper()
    return u in ("F", "FEMALE", "女")


def _gender_label_cn(g: str) -> str:
    """用于错误提示中的性别描述。"""
    if _is_male_gender(g):
        return "男性"
    if _is_female_gender(g):
        return "女性"
    return "未识别或非男非女"


def _gender_display_cn(g: str | None) -> str:
    """列表展示：M/Male/男→男，F/Female/女→女。"""
    if not g or not str(g).strip():
        return ""
    if _is_male_gender(g):
        return "男"
    if _is_female_gender(g):
        return "女"
    return str(g).strip()


@app.template_filter("gender_cn")
def _gender_cn_filter(g: str | None) -> str:
    return _gender_display_cn(g)


def _format_genealogy_display_title(first_male_name: str | None, tree_id: int) -> str:
    """谱名：首名男性姓名 + 支（树Y），Y 为 genealogy.id；无男性时用占位。"""
    if first_male_name and first_male_name.strip():
        return f"{first_male_name.strip()}支（树{tree_id}）"
    return f"（无男性成员）支（树{tree_id}）"


def _first_male_name_in_tree(session: Session, tree_id: int) -> str | None:
    """同一 tree_id 下按 member_id 升序的第一名男性成员姓名。"""
    m = session.scalar(
        select(Member)
        .where(Member.tree_id == tree_id)
        .where(
            or_(
                Member.gender == "M",
                Member.gender == "Male",
                Member.gender == "男",
            )
        )
        .order_by(Member.member_id)
        .limit(1)
    )
    if not m or not (m.name or "").strip():
        return None
    return (m.name or "").strip()


def _sync_genealogy_title_from_members(session: Session, tree_id: int) -> None:
    geo = session.get(Genealogy, tree_id)
    if not geo:
        return
    nm = _first_male_name_in_tree(session, tree_id)
    geo.title = _format_genealogy_display_title(nm, tree_id)


def _sync_all_genealogy_titles_from_members(session: Session) -> None:
    """族谱 id 重排等批量变更后，为每部族谱刷新 title。"""
    for tid in session.scalars(select(Genealogy.id).order_by(Genealogy.id)).all():
        _sync_genealogy_title_from_members(session, tid)


def _display_genealogy_list_titles(
    session: Session, genealogy_rows: list[Genealogy]
) -> dict[int, str]:
    """
    总览/族谱列表：若已有男性成员，则按首名男性（member_id 最小）+ 支（树id）；
    若无男性成员，则显示用户在库中保存的谱名（可为空，不强制「无男性成员」占位）。
    """
    if not genealogy_rows:
        return {}
    gids = [g.id for g in genealogy_rows]
    rows = session.execute(
        select(Member.tree_id, Member.name)
        .where(Member.tree_id.in_(gids))
        .where(
            or_(
                Member.gender == "M",
                Member.gender == "Male",
                Member.gender == "男",
            )
        )
        .order_by(Member.tree_id, Member.member_id)
    ).all()
    first_name_by_tree: dict[int, str] = {}
    for tree_id, name in rows:
        if tree_id not in first_name_by_tree:
            first_name_by_tree[tree_id] = (name or "").strip()
    out: dict[int, str] = {}
    for g in genealogy_rows:
        nm = first_name_by_tree.get(g.id)
        if nm:
            out[g.id] = _format_genealogy_display_title(nm, g.id)
        else:
            out[g.id] = (g.title or "").strip()
    return out


def _genealogy_form_title_for_edit(session: Session, g: Genealogy) -> str:
    """编辑页谱名输入框：与总览/族谱列表同一规则（有男性则按首名男性，否则用库内谱名）。"""
    nm = _first_male_name_in_tree(session, g.id)
    if nm:
        return _format_genealogy_display_title(nm, g.id)
    return (g.title or "").strip()


def _sync_member_id_sequence(session: Session) -> None:
    """将 member_id 序列对齐到当前 MAX(member_id)，使删空后新成员可从 1 起号。"""
    max_id = session.scalar(select(func.max(Member.member_id)))
    if max_id is None:
        session.execute(
            text(
                "SELECT setval(pg_get_serial_sequence('member', 'member_id')::regclass, 1, false)"
            )
        )
    else:
        session.execute(
            text(
                "SELECT setval(pg_get_serial_sequence('member', 'member_id')::regclass, :m, true)"
            ),
            {"m": max_id},
        )


def _sync_genealogy_id_sequence(session: Session) -> None:
    """将 genealogy.id 序列对齐到 MAX(id)，避免手动指定 id 后 SERIAL 与后续 INSERT 冲突。"""
    max_id = session.scalar(select(func.max(Genealogy.id)))
    if max_id is None:
        session.execute(
            text(
                "SELECT setval(pg_get_serial_sequence('genealogy', 'id')::regclass, 1, false)"
            )
        )
    else:
        session.execute(
            text(
                "SELECT setval(pg_get_serial_sequence('genealogy', 'id')::regclass, :m, true)"
            ),
            {"m": max_id},
        )


def _next_genealogy_id(session: Session) -> int:
    """删除后经 _compact_genealogy_ids 为 1..n，新 id 为 max+1（表空则为 1）。"""
    if session.bind.dialect.name == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(428371)"))
    max_id = session.scalar(select(func.max(Genealogy.id)))
    return (max_id or 0) + 1


def _compact_genealogy_ids(session: Session) -> None:
    """
    将 genealogy.id 按当前升序重排为 1..n，无空号、无重复。
    依赖 member.tree_id、genealogy_collaborator.genealogy_id 的 ON UPDATE CASCADE
    （见 sql/16_genealogy_fk_on_update_cascade.sql 或 01_schema 中对应外键）。
    """
    ids = session.scalars(select(Genealogy.id).order_by(Genealogy.id)).all()
    if not ids:
        return
    sorted_old = list(ids)
    mapping = {old: i + 1 for i, old in enumerate(sorted_old)}
    if all(mapping[o] == o for o in sorted_old):
        return
    off = max(sorted_old) + 1
    for old_id in sorted(mapping.keys(), reverse=True):
        session.execute(
            update(Genealogy).where(Genealogy.id == old_id).values(id=old_id + off)
        )
        session.flush()
    for old_id in sorted(mapping.keys()):
        new_id = mapping[old_id]
        temp = old_id + off
        session.execute(
            update(Genealogy).where(Genealogy.id == temp).values(id=new_id)
        )
        session.flush()
    session.expire_all()


def _compact_member_ids_in_tree(session: Session, tree_id: int) -> None:
    """
    将同一 tree_id 下剩余成员的 member_id 压成连续整数（从当前最小 member_id 起），
    并依赖库中外键 ON UPDATE CASCADE 更新 father_id / mother_id / spouse_id。
    需已执行 sql/14_member_fk_on_update_cascade.sql（或 01_schema 含 ON UPDATE CASCADE）。
    """
    ids = session.scalars(
        select(Member.member_id)
        .where(Member.tree_id == tree_id)
        .order_by(Member.member_id)
    ).all()
    if not ids:
        return
    sorted_old = list(ids)
    min_old = sorted_old[0]
    mapping = {old: min_old + i for i, old in enumerate(sorted_old)}
    if all(mapping[o] == o for o in sorted_old):
        return
    for old_id in sorted(mapping.keys()):
        new_id = mapping[old_id]
        if old_id == new_id:
            continue
        session.execute(
            update(Member).where(Member.member_id == old_id).values(member_id=new_id)
        )
        session.flush()
    session.expire_all()


def _flash_db_error(exc: SQLAlchemyError) -> None:
    orig = getattr(exc, "orig", None)
    msg = str(orig) if orig is not None else str(exc)
    if "CONTEXT:" in msg:
        msg = msg.split("CONTEXT:")[0].strip()
    flash(f"保存失败：{msg}")


def _validate_parent_refs(
    s: Session, gid: int, father_id: int | None, mother_id: int | None, self_id: int | None = None
) -> str | None:
    """
    父/母可为任意族谱中已录入的成员（异姓通婚等）；父亲须为男性、母亲须为女性。
    gid 仅用于保留接口；不再限制父母与本成员同属一族谱。
    """
    if father_id is not None and mother_id is not None and father_id == mother_id:
        return "父亲与母亲不能为同一成员 ID，请核对。"
    if self_id is not None:
        if father_id == self_id or mother_id == self_id:
            return "不能将自己填为父或母，请核对。"
    if father_id is not None:
        p = s.get(Member, father_id)
        if not p:
            return "父亲成员 ID 在系统中不存在，请核对。"
        if not _is_male_gender(p.gender):
            return (
                f"父亲须为男性成员；该 ID 对应成员性别为「{_gender_label_cn(p.gender)}」，"
                "父亲不能为女性，请核对。"
            )
    if mother_id is not None:
        p = s.get(Member, mother_id)
        if not p:
            return "母亲成员 ID 在系统中不存在，请核对。"
        if not _is_female_gender(p.gender):
            return (
                f"母亲须为女性成员；该 ID 对应成员性别为「{_gender_label_cn(p.gender)}」，"
                "母亲不能为男性，请核对。"
            )
    return None


def user_can_access_genealogy(user_id: int, genealogy_id: int) -> bool:
    with Session(engine) as s:
        g = s.get(Genealogy, genealogy_id)
        if not g:
            return False
        if _user_has_full_access(s, user_id):
            return True
        if _is_bulk_mock_genealogy_title(g.title):
            return False
        if g.created_by == user_id:
            return True
        q = select(GenealogyCollaborator).where(
            GenealogyCollaborator.genealogy_id == genealogy_id,
            GenealogyCollaborator.user_id == user_id,
        )
        return s.execute(q).first() is not None


def accessible_genealogy_ids(user_id: int) -> list[int]:
    with Session(engine) as s:
        if _user_has_full_access(s, user_id):
            return sorted(s.scalars(select(Genealogy.id)).all())
        created = s.scalars(
            select(Genealogy.id).where(Genealogy.created_by == user_id)
        ).all()
        collab = s.scalars(
            select(GenealogyCollaborator.genealogy_id).where(
                GenealogyCollaborator.user_id == user_id
            )
        ).all()
        gids = sorted(set(created) | set(collab))
        if not gids:
            return []
        gens = s.scalars(select(Genealogy).where(Genealogy.id.in_(gids))).all()
        return sorted(
            g.id for g in gens if not _is_bulk_mock_genealogy_title(g.title)
        )


@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        if not u or not p:
            flash("请填写用户名和密码")
            return render_template("register.html")
        if len(u) > _USER_USERNAME_MAX:
            flash(f"用户名过长（最多 {_USER_USERNAME_MAX} 个字符）")
            return render_template("register.html")
        em = request.form.get("email", "").strip() or None
        if em is not None and len(em) > _USER_EMAIL_MAX:
            flash(f"邮箱过长（最多 {_USER_EMAIL_MAX} 个字符）")
            return render_template("register.html")
        with Session(engine) as s:
            if s.scalar(select(User).where(User.username == u)):
                flash("用户名已存在")
                return render_template("register.html")
            user = User(
                username=u,
                password_hash=generate_password_hash(p),
                email=em,
            )
            s.add(user)
            s.commit()
        # 同浏览器若仍挂着其它账号的会话，直接进 /login 会被「已登录」重定向到总览，导致闪讯在总览上出现
        logout_user()
        flash("注册成功，请登录")
        return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        with Session(engine) as s:
            user = s.scalar(select(User).where(User.username == u))
            if user and check_password_hash(user.password_hash, p):
                login_user(user)
                return redirect(url_for("dashboard"))
        flash("用户名或密码错误")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    gids = accessible_genealogy_ids(current_user.id)
    if not gids:
        return render_template(
            "dashboard.html",
            total=0,
            male=0,
            female=0,
            male_pct="0.00",
            female_pct="0.00",
            genealogies=[],
            member_counts={},
            display_titles={},
        )
    with Session(engine) as s:
        total = s.scalar(
            select(func.count()).select_from(Member).where(Member.tree_id.in_(gids))
        )
        male = s.scalar(
            select(func.count())
            .select_from(Member)
            .where(
                Member.tree_id.in_(gids),
                or_(Member.gender == "M", Member.gender == "Male", Member.gender == "男"),
            )
        )
        female = s.scalar(
            select(func.count())
            .select_from(Member)
            .where(
                Member.tree_id.in_(gids),
                or_(Member.gender == "F", Member.gender == "Female", Member.gender == "女"),
            )
        )
        gens = s.scalars(
            select(Genealogy).where(Genealogy.id.in_(gids)).order_by(Genealogy.id)
        ).all()
        member_counts = _member_counts_by_tree_ids(s, gids)
        display_titles = _display_genealogy_list_titles(s, gens)
    t = total or 0
    m = male or 0
    f = female or 0
    return render_template(
        "dashboard.html",
        total=t,
        male=m,
        female=f,
        male_pct=_pct_two_decimals(m, t),
        female_pct=_pct_two_decimals(f, t),
        genealogies=gens,
        member_counts=member_counts,
        display_titles=display_titles,
    )


@app.route("/genealogies")
@login_required
def genealogies():
    gids = accessible_genealogy_ids(current_user.id)
    with Session(engine) as s:
        rows = s.scalars(
            select(Genealogy).where(Genealogy.id.in_(gids)).order_by(Genealogy.id)
        ).all()
        member_counts = _member_counts_by_tree_ids(s, gids)
        display_titles = _display_genealogy_list_titles(s, rows)
    return render_template(
        "genealogies.html",
        rows=rows,
        member_counts=member_counts,
        display_titles=display_titles,
    )


@app.route("/genealogy/new", methods=["GET", "POST"])
@login_required
def genealogy_new():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        surname = request.form.get("surname", "").strip()
        rd = request.form.get("revision_date", "").strip()
        rev = _parse_revision_date(rd) if rd else None
        cap = _effective_revision_date_cap(request.form.get("revision_date_client_today"))
        if rd and rev is None:
            flash("修谱日期格式须为 YYYY-MM-DD")
            return render_template("genealogy_form.html", g=None)
        if rev is not None and rev > cap:
            flash("修谱日期不能晚于今天（以本机或服务器日历为准）")
            return render_template("genealogy_form.html", g=None)
        if not surname:
            flash("姓氏必填")
            return render_template("genealogy_form.html", g=None)
        if len(surname) > _GENEALOGY_SURNAME_MAX:
            flash(f"姓氏最多 {_GENEALOGY_SURNAME_MAX} 字，请缩短后重试")
            return render_template("genealogy_form.html", g=None)
        with Session(engine) as s:
            nid = _next_genealogy_id(s)
            if len(title) > _GENEALOGY_TITLE_MAX:
                flash(f"谱名最多 {_GENEALOGY_TITLE_MAX} 字，请缩短后重试")
                return render_template("genealogy_form.html", g=None)
            g = Genealogy(
                id=nid,
                title=title,
                surname=surname,
                revision_date=rev,
                created_by=current_user.id,
            )
            s.add(g)
            s.flush()
            _sync_genealogy_id_sequence(s)
            s.commit()
            flash("已创建族谱")
            return redirect(url_for("genealogy_edit", gid=g.id))
    return render_template("genealogy_form.html", g=None, is_creator=False)


@app.route("/genealogy/<int:gid>/delete", methods=["POST"])
@login_required
def genealogy_delete(gid: int):
    if not user_can_access_genealogy(current_user.id, gid):
        flash("无权访问该族谱")
        return redirect(url_for("genealogies"))
    with Session(engine) as s:
        g = s.get(Genealogy, gid)
        if not g:
            flash("族谱不存在")
            return redirect(url_for("dashboard"))
        if g.created_by != current_user.id:
            flash("仅创建者可删除族谱")
            return redirect(url_for("genealogy_edit", gid=gid))
        try:
            s.delete(g)
            s.flush()
            _sync_member_id_sequence(s)
            _compact_genealogy_ids(s)
            _sync_all_genealogy_titles_from_members(s)
            _sync_genealogy_id_sequence(s)
            s.commit()
        except SQLAlchemyError as e:
            s.rollback()
            _flash_db_error(e)
            return redirect(url_for("genealogy_edit", gid=gid))
    flash("族谱已删除")
    return redirect(url_for("dashboard"))


@app.route("/genealogy/<int:gid>/edit", methods=["GET", "POST"])
@login_required
def genealogy_edit(gid: int):
    if not user_can_access_genealogy(current_user.id, gid):
        flash("无权访问该族谱")
        return redirect(url_for("genealogies"))
    with Session(engine) as s:
        g = s.get(Genealogy, gid)
        if not g:
            flash("族谱不存在")
            return redirect(url_for("genealogies"))
        if request.method == "POST":
            t = request.form.get("title", "").strip()
            su = request.form.get("surname", "").strip() or g.surname
            if len(t) > _GENEALOGY_TITLE_MAX or len(su) > _GENEALOGY_SURNAME_MAX:
                flash(
                    f"谱名最多 {_GENEALOGY_TITLE_MAX} 字、姓氏最多 {_GENEALOGY_SURNAME_MAX} 字，请缩短后重试"
                )
                return redirect(url_for("genealogy_edit", gid=gid))
            g.title = t
            g.surname = su
            _touch_genealogy_revision_date(
                s, gid, request.form.get("revision_date_client_today")
            )
            s.commit()
            flash("已保存")
            return redirect(url_for("genealogy_edit", gid=gid))
        collabs = s.scalars(
            select(User)
            .join(
                GenealogyCollaborator,
                GenealogyCollaborator.user_id == User.id,
            )
            .where(GenealogyCollaborator.genealogy_id == gid)
        ).all()
        is_creator = g.created_by == current_user.id
        title_for_form = _genealogy_form_title_for_edit(s, g)
    return render_template(
        "genealogy_form.html",
        g=g,
        title_for_form=title_for_form,
        collabs=collabs,
        is_creator=is_creator,
    )


@app.route("/genealogy/<int:gid>/invite", methods=["POST"])
@login_required
def genealogy_invite(gid: int):
    if not user_can_access_genealogy(current_user.id, gid):
        flash("无权邀请")
        return redirect(url_for("genealogies"))
    uname = request.form.get("username", "").strip()
    if not uname:
        flash("请填写对方用户名")
        return redirect(url_for("genealogy_edit", gid=gid))
    with Session(engine) as s:
        g = s.get(Genealogy, gid)
        if g.created_by != current_user.id:
            flash("仅创建者可邀请协作者")
            return redirect(url_for("genealogy_edit", gid=gid))
        u = s.scalar(select(User).where(User.username == uname))
        if not u:
            flash("用户不存在")
            return redirect(url_for("genealogy_edit", gid=gid))
        if u.id == current_user.id:
            flash("不能邀请自己")
            return redirect(url_for("genealogy_edit", gid=gid))
        exists = s.scalar(
            select(GenealogyCollaborator).where(
                GenealogyCollaborator.genealogy_id == gid,
                GenealogyCollaborator.user_id == u.id,
            )
        )
        if exists:
            flash("已是协作者")
            return redirect(url_for("genealogy_edit", gid=gid))
        s.add(
            GenealogyCollaborator(
                genealogy_id=gid, user_id=u.id, invited_by=current_user.id
            )
        )
        _touch_genealogy_revision_date(
            s, gid, request.form.get("revision_date_client_today")
        )
        s.commit()
        flash("已添加协作者")
    return redirect(url_for("genealogy_edit", gid=gid))


@app.route("/genealogy/<int:gid>/members")
@login_required
def members_list(gid: int):
    if not user_can_access_genealogy(current_user.id, gid):
        flash("无权访问")
        return redirect(url_for("genealogies"))
    q = request.args.get("q", "").strip()
    try:
        with Session(engine) as s:
            ordered_ids = s.scalars(
                select(Member.member_id)
                .where(Member.tree_id == gid)
                .order_by(Member.member_id)
            ).all()
            rank_map = {mid: i + 1 for i, mid in enumerate(ordered_ids)}
            stmt = select(Member).where(Member.tree_id == gid)
            if q:
                stmt = stmt.where(
                    Member.name.ilike(f"%{_escape_like_pattern(q)}%", escape="\\")
                )
            stmt = stmt.order_by(Member.member_id)
            rows = s.scalars(stmt).all()
    except SQLAlchemyError:
        current_app.logger.exception("members_list query failed (schema mismatch?)")
        flash(
            "无法加载成员：数据库 member 表与当前程序不一致。"
            "请清空后执行 sql/01_schema.sql 与 sql/02_indexes.sql（列须与 members.csv 表头一致）。"
        )
        return redirect(url_for("genealogy_edit", gid=gid))
    return render_template(
        "members.html", gid=gid, rows=rows, q=q, rank_map=rank_map
    )


@app.route("/genealogy/<int:gid>/member/new", methods=["GET", "POST"])
@login_required
def member_new(gid: int):
    if not user_can_access_genealogy(current_user.id, gid):
        flash("无权访问")
        return redirect(url_for("genealogies"))
    with Session(engine) as s:
        if request.method == "POST":
            parsed = _parse_member_years_from_form()
            if parsed is None:
                return render_template("member_form.html", gid=gid, m=None)
            by, dy = parsed
            try:
                father_id = int(f) if (f := request.form.get("father_id", "").strip()) else None
                mother_id = int(mo) if (mo := request.form.get("mother_id", "").strip()) else None
                spouse_id = int(sp) if (sp := request.form.get("spouse_id", "").strip()) else None
            except ValueError:
                flash("父亲、母亲、配偶成员 ID 须为整数，或留空")
                return render_template("member_form.html", gid=gid, m=None)
            err = _validate_parent_refs(s, gid, father_id, mother_id, self_id=None)
            if err:
                flash(err)
                return render_template("member_form.html", gid=gid, m=None)
            nm = request.form.get("name", "").strip()
            name_err = _validate_member_cn_name(nm)
            if name_err:
                flash(name_err)
                return render_template("member_form.html", gid=gid, m=None)
            bio_raw = request.form.get("bio", "")
            bio_err = _validate_bio_len(bio_raw)
            if bio_err:
                flash(bio_err)
                return render_template("member_form.html", gid=gid, m=None)
            gn_raw = request.form.get("generation_level", "").strip()
            if gn_raw:
                try:
                    gl = int(gn_raw)
                except ValueError:
                    flash("辈分须为整数，或留空")
                    return render_template("member_form.html", gid=gid, m=None)
            else:
                gl = None
            m = Member(
                tree_id=gid,
                name=nm,
                gender=_normalize_form_gender(request.form.get("gender")) or "Male",
                birth_year=by,
                death_year=dy,
                bio=bio_raw.strip() or None,
                father_id=father_id,
                mother_id=mother_id,
                spouse_id=spouse_id,
                generation_level=gl,
                created_by=current_user.id,
            )
            try:
                s.add(m)
                _touch_genealogy_revision_date(
                    s, gid, request.form.get("revision_date_client_today")
                )
                s.commit()
            except SQLAlchemyError as e:
                s.rollback()
                _flash_db_error(e)
                return render_template("member_form.html", gid=gid, m=None)
            flash("成员已添加")
            return redirect(url_for("members_list", gid=gid))
        return render_template("member_form.html", gid=gid, m=None)


@app.route("/genealogy/<int:gid>/member/<int:mid>/edit", methods=["GET", "POST"])
@login_required
def member_edit(gid: int, mid: int):
    if not user_can_access_genealogy(current_user.id, gid):
        flash("无权访问")
        return redirect(url_for("genealogies"))
    with Session(engine) as s:
        m = s.get(Member, mid)
        if not m or m.tree_id != gid:
            flash("成员不存在")
            return redirect(url_for("members_list", gid=gid))
        if request.method == "POST":
            if request.form.get("_delete") == "1":
                tid = m.tree_id
                s.delete(m)
                s.flush()
                try:
                    _compact_member_ids_in_tree(s, tid)
                    _sync_member_id_sequence(s)
                    _touch_genealogy_revision_date(
                        s, tid, request.form.get("revision_date_client_today")
                    )
                    s.commit()
                except SQLAlchemyError as e:
                    s.rollback()
                    _flash_db_error(e)
                    return redirect(url_for("members_list", gid=gid))
                flash("已删除")
                return redirect(url_for("members_list", gid=gid))
            parsed = _parse_member_years_from_form()
            if parsed is None:
                return render_template("member_form.html", gid=gid, m=m)
            by, dy = parsed
            try:
                father_id = int(fi) if (fi := request.form.get("father_id", "").strip()) else None
                mother_id = int(moi) if (moi := request.form.get("mother_id", "").strip()) else None
                spouse_id = int(sp) if (sp := request.form.get("spouse_id", "").strip()) else None
            except ValueError:
                flash("父亲、母亲、配偶成员 ID 须为整数，或留空")
                return render_template("member_form.html", gid=gid, m=m)
            err = _validate_parent_refs(s, gid, father_id, mother_id, self_id=m.member_id)
            if err:
                flash(err)
                return render_template("member_form.html", gid=gid, m=m)
            nm = request.form.get("name", "").strip()
            name_err = _validate_member_cn_name(nm)
            if name_err:
                flash(name_err)
                return render_template("member_form.html", gid=gid, m=m)
            bio_raw = request.form.get("bio", "")
            bio_err = _validate_bio_len(bio_raw)
            if bio_err:
                flash(bio_err)
                return render_template("member_form.html", gid=gid, m=m)
            m.name = nm
            m.gender = _normalize_form_gender(request.form.get("gender")) or m.gender
            m.birth_year = by
            m.death_year = dy
            m.bio = bio_raw.strip() or None
            m.father_id = father_id
            m.mother_id = mother_id
            m.spouse_id = spouse_id
            gn = request.form.get("generation_level", "").strip()
            if gn:
                try:
                    m.generation_level = int(gn)
                except ValueError:
                    flash("辈分须为整数，或留空")
                    return render_template("member_form.html", gid=gid, m=m)
            else:
                m.generation_level = None
            try:
                _touch_genealogy_revision_date(
                    s, gid, request.form.get("revision_date_client_today")
                )
                s.commit()
            except SQLAlchemyError as e:
                s.rollback()
                s.refresh(m)
                _flash_db_error(e)
                return render_template("member_form.html", gid=gid, m=m)
            flash("已保存")
            return redirect(url_for("members_list", gid=gid))
        return render_template("member_form.html", gid=gid, m=m)


def neighbor_ids(s: Session, mid: int) -> set[int]:
    m = s.get(Member, mid)
    if not m:
        return set()
    n: set[int] = set()
    if m.father_id:
        n.add(m.father_id)
    if m.mother_id:
        n.add(m.mother_id)
    if m.spouse_id:
        n.add(m.spouse_id)
    for cid in s.scalars(
        select(Member.member_id).where(
            or_(Member.father_id == mid, Member.mother_id == mid)
        )
    ).all():
        n.add(cid)
    return n


def bfs_path(s: Session, start: int, goal: int) -> list[int] | None:
    if start == goal:
        return [start]
    q: deque[int] = deque([start])
    prev: dict[int, int | None] = {start: None}
    while q:
        u = q.popleft()
        for v in neighbor_ids(s, u):
            if v in prev:
                continue
            prev[v] = u
            if v == goal:
                chain: list[int] = []
                cur: int | None = v
                while cur is not None:
                    chain.append(cur)
                    cur = prev[cur]  # type: ignore[assignment]
                chain.reverse()
                return chain
            q.append(v)
    return None


@app.route("/genealogy/<int:gid>/tree")
@login_required
def tree_preview(gid: int):
    if not user_can_access_genealogy(current_user.id, gid):
        flash("无权访问")
        return redirect(url_for("genealogies"))
    root_id = request.args.get("root", "").strip()
    with Session(engine) as s:
        if root_id:
            try:
                rid = int(root_id)
            except ValueError:
                flash("根成员 ID 须为整数")
                return redirect(url_for("tree_preview", gid=gid))
            root = s.get(Member, rid)
            if not root or root.tree_id != gid:
                flash("根成员无效")
                return redirect(url_for("tree_preview", gid=gid))
        else:
            root = s.scalar(
                select(Member)
                .where(Member.tree_id == gid)
                .where(Member.father_id.is_(None), Member.mother_id.is_(None))
                .order_by(Member.member_id)
                .limit(1)
            )
            if not root:
                root = s.scalar(
                    select(Member).where(Member.tree_id == gid).order_by(Member.member_id).limit(1)
                )
        lines: list[tuple[int, str, int]] = []

        def walk(pid: int, depth: int, seen: set[int]):
            if pid in seen:
                return
            seen.add(pid)
            m = s.get(Member, pid)
            if not m:
                return
            lines.append((depth, m.name, m.member_id))
            for cid in s.scalars(
                select(Member.member_id)
                .where(Member.tree_id == gid)
                .where(or_(Member.father_id == pid, Member.mother_id == pid))
                .order_by(Member.member_id)
            ).all():
                walk(cid, depth + 1, seen)

        if root:
            walk(root.member_id, 0, set())
    return render_template("tree.html", gid=gid, lines=lines, root=root)


@app.route("/genealogy/<int:gid>/ancestors")
@login_required
def ancestors_view(gid: int):
    if not user_can_access_genealogy(current_user.id, gid):
        flash("无权访问")
        return redirect(url_for("genealogies"))
    mid = request.args.get("id", "").strip()
    rows = []
    if mid:
        try:
            mid_i = int(mid)
        except ValueError:
            flash("成员 ID 须为整数")
            return render_template("ancestors.html", gid=gid, rows=[], mid=mid)
        with Session(engine) as s:
            sql = text(
                """
                WITH RECURSIVE anc AS (
                    SELECT member_id, name, gender, birth_year, father_id, mother_id, 0 AS hop,
                           ARRAY[member_id::bigint] AS path_ids
                    FROM member WHERE member_id = :mid AND tree_id = :gid
                    UNION ALL
                    SELECT p.member_id, p.name, p.gender, p.birth_year, p.father_id, p.mother_id,
                           a.hop + 1, a.path_ids || p.member_id
                    FROM anc a
                    JOIN member p ON p.member_id = a.father_id OR p.member_id = a.mother_id
                    WHERE NOT (p.member_id = ANY (a.path_ids))
                )
                SELECT DISTINCT ON (member_id) member_id, name, gender, birth_year, hop
                FROM anc WHERE hop > 0 ORDER BY member_id, hop
                """
            )
            raw = s.execute(sql, {"mid": mid_i, "gid": gid}).mappings().all()
            rows = sorted(raw, key=lambda r: (r["hop"], r["member_id"]))
    return render_template("ancestors.html", gid=gid, rows=rows, mid=mid)


@app.route("/genealogy/<int:gid>/kinship", methods=["GET", "POST"])
@login_required
def kinship(gid: int):
    if not user_can_access_genealogy(current_user.id, gid):
        flash("无权访问")
        return redirect(url_for("genealogies"))
    path_names: list[str] = []
    a = b = None
    if request.method == "POST":
        a = request.form.get("a", "").strip()
        b = request.form.get("b", "").strip()
        if a.isdigit() and b.isdigit():
            with Session(engine) as s:
                ma = s.get(Member, int(a))
                mb = s.get(Member, int(b))
                if (
                    ma
                    and mb
                    and ma.tree_id == gid
                    and mb.tree_id == gid
                ):
                    p = bfs_path(s, int(a), int(b))
                    if p:
                        for i in p:
                            mm = s.get(Member, i)
                            path_names.append(mm.name if mm else str(i))
                    else:
                        flash("两人之间未发现由血缘/婚姻连成的通路")
                else:
                    flash("成员 ID 须属于本族谱")
    return render_template("kinship.html", gid=gid, path=path_names, a=a, b=b)


@app.cli.command("init-db")
def init_db():
    """仅开发用：根据模型建表（生产请用 sql/01_schema.sql 以获得触发器）。"""
    Base.metadata.create_all(engine)
    print("Tables created (no triggers). Run sql/01_schema.sql for full constraints.")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
