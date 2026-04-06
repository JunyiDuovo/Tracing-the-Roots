"""
生成 members.csv:多族谱、非整齐总人数。
全局 member_id:按辈分 generation_level 从小到大分配；同一族谱、同辈内先男后女再随机，
保证每谱「第一人」为男性始祖，便于传承；祖先辈分仍 < 后辈。
"""
import csv
import random

# 固定种子可复现；改为 None 则每次不同
_SEED = None
if _SEED is not None:
    random.seed(_SEED)


def generate_random_name(surname, gender, male_chars, female_chars):
    """根据姓氏和性别随机生成 2 字或 3 字姓名。"""
    chars_pool = male_chars if gender == "Male" else female_chars
    name_length = random.choice([2, 3])
    if name_length == 2:
        return surname + random.choice(chars_pool)
    return surname + random.choice(chars_pool) + random.choice(chars_pool)


def random_tree_sizes():
    """
    共 11 个族谱；总人数为随机非「整数万」
    """
    target_total = random.randint(250_000, 270_000)
    raw = [
        65_000,
        35_000,
        30_000,
        28_000,
        25_000,
        20_000,
        18_000,
        17_000,
        *[15_000] * 3
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
    # row: member_id, tree_id, name, gender, birth_year, death_year, bio,
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
    """单族谱内使用局部 member_id(从 1 递增)，返回行列表。"""
    local_id = 1
    members = []
    couples = []

    current_father_id = None
    current_mother_id = None
    base_year = 1000

    for gen in range(1, 31):
        husband_id = local_id
        local_id += 1
        h_birth = base_year + (gen - 1) * 25 + random.randint(-2, 5)
        h_name = generate_random_name(main_surname, "Male", male_chars, female_chars)

        members.append(
            [
                husband_id,
                tree_id,
                h_name,
                "Male",
                h_birth,
                h_birth + random.randint(45, 80),
                f"{main_surname}氏第{gen}代传人。",
                gen,
                current_father_id,
                current_mother_id,
                husband_id + 1,
            ]
        )

        wife_id = local_id
        local_id += 1
        w_birth = h_birth + random.randint(-5, 5)
        w_surname = random.choice([s for s in surnames if s != main_surname])
        w_name = generate_random_name(w_surname, "Female", male_chars, female_chars)

        members.append(
            [
                wife_id,
                tree_id,
                w_name,
                "Female",
                w_birth,
                w_birth + random.randint(45, 80),
                f"嫁入{main_surname}家。",
                gen,
                "",
                "",
                husband_id,
            ]
        )

        couples.append((husband_id, wife_id, gen, h_birth))
        current_father_id = husband_id
        current_mother_id = wife_id

    current_size = 60

    while current_size < target_size:
        parent = random.choice(couples)
        p_father_id, p_mother_id, p_gen, p_birth = parent

        child_gen = p_gen + 1
        child_birth = p_birth + random.randint(20, 35)

        is_male = random.choice([True, False])
        child_id = local_id
        local_id += 1

        gender = "Male" if is_male else "Female"
        c_name = generate_random_name(main_surname, gender, male_chars, female_chars)

        will_marry = random.random() > 0.3
        # 子代 + 配偶共占 2 个名额；若只剩 1 个名额仍写 spouse_id,会指向未生成的配偶行
        if will_marry and current_size + 2 > target_size:
            will_marry = False
        spouse_id = local_id if will_marry else ""

        members.append(
            [
                child_id,
                tree_id,
                c_name,
                gender,
                child_birth,
                child_birth + random.randint(40, 90),
                f"{main_surname}氏第{child_gen}代传人。",
                child_gen,
                p_father_id,
                p_mother_id,
                spouse_id,
            ]
        )
        current_size += 1

        if will_marry and current_size < target_size:
            s_id = local_id
            local_id += 1
            s_birth = child_birth + random.randint(-5, 5)

            s_surname = random.choice([s for s in surnames if s != main_surname])

            if is_male:
                s_gender = "Female"
                s_name = generate_random_name(s_surname, s_gender, male_chars, female_chars)
                couples.append((child_id, s_id, child_gen, child_birth))
                spouse_target = child_id
            else:
                s_gender = "Male"
                s_name = generate_random_name(s_surname, s_gender, male_chars, female_chars)
                couples.append((s_id, child_id, child_gen, s_birth))
                spouse_target = child_id

            members.append(
                [
                    s_id,
                    tree_id,
                    s_name,
                    s_gender,
                    s_birth,
                    s_birth + random.randint(40, 90),
                    f"与{c_name}结为伴侣。",
                    child_gen,
                    "",
                    "",
                    spouse_target,
                ]
            )
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
                "birth_year",
                "death_year",
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