"""
生成 members.csv:多族谱、非整齐总人数。
全局 member_id:按辈分 generation_level 从小到大分配；同一族谱、同辈内先男后女再随机，
保证每谱「第一人」为男性始祖，便于传承；祖先辈分仍 < 后辈。

出生 / 去世为公历合法日期字符串 YYYY-MM-DD；随机出的出生日、去世日均不得晚于「脚本运行时」的本地当日。
若在合理寿命内无法得到不晚于当日的去世日（多为近代出生者），去世日留空（CSV 中空单元格）。
随机配偶须满足中国大陆法定婚龄（男满 22 周岁、女满 20 周岁，以脚本运行日为参照）；未满足则不写入 spouse 或调整主谱夫妻出生日。
夫妻二人出生年份多为相差 ±5 年内（可男大或女大）；仍须满足前述婚龄与本程序其它约束。
入库 import_member_csv 写入 birth_date/death_date 与 birth_year/death_year（PostgreSQL 迁移见 sql/17_member_birth_death_date.sql）。
"""
import csv
import random
from datetime import date

# 固定种子可复现；改为 None 则每次不同
_SEED = None
if _SEED is not None:
    random.seed(_SEED)

# 全谱随机数据的最早公历出生年（含第 1 代男性始祖及其配偶）
_EARLIEST_BIRTH_YEAR = 1000


def _random_date_in_year(year: int, cap: date) -> date:
    """在公元 year 年内均匀随机某一天，且日期不晚于 cap（本地「今天」）。"""
    first = date(year, 1, 1)
    last = date(year, 12, 31)
    last = min(last, cap)
    if first > last:
        return last
    return date.fromordinal(random.randint(first.toordinal(), last.toordinal()))


def _clamp_death_after_birth(birth: date, cap: date) -> date | None:
    """在出生后约 45～92 年间随机去世日，须严格晚于出生且 ≤ cap；若无法在 cap 之前满足则视为仍在世（不写去世日）。"""
    cap_ord = cap.toordinal()
    bir_ord = birth.toordinal()
    low_ord = bir_ord + 45 * 365
    span_hi = bir_ord + 92 * 369
    high_ord = min(span_hi, cap_ord)
    if low_ord >= cap_ord:
        return None
    high_ord = max(high_ord, low_ord + 1)
    high_ord = min(high_ord, cap_ord)
    if low_ord >= high_ord:
        return None
    return date.fromordinal(random.randint(low_ord, high_ord))


def _birth_after_parents(
    father_bd: date, mother_bd: date, year_offset_lo: int, year_offset_hi: int, cap: date
) -> date:
    """子女出生日：其出生年须严格大于父母双方出生年（满足库触发器按年比较）；出生日不晚于 cap。"""
    base_y = max(father_bd.year, mother_bd.year)
    lo_y = base_y + year_offset_lo
    hi_y = min(base_y + year_offset_hi, cap.year)
    lo_y = max(lo_y, base_y + 1, _EARLIEST_BIRTH_YEAR)
    if lo_y > hi_y:
        child_y = hi_y
    else:
        child_y = random.randint(lo_y, hi_y)
    return _random_date_in_year(child_y, cap)


def _iso(d: date) -> str:
    return d.isoformat()


def _iso_death(d: date | None) -> str:
    """去世日可空（仍在世或无法生成符合 cap 的去世日）。"""
    return d.isoformat() if d is not None else ""


# 夫妻二人出生年相差不宜过大（±5 年量级）；不满足法定婚龄时 legalization / 抽样会放宽。
_SPOUSE_BIRTH_YEAR_DELTA_MAX = 5

# 中国大陆法定结婚年龄（周岁；以脚本运行日为参照）
_LEGAL_MARRY_AGE_MALE = 22
_LEGAL_MARRY_AGE_FEMALE = 20


def _full_years_on(birth: date, ref: date) -> int:
    """周岁：到 ref 当日是否已过生日。"""
    y = ref.year - birth.year
    if (ref.month, ref.day) < (birth.month, birth.day):
        y -= 1
    return y


def _pair_meets_marriage_law_cn(hubby_bd: date, wifey_bd: date, ref: date) -> bool:
    """男≥22 周岁、女≥20 周岁。"""
    return (
        _full_years_on(hubby_bd, ref) >= _LEGAL_MARRY_AGE_MALE
        and _full_years_on(wifey_bd, ref) >= _LEGAL_MARRY_AGE_FEMALE
    )


def _meets_own_marriage_age(gender: str, birth: date, ref: date) -> bool:
    """仅本人已达「可登记结婚」周岁的性别下限。"""
    if gender == "Male":
        return _full_years_on(birth, ref) >= _LEGAL_MARRY_AGE_MALE
    if gender == "Female":
        return _full_years_on(birth, ref) >= _LEGAL_MARRY_AGE_FEMALE
    return False


def _legalize_mainline_couple(
    h_bd: date,
    w_bd: date,
    cap: date,
    parent_max_birth_year: int | None,
) -> tuple[date, date]:
    """主谱夫妻二人到 cap 当日均须已满法定婚龄；丈夫出生年必须严格大于父母的最大出生年（若有父母）。"""
    for _ in range(260):
        h_age_ok = _full_years_on(h_bd, cap) >= _LEGAL_MARRY_AGE_MALE
        w_age_ok = _full_years_on(w_bd, cap) >= _LEGAL_MARRY_AGE_FEMALE
        hier_ok = parent_max_birth_year is None or h_bd.year > parent_max_birth_year
        if h_age_ok and w_age_ok and hier_ok:
            return h_bd, w_bd
        if not hier_ok or not h_age_ok:
            ny = h_bd.year
            if parent_max_birth_year is not None:
                ny = max(ny - random.randint(1, 10), parent_max_birth_year + 1)
            else:
                ny = ny - random.randint(1, 10)
            ny = max(_EARLIEST_BIRTH_YEAR, ny)
            ny = min(ny, cap.year)
            h_bd = _random_date_in_year(ny, cap)
            continue
        if not w_age_ok:
            ny = max(_EARLIEST_BIRTH_YEAR, w_bd.year - random.randint(1, 15))
            ny = min(ny, cap.year)
            w_bd = _random_date_in_year(ny, cap)

    return h_bd, w_bd


def _sample_spouse_birth_for_cn_law(child_bd: date, child_is_male: bool, cap: date) -> date | None:
    """随机配偶出生日：优先在子女生年 ±5 年内，再放宽区间，使双方均达法定婚龄。"""
    cy = child_bd.year
    tiers = (
        (-_SPOUSE_BIRTH_YEAR_DELTA_MAX, _SPOUSE_BIRTH_YEAR_DELTA_MAX, 180),
        (-12, 12, 120),
        (-20, 18, 90),
    )
    for lo, hi, cap_n in tiers:
        for _ in range(cap_n):
            delta = random.randint(lo, hi)
            sy = cy + delta
            sy = max(_EARLIEST_BIRTH_YEAR, min(sy, cap.year))
            s_bd = _random_date_in_year(sy, cap)
            if child_is_male:
                hubby, wifey = child_bd, s_bd
            else:
                hubby, wifey = s_bd, child_bd
            if _pair_meets_marriage_law_cn(hubby, wifey, cap):
                return s_bd
    return None


def generate_random_name(surname, gender, male_chars, female_chars):
    """根据姓氏和性别随机生成 2 字或 3 字姓名。"""
    chars_pool = male_chars if gender == "Male" else female_chars
    name_length = random.choice([2, 3])
    if name_length == 2:
        return surname + random.choice(chars_pool)
    return surname + random.choice(chars_pool) + random.choice(chars_pool)


def _bio_parent_line(
    father_id: int | None,
    mother_id: int | None,
    id_to_name: dict[int, str],
    child_gender: str,
) -> str:
    """父母姓名可查时：「父与母之子/女」；仅一方则「某之子/女」。"""
    sex = "子" if child_gender == "Male" else "女"
    fid = int(father_id) if father_id is not None else None
    mid = int(mother_id) if mother_id is not None else None
    fn = id_to_name.get(fid) if fid is not None else None
    mn = id_to_name.get(mid) if mid is not None else None
    if fn and mn:
        return f"{fn}与{mn}之{sex}"
    if fn:
        return f"{fn}之{sex}"
    if mn:
        return f"{mn}之{sex}"
    return ""


def _bio_spouse_role_line(spouse_name: str | None, self_gender: str) -> str:
    """配偶姓名已知：男为「女方姓名之夫」，女为「男方姓名之妻」。"""
    if not spouse_name:
        return ""
    if self_gender == "Male":
        return f"{spouse_name}之夫"
    return f"{spouse_name}之妻"


def _join_bio_parts(*parts: str) -> str:
    """将多个简介分句用中文分号连接，句末顿号。"""
    segs = []
    for p in parts:
        if not p:
            continue
        t = str(p).strip().rstrip("。")
        if t:
            segs.append(t)
    if not segs:
        return ""
    return "；".join(segs) + "。"


def random_tree_sizes():
    """
    共 11 个族谱；总人数为随机非「整数万」
    """
    target_total = random.randint(270_000, 300_000)
    raw = [
        65_000,
        35_000,
        30_000,
        28_000,
        25_000,
        20_000,
        18_000,
        17_000,
        *[15_000] * 3,
        10000
    ]
    jittered = []
    for r in raw:
        lo, hi = int(-r * 0.005), int(r * 0.005)
        jittered.append(max(400, r + random.randint(lo, hi)))
    s = sum(jittered)
    scale = target_total / s
    sizes = [max(300, int(round(x * scale))) for x in jittered]
    diff = target_total - sum(sizes)
    sizes[0] = max(300, sizes[0] + diff)
    return sizes


def _empty_fk(v):
    return v is None or v == ""


def assign_global_ids_by_generation(all_rows):
    """
    按 generation_level 升序；同一辈分内按 tree_id 分组，每组内男性在前、女性在后
    （组内仍随机打乱同性别的顺序），使每个族谱在全局编号中首次出现者为男性始祖。
    并重写 father_id / mother_id / spouse_id(均为本树局部 id -> 全局 id)。
    """
    # row: member_id, tree_id, name, gender, birth_date, death_date, bio,
    #      generation_level, father_id, mother_id, spouse_id
    by_gen = {}
    for r in all_rows:
        g = r[7]
        by_gen.setdefault(g, []).append(r)

    def _male_female_shuffle(rows):
        males = [r for r in rows if r[3] == "Male"]
        females = [r for r in rows if r[3] == "Female"]
        other = [r for r in rows if r[3] not in ("Male", "Female")]
        random.shuffle(males)
        random.shuffle(females)
        random.shuffle(other)
        return males + females + other

    ordered = []
    for g in sorted(by_gen.keys()):
        part = by_gen[g][:]
        by_tree = {}
        for r in part:
            by_tree.setdefault(r[1], []).append(r)
        tree_order = list(by_tree.keys())
        random.shuffle(tree_order)
        for tid in tree_order:
            ordered.extend(_male_female_shuffle(by_tree[tid]))

    mapping = {}
    for new_id, r in enumerate(ordered, start=1):
        tid = r[1]
        lid = r[0]
        mapping[(tid, lid)] = new_id

    def remap(tid, ref):
        if _empty_fk(ref):
            return ""
        key = (tid, ref)
        if key not in mapping:
            raise KeyError(f"引用未映射: tree_id={tid} local_ref={ref}")
        return mapping[key]

    out = []
    for r in ordered:
        tid = r[1]
        new_row = [
            mapping[(tid, r[0])],
            tid,
            r[2],
            r[3],
            r[4],
            r[5],
            r[6],
            r[7],
            remap(tid, r[8]),
            remap(tid, r[9]),
            remap(tid, r[10]),
        ]
        out.append(new_row)

    out.sort(key=lambda row: row[0])
    return out


def generate_one_tree(tree_id, target_size, main_surname, male_chars, female_chars, surnames):
    """单族谱内使用局部 member_id(从 1 递增)，返回行列表。
    birth_date/death_date 列为 YYYY-MM-DD 合法公历字符串；去世可空（不晚于运行当日）。
    """
    cap = date.today()
    local_id = 1
    members = []
    couples = []
    id_to_name: dict[int, str] = {}

    current_father_id = None
    current_mother_id = None
    base_year = _EARLIEST_BIRTH_YEAR

    parent_max_birth_year = None

    for gen in range(1, 31):
        husband_id = local_id
        local_id += 1
        h_year = base_year + (gen - 1) * 25 + random.randint(-2, 5)
        h_year = max(_EARLIEST_BIRTH_YEAR, min(h_year, cap.year))
        if parent_max_birth_year is not None:
            h_year = max(h_year, parent_max_birth_year + 1)
        h_bd = _random_date_in_year(h_year, cap)
        h_name = generate_random_name(main_surname, "Male", male_chars, female_chars)

        wife_id = local_id
        local_id += 1
        # 妻出生年多在夫年 ±5 年内（可男大或女大），再 legalize 满足婚龄与父母年序
        w_year = h_bd.year + random.randint(
            -_SPOUSE_BIRTH_YEAR_DELTA_MAX, _SPOUSE_BIRTH_YEAR_DELTA_MAX
        )
        w_year = max(_EARLIEST_BIRTH_YEAR, min(w_year, cap.year))
        w_bd = _random_date_in_year(w_year, cap)
        h_bd, w_bd = _legalize_mainline_couple(h_bd, w_bd, cap, parent_max_birth_year)
        h_dd = _clamp_death_after_birth(h_bd, cap)
        w_dd = _clamp_death_after_birth(w_bd, cap)
        w_surname = random.choice([s for s in surnames if s != main_surname])
        w_name = generate_random_name(w_surname, "Female", male_chars, female_chars)

        h_bio = _join_bio_parts(
            f"{main_surname}氏第{gen}代传人",
            _bio_parent_line(current_father_id, current_mother_id, id_to_name, "Male"),
            _bio_spouse_role_line(w_name, "Male"),
        )

        members.append(
            [
                husband_id,
                tree_id,
                h_name,
                "Male",
                _iso(h_bd),
                _iso_death(h_dd),
                h_bio,
                gen,
                current_father_id,
                current_mother_id,
                husband_id + 1,
            ]
        )
        id_to_name[husband_id] = h_name

        w_bio = _join_bio_parts(
            f"嫁入{main_surname}家",
            "",
            _bio_spouse_role_line(h_name, "Female"),
        )

        members.append(
            [
                wife_id,
                tree_id,
                w_name,
                "Female",
                _iso(w_bd),
                _iso_death(w_dd),
                w_bio,
                gen,
                "",
                "",
                husband_id,
            ]
        )
        id_to_name[wife_id] = w_name

        couples.append((husband_id, wife_id, gen, h_bd, w_bd))
        current_father_id = husband_id
        current_mother_id = wife_id
        parent_max_birth_year = max(h_bd.year, w_bd.year)

    current_size = 60

    while current_size < target_size:
        parent = random.choice(couples)
        p_father_id, p_mother_id, p_gen, p_hbd, p_wbd = parent

        child_gen = p_gen + 1
        child_bd = _birth_after_parents(p_hbd, p_wbd, 20, 35, cap)

        is_male = random.choice([True, False])
        child_id = local_id
        local_id += 1

        gender = "Male" if is_male else "Female"
        c_name = generate_random_name(main_surname, gender, male_chars, female_chars)

        will_marry = random.random() > 0.3
        if will_marry and current_size + 2 > target_size:
            will_marry = False
        if will_marry and not _meets_own_marriage_age(gender, child_bd, cap):
            will_marry = False

        spouse_birth_for_pair: date | None = None
        if will_marry:
            spouse_birth_for_pair = _sample_spouse_birth_for_cn_law(child_bd, is_male, cap)
            if spouse_birth_for_pair is None:
                will_marry = False

        s_name: str | None = None
        s_gender_str: str | None = None
        s_bd_val: date | None = None
        if will_marry and spouse_birth_for_pair is not None:
            s_surname = random.choice([s for s in surnames if s != main_surname])
            if is_male:
                s_gender_str = "Female"
                s_name = generate_random_name(
                    s_surname, "Female", male_chars, female_chars
                )
            else:
                s_gender_str = "Male"
                s_name = generate_random_name(s_surname, "Male", male_chars, female_chars)
            s_bd_val = spouse_birth_for_pair

        spouse_id = local_id if will_marry else ""

        child_bio = _join_bio_parts(
            f"{main_surname}氏第{child_gen}代传人",
            _bio_parent_line(p_father_id, p_mother_id, id_to_name, gender),
            _bio_spouse_role_line(s_name, gender) if s_name else "",
        )

        c_dd = _clamp_death_after_birth(child_bd, cap)
        members.append(
            [
                child_id,
                tree_id,
                c_name,
                gender,
                _iso(child_bd),
                _iso_death(c_dd),
                child_bio,
                child_gen,
                p_father_id,
                p_mother_id,
                spouse_id,
            ]
        )
        id_to_name[child_id] = c_name
        current_size += 1

        if will_marry and current_size < target_size and s_name is not None and s_bd_val is not None:
            s_id = local_id
            local_id += 1
            s_bd = s_bd_val
            s_gender = s_gender_str

            if is_male:
                hubby_bd = child_bd
                wifey_bd = s_bd
                couples.append((child_id, s_id, child_gen, hubby_bd, wifey_bd))
                spouse_target = child_id
            else:
                hubby_bd = s_bd
                wifey_bd = child_bd
                couples.append((s_id, child_id, child_gen, hubby_bd, wifey_bd))
                spouse_target = child_id

            spouse_bio = _join_bio_parts(
                f"与{c_name}结为伴侣",
                "",
                _bio_spouse_role_line(c_name, s_gender_str),
            )

            s_dd = _clamp_death_after_birth(s_bd, cap)
            members.append(
                [
                    s_id,
                    tree_id,
                    s_name,
                    s_gender_str,
                    _iso(s_bd),
                    _iso_death(s_dd),
                    spouse_bio,
                    child_gen,
                    "",
                    "",
                    spouse_target,
                ]
            )
            id_to_name[s_id] = s_name
            current_size += 1

    return members


def generate_genealogy_csv(filename="members.csv"):
    tree_sizes = random_tree_sizes()
    num_trees = len(tree_sizes)

    surnames = [
        "李","王","张","刘","陈","杨","赵","黄",
        "周","吴","徐","孙","胡","朱","高","林",
        "何","郭","马","罗","梁","宋","郑","谢",
        "韩","唐","冯","于","董","萧","程","曹",
        "袁","邓","许","傅","沈","曾","彭","吕",
        "汪","田","任","姜","范","方","石","姚",
    ]
    male_chars = [
        "伟","强","磊","军","洋","勇","杰","明","国","平","坤","涛",
        "刚","辉","博","达","健","震","锋","宇","浩","然","斌","昊",
        "轩","鹏","淘","宏","义","辰","哲","翔","霖","峰","鑫","凯",
        "飞","龙","阳","远","泽","航","志","威","华","松","林","柏",
        "城","恩","诚","恒","智","骏","帆","瑞","越","熙","铭","俊",
        "豪","旭","尧","楠","钧","盛","钦","伦","嘉","锦","栋","瀚",
        "渊","宁","冠","策","腾","彬","璟","炎","彪","庆","坚","旺",
        "融","逸","彦","彰","霆","烨","炫","晖","畅","景","硕","展",
        "翊","阔","跃","卓","洲","泰","康","源","沐","川","岩","雷",
        "捷","星","海","波","超","亮","政","毅","信","达","建","新",
        "睿","韬","砚","钊","铎","锴","行","琛","玮","昆","珂","琦",
        "铠","成","勋","丞","佑","伯","佐","帅","朔","朗","昱","晟",
    ]

    female_chars = [
        "芳","娜","敏","静","丽","艳","娟","秀","梅","萍","玲","雪",
        "婷","慧","佳","仪","欣","瑶","玥","琴","洁","雅","菲","雁",
        "珊","莎","黛","青","倩","珍","蕊","薇","璐","琪","婉","萱",
        "岚","曼","彤","瑾","颖","露","馨","兰","蓉","芸","凝","晓",
        "欢","霄","枫","寒","伊","亚","宜","可","姬","舒","影","荔",
        "枝","思","飘","美","滢","馥","筠","柔","竹","霭","香","月",
        "玉","珠","翠","环","红","双","文","凤","琳","素","云","莲",
        "真","荣","爱","妹","霞","莺","媛","紫","丹","妮","梦","漪",
        "漫","霓","秋","诗","璇","语","蕾","冰","彩","春","菊","勤",
        "贞","莉","菀","菁","婉","姣","妙","姿","娇","侗","嘉","心",
        "茜","茵","茹","芊","茉","芮","芩","莘","莞","芷","茯","若",
        "茱","荫","荷","莓","棠","樱","柚","柠","姗","妤","姝","娴",
    ]

    all_rows = []
    for k in range(num_trees):
        tid = k + 1
        target = tree_sizes[k]
        main_surname = surnames[k % len(surnames)]
        rows = generate_one_tree(
            tid,
            target,
            main_surname,
            male_chars,
            female_chars,
            surnames,
        )
        all_rows.extend(rows)
        print(f"族谱 tree_id={tid} ({main_surname}氏) 结构已生成，目标约 {target} 人，本批行数 {len(rows)}")

    final_rows = assign_global_ids_by_generation(all_rows)

    with open(filename, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "member_id",
                "tree_id",
                "name",
                "gender",
                "birth_date",
                "death_date",
                "bio",
                "generation_level",
                "father_id",
                "mother_id",
                "spouse_id",
            ]
        )
        writer.writerows(final_rows)

    total = len(final_rows)
    print(f"\n所有数据生成完毕! 共计 {total} 条（目标规模约 {sum(tree_sizes)}），已保存至 {filename}")
    print(f"各家族目标人数(tree_id 1..{num_trees}):{tree_sizes}")
    print("全局 member_id:按辈分由小到大分配；同谱同辈内先男后女，同性内随机")


if __name__ == "__main__":
    generate_genealogy_csv()