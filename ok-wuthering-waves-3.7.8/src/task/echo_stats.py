"""Strict OCR validation before any echo cultivation decision."""
import re


class EchoRecognitionError(ValueError):
    """Unreadable evidence must never be treated as a rejected echo."""


STATS = {'暴击', '暴击伤害', '攻击', '生命', '防御', '共鸣效率', '普攻伤害加成',
         '重击伤害加成', '共鸣解放伤害加成', '共鸣技能伤害加成'}
TRANSLATION = str.maketrans('擊傷禦鳴', '击伤御鸣')


def parse_number(text):
    value = str(text).strip().replace('％', '%')
    if not re.fullmatch(r'\d+(?:\.\d+)?\s*%?', value):
        raise EchoRecognitionError(f'无法识别词条数值：{text!r}')
    number = float(value.rstrip('%').strip())
    if number <= 0:
        raise EchoRecognitionError(f'词条数值必须大于0：{text!r}')
    return number


def pair_stats(properties, values):
    if not 1 <= len(properties) <= 5 or len(properties) != len(values):
        raise EchoRecognitionError('词条与数值数量不完整，已停止培养')
    properties = sorted(properties, key=lambda b: b.y)
    values = sorted(values, key=lambda b: b.y)
    paired = []
    seen = set()
    for prop, value in zip(properties, values):
        # OCR labels and values can have slightly different boxes, but must be
        # on the same row. The cap also prevents abnormally tall OCR boxes
        # from accepting a value on a neighbouring row.
        heights = [getattr(b, 'height', 0) or 0 for b in (prop, value)]
        tolerance = max(8, min(24, max(heights) * .8))
        if abs(prop.y - value.y) > tolerance:
            raise EchoRecognitionError('词条与数值不在同一行')
        name = re.sub(r'^[+\s.·✦✧]+', '', prop.name.strip()).translate(TRANSLATION)
        if name not in STATS:
            raise EchoRecognitionError(f'无法识别词条名称：{prop.name}')
        text = value.name.strip().replace('％', '%')
        number = parse_number(text)
        percent = '%' in text
        if name not in ('攻击', '生命', '防御') and not percent:
            raise EchoRecognitionError(f'{name}缺少百分号，不能据此判断')
        if percent and number > 100:
            raise EchoRecognitionError('百分比词条读数超出范围')
        if not percent and (number != int(number) or number > 1000):
            raise EchoRecognitionError('固定数值词条读数异常')
        canonical = name + ('百分比' if percent and name in ('攻击', '生命', '防御') else '')
        if canonical in seen:
            raise EchoRecognitionError(f'重复识别词条：{canonical}')
        seen.add(canonical)
        paired.append((canonical, text))
    return paired
