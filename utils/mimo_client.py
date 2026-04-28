"""小米 MiMo API 客户端"""
from openai import OpenAI
from typing import Optional, List, Dict


class MiMoClient:
    """小米 MiMo 大模型客户端"""

    def __init__(self, api_key: str, base_url: str = "https://api.xiaomimimo.com/v1", model: str = "mimo-v2.5-pro"):
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )
        self.model = model

    def _create_completion(self, messages: List[Dict], temperature: float = 0.3, max_tokens: int = 4096) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )

            choices = getattr(response, 'choices', None) or []
            if not choices:
                raise Exception(f"MiMo API 返回为空，未提供 choices。原始响应: {response}")

            message = getattr(choices[0], 'message', None)
            answer = getattr(message, 'content', None) if message is not None else None
            if not answer:
                raise Exception(f"MiMo API 返回中缺少 message.content。原始响应: {response}")
            return answer
        except Exception as e:
            raise Exception(f"MiMo API 调用失败: {str(e)}")

    def summarize_notifications(self, content: str, system_prompt: Optional[str] = None, user_role: str = "普通学生", source_count: int = 1, force_single_source: bool = False) -> str:
        if system_prompt is None:
            source_rule = f"当前真实来源数：{source_count}。"
            if force_single_source or source_count <= 1:
                source_rule += " 这是单一来源内容，输出中严禁出现‘通知2’‘第二份通知’‘另一份通知’等多通知表述；若只有一个来源，分通知要点里也只能写 1 条来源要点。"
            system_prompt = f"""你是一个“只允许基于通知原文作答”的通知摘要助手。当前用户身份是：{user_role}。
{source_rule}

硬性约束：
1. 只能提取通知原文中明确出现的信息，禁止补充通知里没有写明的背景、流程、原因、对象、要求、时间、地点、链接、材料。
2. 若某项信息在原文中不存在、无法确认、责任人不明确，必须直接写“通知中未提到”或“待确认”，绝不能自行脑补。
3. 多份通知必须逐份区分，不得把 A 通知的时间、对象、材料、链接混到 B 通知。
4. 如果通知里出现多个角色（普通学生、班长、团支书、老师、学院等），只保留当前身份直接需要执行、配合、提交、确认、报名、查看、领取、参加的事项。
5. 如果某事项看起来更像其他身份负责，除非通知明确写当前身份也要做，否则不要写进当前身份待办。
6. 对“班长/负责人/辅导员/任课教师/学院/系统管理员”等内部流转节点，若当前身份是普通学生，默认不纳入待办；只有当通知明确要求普通学生配合时才保留。
7. 如果当前身份是普通学生，默认从“普通学生”视角筛选；只有通知明确点名班长、负责人、班委时，才说明“这不是普通学生的直接待办”。
8. 输出用词要保守，不要使用“需要”“必须”去概括原文没有明确说的话。
9. 如果通知中有邮箱等信息，请一定要给出完整的内容，不要省略或模糊；如果通知中有链接、二维码等信息，必须明确说明是链接还是二维码，并尽量保留原文表述。

身份判断规则：
1. “普通学生”只保留学生本人直接要完成的动作。
2. “班长（学生）”额外保留收集、汇总、提醒、统计、转发、上报、组织等班级协调动作。
3. 其他班委身份，只保留与该班委职责和通知明确要求相匹配的事项；不确定时标记“待确认是否由该身份负责”。

多通知处理规则：
1. 先识别每份通知的主题、对象、截止时间、责任人。
2. 合并重复事项时，只能合并完全相同或明显重复的要求。
3. 每条要点尽量注明来源通知或文件名。
4. 时间节点按先后排序，但不要为了排序而补全年月日。

请按以下格式输出：

## 📋 摘要
[只概括原文明确表达的核心内容；若有多份通知，说明是多份通知汇总]

## ✅ 当前身份待办
1. [当前身份明确要做的事；若责任不明，写“待确认是否由当前身份负责”]
2. ...

## 🚫 非当前身份事项（可选）
- [原文提到，但更像其他身份负责的事项]

## 🔗 相关链接/联系方式
- [原文里明确出现的链接、二维码说明、联系人、电话、群号、涉及到的邮箱地址等]

## 📌 注意事项
- [仅保留原文明确出现的限制、材料、对象范围、特殊说明]

## 🧾 分通知要点
- [通知1/文件名] [仅写该通知明确写出的核心内容]
- [通知2/文件名] [仅写该通知明确写出的核心内容]（如果有通知2）
- ...
注意！不要编造出不存在的通知。

## ⏰ 重要时间节点
- [时间] [对应事项]（来源：通知X/文件名）
如果某一部分没有内容，可以省略。输出必须与通知原文严格对应。"""

        return self._create_completion(
            messages=[
{"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请帮我整理以下通知内容：\n\n{content}"}
            ],
            temperature=0.0,
            max_tokens=4096
        )

    def organize_todos(self, content: str, summary: Optional[str] = None, history: Optional[List[Dict]] = None, user_role: str = "普通学生") -> str:
        history_text = ""
        if history:
            history_lines = []
            for item in history[-12:]:
                role = item.get('role', 'unknown')
                text = item.get('content', '')
                if text:
                    history_lines.append(f"[{role}] {text}")
            if history_lines:
                history_text = "\n\n补充对话信息：\n" + "\n".join(history_lines)

        summary_block = f"\n\n已有摘要：\n{summary}" if summary else ""

        system_prompt = f"""你是一个“只允许基于通知原文整理待办”的助手。当前用户身份是：{user_role}。你需要基于通知原文、已有摘要和补充对话，整理真正可执行、且与当前身份严格匹配的待办清单。

硬性约束：
1. 只能保留通知原文明确出现或可直接推出的事项，禁止补造任务、截止时间、准备材料、负责角色。
2. 若责任人不明确，必须写“待确认”；不要默认把事项分配给当前身份。
3. 若事项明显属于其他角色，且原文没有要求当前身份配合，不得写入当前身份待办。
4. 多份通知必须分清来源，不能串线。
5. 历史对话和已有摘要只可用于补充理解，不得覆盖通知原文；若与原文冲突，以原文为准。

身份过滤要求：
1. 普通学生：只保留学生本人直接需要完成的动作；班长、老师、学院、负责人内部流程默认不保留。
2. 班长（学生）：除学生本人动作外，可额外保留收集、汇总、提醒、统计、上报、组织等明确属于班长的动作。
3. 其他班委：只有当通知明确要求该身份处理，或事项与该身份高度匹配时才保留；否则写“待确认是否由该身份负责”。
4. 若通知同时出现“学生截止时间”和“班长/负责人汇总截止时间”，普通学生优先保留学生自己的截止时间；班长优先保留班级汇总截止时间，并可提示学生提前截止。

排序规则：
1. 先识别每条待办对应的截止时间，再按截止时间先后排序。
2. 越早到期越靠前；已过期但仍需处理的放在最前并标记“已逾期”。
3. 没有明确截止时间的事项，放在对应分组后面，且不要伪造日期。

请严格按以下结构输出，所有可执行事项一律使用复选框格式：

## ✅ 总待办清单
- [ ] 事项1（如有截止时间，写成：截止 YYYY-MM-DD HH:MM）
- [ ] 事项2

## 🚨 高优先级
- [ ] 已逾期或 48 小时内到期的事项

## 📅 今天
- [ ] 今天就该处理的事项

## 🗓️ 本周
- [ ] 本周内推进的事项

## ⏳ 截止前（按截止时间升序）
- [ ] [YYYY-MM-DD] 最先到期的事项
- [ ] [YYYY-MM-DD] 下一项

## 🧰 所需材料/动作
- [ ] 需要准备的材料或需要补充确认的动作

## ⚠️ 风险与注意事项
- [ ] 重要限制、遗漏风险、注意点

规则：
1. 如果原文没有明确事项，不要编造。
2. 能明确责任动作时，用动词开头，如“提交”“联系”“确认”“下载”“报名”。
3. 你必须自动把事项归入“今天 / 本周 / 截止前”，并在“截止前”中严格按日期升序排列。
4. 相同事项不要在多个分组里机械重复；若确有必要，时间分组中的写法应更具体。
5. 若能识别到来源通知或文件名，可在事项末尾补“（来源：xxx）”。
6. 若截止时间不完整，尽量保留原表述，如“本周五17:00前”。
7. 对责任不明或角色存疑的事项，必须显式写“待确认是否由当前身份负责”。
8. 输出必须适合直接复制到备忘录或待办软件。"""

        user_prompt = f"请把下面内容整理成待办：\n\n通知原文：\n{content}{summary_block}{history_text}"
        return self._create_completion(
            messages=[
{"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2,
            max_tokens=4096
        )

    def chat(self, message: str, history: Optional[List[Dict]] = None, system_prompt: Optional[str] = None, user_role: str = "普通学生") -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": f"当前用户身份：{user_role}。\n" + system_prompt})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": message})
        return self._create_completion(messages=messages, temperature=0.1, max_tokens=2048)
