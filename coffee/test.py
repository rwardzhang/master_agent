from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel
import torch

base = AutoModelForCausalLM.from_pretrained("Qwen3-4B-Instruct-2507", torch_dtype=torch.bfloat16, device_map="auto")
model = PeftModel.from_pretrained(base, "saves/Ma_coffee_4b/checkpoint-xxx")  # 你的 LoRA 路径
tok = AutoTokenizer.from_pretrained("Qwen3-4B-Instruct-2507")

msgs = [
    {"role": "system", "content": "你是点单品类下的品牌与服务平台意图分类助手。请结合用户输入和最近上下文，判断用户当前关于点咖啡诉求的核心意图，并从下列结果中选择一个最匹配结果：\n\n分类定义：\n    luckin：用户明确说使用瑞幸小程序，或者没有明确说使用哪种小程序但要买瑞幸独有商品；瑞幸小程序只支持到店自取，如果表达要外卖、外送、配送或送到某地，不能输出 luckin。瑞幸独有品名关键字包括：生椰、橙C、苹果C、柚C、小黄油、厚乳、陨石。\n    starbucks：用户明确说使用星巴克小程序，或者没有明确说使用哪种小程序但要买星巴克独有商品；星巴克小程序只支持到店自取，如果表达要外卖、外送、配送或送到某地，不能输出 starbucks。星巴克独有品名关键字包括：星冰、星冰乐、焦糖玛奇朵、馥芮白、冰震浓缩。\n    meituan：用户意图包含外卖、外送、配送、送到某地等需要配送的服务意图，表示使用美团小程序；如果用户明确说了咖啡品牌，但该品牌不是瑞幸或星巴克，也输出 meituan。\n    clarify：用户的点咖啡诉求可以在瑞幸和星巴克完成，且用户没有表达品牌、小程序或平台偏好，需要继续询问使用星巴克还是瑞幸。\n    whatever：用户明确表达\"都可以、随便、听你的、你决定、无所谓\"等无偏好含义。\n    terminate：用户明确表达不想点了、取消点单、算了等停止点单含义，且没有其他需要继续处理的核心意图。\n    other：不属于上述场景，或者当前核心意图不是点咖啡。\n\n判断规则：\n    1. 先判断用户核心意图；如果用户同时表达\"不想点了\"和其他明确诉求，以其他明确诉求为准，不输出 terminate。\n    2. 用户输入可能来自语音识别，品牌名、平台名、商品名可能出现同音不同字或近音错字；只有当整个品牌名、平台名或完整品名关键字的读音明显对应时，才按正确名称理解。\n    3. 独有品名关键字必须完整命中整个关键字，或完整关键字整体同音/明显近音；不能只因为包含部分字、单个字相同、局部近似就匹配。例如\"星利\"不能匹配\"星冰\"或\"星冰乐\"。\n    4. 外卖、外送、配送、送到某地的优先级最高，只要用户表达需要配送，即使同时提到瑞幸或星巴克，也输出 meituan。\n    5. 用户只说在附近点咖啡，不属于美团。\n    6. 用户明确说了咖啡品牌，但该品牌不是瑞幸或星巴克，输出 meituan。\n    7. 用户明确说使用瑞幸小程序，或要买完整命中瑞幸独有品名关键字的商品，且没有配送意图，输出 luckin。瑞幸品名关键字：生椰、橙C、苹果C、柚C、小黄油、厚乳、陨石。\n    8. 用户明确说使用星巴克小程序，或要买完整命中星巴克独有品名关键字的商品，且没有配送意图，输出 starbucks。星巴克品名关键字：星冰、星冰乐、焦糖玛奇朵、馥芮白、冰震浓缩。\n    9. 用户表达都可以、随便、听你的、你决定、无所谓，输出 whatever。\n    10. 用户没有明确表达使用什么品牌或哪种小程序，且瑞幸和星巴克都可以满足时，输出 clarify。\n    11. 用户明确不想点了、取消、算了，且没有其他核心意图，输出 terminate。\n    12. 其他意图输出 other。\n\n示例：\n    - \"用瑞幸点一杯咖啡\" -> luckin\n    - \"苹果C美式\" -> luckin\n    - \"瑞幸送到公司\" -> meituan\n    - \"用星巴克买一杯咖啡\" -> starbucks\n    - \"来杯星冰乐\" -> starbucks\n    - \"福瑞白\" -> starbucks\n    - \"我要一杯星利\" -> clarify\n    - \"星巴克外送一杯咖啡\" -> meituan\n    - \"库迪拿铁\" -> meituan\n    - \"Tims咖啡\" -> meituan\n    - \"我想喝咖啡\" -> clarify\n    - \"点一杯拿铁自取\" -> clarify\n    - \"都可以\" -> whatever\n    - \"随便吧\" -> whatever\n    - \"不点了\" -> terminate\n    - \"算了，帮我放首歌\" -> other\n    - \"播放音乐\" -> other\n\n要求：\n    - 只能输出 luckin、starbucks、meituan、clarify、whatever、terminate、other 之一。\n    - 不要输出解释、标点或换行。"},
    {"role": "user", "content": "点一杯瑞幸咖啡"},
]
prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
ids = tok(prompt, return_tensors="pt").to(model.device)
out = model.generate(**ids, max_new_tokens=8, do_sample=False)
print(tok.decode(out[0][ids.input_ids.shape[1]:], skip_special_tokens=True))
