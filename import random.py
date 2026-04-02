import random
import csv

def generate_random_name(surname, gender, male_chars, female_chars):
    """
    根据给定的姓氏和性别，随机生成 2 字或 3 字的姓名
    """
    chars_pool = male_chars if gender == "Male" else female_chars
    # 随机决定姓名总长度为 2 还是 3
    name_length = random.choice([2, 3])
    
    if name_length == 2:
        # 姓 + 1个单字
        return surname + random.choice(chars_pool)
    else:
        # 姓 + 2个单字
        return surname + random.choice(chars_pool) + random.choice(chars_pool)

def generate_genealogy_csv(filename="members.csv"):
    # 核心参数配置
    tree_sizes = [55000] + [5000] * 9  # 1个55000人的大族谱，9个5000人的小族谱，共10个，总计10万人
    
    # 词库配置
    surnames = ["李", "王", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴", "徐", "孙", "胡", "朱", "高"]
    male_chars = [
        "伟", "强", "磊", "军", "洋", "勇", "杰", "明", "国", "平", 
        "刚", "辉", "博", "达", "健", "震", "锋", "宇", "浩", "然",
        "斌", "轩", "鹏", "涛", "宏", "义", "辰", "哲", "翔", "霖", 
        "峰", "鑫", "凯", "飞", "龙", "阳", "远", "泽", "航", "志",
        "威", "华", "松", "林", "柏", "城", "恩", "诚", "恒", "智", 
        "骏", "帆", "瑞", "越", "熙", "铭", "俊", "豪", "旭", "尧",
        "楠", "钧", "盛", "钦", "伦", "嘉", "锦", "栋", "瀚", "渊", 
        "宁", "冠", "策", "腾", "彬", "璟", "炎", "彪", "庆", "坚",
        "旺", "融", "逸", "彦", "彰", "霆", "烨", "炫", "晖", "畅", 
        "景", "硕", "展", "翊", "阔", "跃", "卓", "洲", "泰", "康",
        "源", "沐", "川", "岩", "雷", "捷", "星", "海", "波", "超", 
        "亮", "政", "毅", "信", "达", "建", "新"
    ]
    
    female_chars = [
        "芳", "娜", "敏", "静", "丽", "艳", "娟", "秀", "梅", "萍", 
        "玲", "雪", "婷", "慧", "佳", "仪", "欣", "瑶", "玥", "琴",
        "洁", "雅", "菲", "雁", "珊", "莎", "黛", "青", "倩", "珍", 
        "蕊", "薇", "璐", "琪", "婉", "萱", "岚", "曼", "彤", "瑾",
        "颖", "露", "馨", "兰", "蓉", "芸", "凝", "晓", "欢", "霄", 
        "枫", "寒", "伊", "亚", "宜", "可", "姬", "舒", "影", "荔",
        "枝", "思", "飘", "育", "滢", "馥", "筠", "柔", "竹", "霭", 
        "香", "月", "玉", "珠", "翠", "环", "红", "双", "文", "凤",
        "琳", "素", "云", "莲", "真", "荣", "爱", "妹", "霞", "莺", 
        "媛", "紫", "丹", "妮", "梦", "漪", "漫", "霓", "秋", "诗",
        "璇", "语", "蕾", "冰", "彩", "春", "菊", "勤", "贞", "莉", 
        "菀", "菁", "婉", "姣", "妙", "姿", "娇"
    ]
    
    global_member_id = 1
    
    # 打开CSV文件准备写入
    with open(filename, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        # 写入表头
        writer.writerow(["member_id", "tree_id", "name", "gender", "birth_year", "death_year", "bio", "generation_level", "father_id", "mother_id", "spouse_id"])
        
        for tree_index, target_size in enumerate(tree_sizes):
            tree_id = tree_index + 1
            main_surname = surnames[tree_index % len(surnames)]
            
            members = []
            # 记录可以作为父母的“夫妻对”：(father_id, mother_id, generation, birth_year)
            couples = [] 
            
            # --- 步骤 1: 生成 30 代单线主干 ---
            current_father_id = None
            current_mother_id = None
            base_year = 1200 
            
            for gen in range(1, 31):
                # 生成丈夫（血脉成员）
                husband_id = global_member_id
                global_member_id += 1
                h_birth = base_year + (gen - 1) * 25 + random.randint(-2, 5)
                h_name = generate_random_name(main_surname, "Male", male_chars, female_chars)
                
                members.append([
                    husband_id, tree_id, h_name, "Male", h_birth, h_birth + random.randint(45, 80),
                    f"{main_surname}氏第{gen}代传人。", gen, current_father_id, current_mother_id, husband_id + 1
                ])
                
                # 生成妻子（外来配偶）
                wife_id = global_member_id
                global_member_id += 1
                w_birth = h_birth + random.randint(-5, 5)
                w_surname = random.choice([s for s in surnames if s != main_surname])
                w_name = generate_random_name(w_surname, "Female", male_chars, female_chars)
                
                members.append([
                    wife_id, tree_id, w_name, "Female", w_birth, w_birth + random.randint(45, 80),
                    f"嫁入{main_surname}家。", gen, "", "", husband_id
                ])
                
                couples.append((husband_id, wife_id, gen, h_birth))
                
                # 下一代的父母
                current_father_id = husband_id
                current_mother_id = wife_id
            
            # --- 步骤 2: 随机分支扩展 ---
            current_size = 60 
            
            while current_size < target_size:
                parent = random.choice(couples)
                p_father_id, p_mother_id, p_gen, p_birth = parent
                
                child_gen = p_gen + 1
                child_birth = p_birth + random.randint(20, 35) 
                
                is_male = random.choice([True, False])
                child_id = global_member_id
                global_member_id += 1
                
                gender = "Male" if is_male else "Female"
                c_name = generate_random_name(main_surname, gender, male_chars, female_chars)
                
                will_marry = random.random() > 0.3 # 70%的概率会结婚
                spouse_id = global_member_id if will_marry else ""
                
                members.append([
                    child_id, tree_id, c_name, gender, child_birth, child_birth + random.randint(40, 90),
                    f"{main_surname}氏分支成员。", child_gen, p_father_id, p_mother_id, spouse_id
                ])
                current_size += 1
                
                if will_marry and current_size < target_size:
                    s_id = global_member_id
                    global_member_id += 1
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
                    
                    members.append([
                        s_id, tree_id, s_name, s_gender, s_birth, s_birth + random.randint(40, 90),
                        f"与{c_name}结为伴侣。", child_gen, "", "", spouse_target
                    ])
                    current_size += 1

            # 批量写入
            writer.writerows(members)
            print(f"族谱 {tree_id} ({main_surname}氏) 生成完毕，成员数：{current_size}")

    print(f"\n所有数据生成完毕！共计 {global_member_id - 1} 条，已保存至 {filename}")

if __name__ == "__main__":
    generate_genealogy_csv()