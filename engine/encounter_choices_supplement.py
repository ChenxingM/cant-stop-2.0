# -*- coding: utf-8 -*-
"""
遭遇选择补充代码 - 用于批量添加到content_handler.py

将以下方法添加到ContentHandler类中，替换现有的无choice参数版本
"""

# 遭遇22-60的choice处理代码

ENCOUNTER_IMPLEMENTATIONS = """
    def _encounter_talent_market(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        if choice is None:
            return ContentResult(True, f"📖 {encounter_name}\\n你被带到了疯人院,可以选择一位室友",
                               requires_input=True, choices=["选择高个子的那个", "选择矮个子的那个"])
        if choice == "选择高个子的那个":
            return ContentResult(True, "你的室友是个话痨,你忍不了了,暴揍了他一顿。谜语人滚出OAS!战斗力+1(并不存在这种东西)")
        else:
            self.player_dao.add_score(qq_id, 5)
            return ContentResult(True, "你的室友后来成为了当地的市长,给你留下了一笔钱。你的积分+5")

    def _encounter_bika(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        player = self.player_dao.get_player(qq_id)
        if choice is None:
            if player.faction == "收养人":
                choices = ["让我康康!", "不该看的不看"]
            elif player.faction == "Aeonreth":
                choices = ["谁管ae看什么呢~"]
            else:
                choices = ["继续前进"]
            return ContentResult(True, f"📖 {encounter_name}\\n模糊的粉色不明物体怪叫着跑了过来",
                               requires_input=True, choices=choices)
        if choice == "让我康康!":
            self.player_dao.add_score(qq_id, -5)
            return ContentResult(True, '"小孩子不许看这个。" 魔女大姐姐略有些责备地把那个小东西抓走了,而你也受到了惩罚。你的积分-5')
        elif choice == "不该看的不看":
            self.player_dao.add_score(qq_id, 5)
            return ContentResult(True, "巡逻的魔女大姐姐赞许地点了点头,并把那个小东西抓走了。你的积分+5")
        elif choice == "谁管ae看什么呢~":
            return ContentResult(True, "当你发觉自己看到了什么的时候一切都已经来不及了…但话说回来,谁管ae看什么呢~无事发生")
        else:
            return ContentResult(True, "无事发生")

    def _encounter_protect_brain(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        if choice is None:
            return ContentResult(True, f"📖 {encounter_name}\\n丧尸危机!你被困在老宅中,手边只有一个小袋子和一瓶洗手液",
                               requires_input=True, choices=["选择小袋子", "选择洗手液"])
        if choice == "选择小袋子":
            self.player_dao.add_score(qq_id, 5)
            self.inventory_dao.add_item(qq_id, 9106, "小奖杯", "hidden_item")
            return ContentResult(True, "种子长出了向日葵和豌豆...你靠着这些植物抵御了僵尸的进攻\\n获得隐藏物品:小奖杯。你的积分+5")
        else:
            self.achievement_dao.add_achievement(qq_id, 104, "洗手液战神", "normal")
            return ContentResult(True, "洗手液让你所有的伤口愈合如初!你凭借着洗手液杀出重围成功生存\\n获得成就:洗手液战神")

    def _encounter_real_estate(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        if choice is None:
            return ContentResult(True, f"📖 {encounter_name}\\n\\"哟?又带嫂子来看房啦?\\"",
                               requires_input=True, choices=["哪儿来的嫂子?", "不理它"])
        if choice == "哪儿来的嫂子?":
            dice_roll = random.randint(1, 20)
            if dice_roll >= 18:
                return ContentResult(True, f"d20={dice_roll}≥18 凭借回头溜鬼的通用技巧,你轻松摆脱了木偶的追杀\\n你当前临时标记向前移动一格",
                                   {'move_temp_forward': 1})
            elif dice_roll >= 5:
                return ContentResult(True, f"d20={dice_roll} 经过不懈的努力,你终于摆脱了木偶")
            else:
                return ContentResult(True, f"d20={dice_roll}<5 你没能成功逃离\\n你当前临时标记向后移动一格", {'temp_retreat': 1})
        else:
            return ContentResult(True, "似乎不是对你说的,你快步离开了。无事发生")

    def _encounter_mouth(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        if choice is None:
            return ContentResult(True, f"📖 {encounter_name}\\n\\"你好。\\"不知道从哪里传出声音",
                               requires_input=True, choices=["谁?", "寻找声音来源"])
        if choice == "谁?":
            return ContentResult(True, '"嘻嘻嘻嘻…" 声音再次响起,你突然被不知道什么东西砸晕了\\n你暂停一回合(消耗一回合积分)',
                               {'skip_rounds': 1})
        else:  # 寻找声音来源 -> 需要二次选择
            return ContentResult(True, "你看到一个嘴长在面前脚下的格子上",
                               requires_input=True, choices=['"你好"', "还是不回应了"])

    def _encounter_strange_dish(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        if choice is None:
            return ContentResult(True, f"📖 {encounter_name}\\n锅里装着奇怪的食材,咕嘟咕嘟冒着泡…",
                               requires_input=True, choices=["好怪,尝一口", "好怪,还是不要吧", "好怪!一口闷了!"])
        if choice == "好怪,尝一口":
            self.player_dao.add_score(qq_id, 5)
            return ContentResult(True, "虽然入口就像炖轮胎佐鲱鱼罐头汤,但异味很快消失了,你感觉力气在恢复。你的积分+5")
        elif choice == "好怪,还是不要吧":
            return ContentResult(True, "你捏着鼻子走开了。无事发生")
        else:
            self.player_dao.add_score(qq_id, 10)
            return ContentResult(True, "本着猎奇的心理你还是干了,你感觉充满了力气!!你的积分+10")

    def _encounter_fishing(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        if choice is None:
            return ContentResult(True, f"📖 {encounter_name}\\n钓鱼大赛!你只差几条就能拿到最终的奖励!",
                               requires_input=True, choices=["坚持钓到最后一刻", "差不多得了,先交了走人"])
        if choice == "坚持钓到最后一刻":
            self.player_dao.add_score(qq_id, -10)
            return ContentResult(True, "你昏迷了。再醒来时一封信躺在枕头边:\\"医疗小队服务费\\"\\n你的积分-10")
        else:
            self.player_dao.add_score(qq_id, 5)
            return ContentResult(True, "见好就收,虽然没能拿到大奖,但是现在的收获也足够换一些奖励了。你的积分+5")

    def _encounter_cold_joke(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        if choice is None:
            return ContentResult(True, f"📖 {encounter_name}\\n停,就是你,现在3分钟内讲一个冷笑话",
                               requires_input=True, choices=["完成后输入[冷笑话已完成]", "无法完成"])
        if choice == "完成后输入[冷笑话已完成]":
            return ContentResult(True, "完成任务!")
        else:
            self.player_dao.add_score(qq_id, -5)
            return ContentResult(True, "未能完成,自动积分-5")
"""

if __name__ == "__main__":
    print("遭遇选择补充代码已生成")
    print("请将上述代码手动集成到content_handler.py中")
