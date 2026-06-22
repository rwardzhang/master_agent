#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive fix script for nlu_car_control dataset.
Fixes:
 1. 档位P但车速非驻车 -> 改车速为驻车
 2. 低温(≤16°)座椅通风 -> 关闭通风(controller + policy/logic)
 3. 高温(≥30°)座椅加热 -> 关闭加热(controller + policy/logic)
 4. 低温(≤18°)空调制冷 -> 改为制热(controller + policy/logic)
 5. 高温(≥30°)空调制热 -> 改为制冷(controller + policy/logic)
 6. 大雨/大雪/积雪 policy建议开窗 -> 删除/改为0
 7. 小雨/小雪/积水 policy开窗>10% -> 截断10%
 8. 雾天 policy开窗>20% -> 截断20%
 9. 开空调+车窗≥50% -> 截断车窗(controller state)
10. 大雨/大雪/积雪/积水 policy打开外循环 -> 删除
14. 空气质量差 policy打开外循环 -> 删除
17. 空调制热+座椅通风 -> 关闭通风
18. 空调制冷+座椅加热 -> 关闭加热
Plus new issues:
A.  缺少特征无推荐执行结果 + 其他动作(外循环/空气净化) -> 保留缺少特征，删除额外动作
B.  logic天气与实拍天气不符 -> 替换为实拍天气对应的短语
"""

import json
import re
import random
from collections import defaultdict

INPUT_FILE = "nlu_car_control_v8_final_v27_new_converted_fixed4_weather_fixed.jsonl"
OUTPUT_FILE = "nlu_car_control_v8_final_v27_new_converted_fixed5.jsonl"

# ============================================================
# Constants
# ============================================================

TEMP_PARSE = re.compile(r'(-?\d+)度')

def parse_temp(s):
    m = TEMP_PARSE.search(s)
    return int(m.group(1)) if m else None

# Seat names
SEATS = ['主驾', '副驾', '后排左', '后排右']

# Weather → window max policy (None = no limit)
WEATHER_WIN_POLICY_MAX = {
    '大雨': 0, '大雪': 0, '积雪': 0,
    '小雨': 10, '小雪': 10, '积水': 10,
    '雾天': 20,
    '晴天': None, '阴天': None,
}

# Weather → window close logic label
WEATHER_WIN_LOGIC = {
    '大雨': '大雨天气需关闭车窗',
    '大雪': '大雪天气需关闭车窗',
    '积雪': '积雪天气需关闭车窗',
    '小雨': '小雨天气限制车窗开度10%',
    '小雪': '小雪天气限制车窗开度10%',
    '积水': '积水路面限制车窗开度10%',
    '雾天': '雾天限制车窗开度20%',
}

# Weather phrases in logic that should be replaced when they don't match 实拍天气
# These are ALL possible weather-related window-restriction phrases
ALL_WEATHER_WIN_PHRASES = [
    '大雪天气需关闭车窗', '大雨天气需关闭车窗', '积雪天气需关闭车窗',
    '小雨天气限制车窗开度10%', '小雪天气限制车窗开度10%', '积水路面限制车窗开度10%',
    '雾天限制车窗开度20%',
    '雨雪天老人儿童限开窗', '雾霾天气限制开窗', '雨雪天限制开窗通风',
    '雾霾天限制开窗通风', '雾霾天不宜开窗',
    '下雨限制开窗后排左透气', '下雨限制开窗主驾透气', '下雨限制开窗副驾透气',
    '下雨限制开窗后排右透气', '下雨微开窗透气',
    '雾限制开窗主驾透气', '雾限制开窗后排左透气', '雾限制开窗后排右透气',
    '雾限制开窗副驾透气', '雾微开窗透气',
    '下雨限制开窗辅助通风', '雾限制开窗辅助通风',
    '雨天限制开窗10%', '雨天限制开窗5%', '雪天限制开窗5%',
    '下雨关闭车窗', '车外空气差雨天不开窗',
]

# Detect weather type in a logic phrase
def detect_weather_type_in_phrase(phrase):
    """Return the weather-class implied by the phrase."""
    if any(x in phrase for x in ['大雨', '大雪', '积雪', '大雪', '关闭车窗', '下雨关闭']):
        if '大雨' in phrase: return 'close_rain'
        if '大雪' in phrase: return 'close_snow'
        if '积雪' in phrase: return 'close_snow'
        if '下雨关闭' in phrase: return 'close_rain'
    if any(x in phrase for x in ['小雨', '小雪', '积水']):
        return 'limit10'
    if any(x in phrase for x in ['雾', '雾天', '雾霾']):
        return 'limit20_or_close'
    if '雨雪' in phrase:
        return 'rain_or_snow'
    if any(x in phrase for x in ['下雨', '雨天']):
        return 'rain'
    return None

# ============================================================
# Text field parsers
# ============================================================

def get_field(text, field):
    """Extract value after 'field:' up to ';' or newline."""
    m = re.search(rf'{re.escape(field)}:([^;\n]+)', text)
    return m.group(1).strip() if m else None

def parse_controller_state(text):
    """
    Parse 控制器状态 block.
    Returns dict with keys: ac_on, ac_mode, ac_temp, ac_fan, seats (dict), windows (dict)
    """
    m = re.search(r'#控制器状态\n(.+)', text, re.DOTALL)
    if not m:
        return None
    cs = m.group(1).strip()

    result = {
        'ac_on': False, 'ac_mode': None, 'ac_temp': None, 'ac_fan': None,
        'seats': {}, 'windows': {}
    }

    # AC
    if '空调开启' in cs:
        result['ac_on'] = True
        for mode in ['制冷', '制热', '通风']:
            if mode in cs:
                result['ac_mode'] = mode
                break
        tm = re.search(r'(\d+)度', cs)
        if tm:
            result['ac_temp'] = int(tm.group(1))
        fm = re.search(r'(\d+)档风量', cs)
        if fm:
            result['ac_fan'] = int(fm.group(1))

    # Seats
    sm = re.search(r'座椅加热或通风:([^\n;]+)', cs)
    if sm:
        seat_str = sm.group(1)
        for seat in SEATS:
            sm2 = re.search(rf'{seat}(\S+)', seat_str)
            if sm2:
                result['seats'][seat] = sm2.group(1)

    # Windows - format: 主驾70%,副驾80%,...
    wm = re.search(r'车窗开度:([^\n]+)', cs)
    if wm:
        win_str = wm.group(1)
        for m2 in re.finditer(r'([^\d,;:]+?)(\d+)%', win_str):
            seat = m2.group(1).strip()
            pct = int(m2.group(2))
            result['windows'][seat] = pct

    return result

# ============================================================
# Issue fix functions
# ============================================================

stats = defaultdict(int)

def fix_text_gear_speed(text):
    """Fix 1: 档位P but 车速 != 驻车 -> set 车速 to 驻车"""
    gear = get_field(text, '档位')
    speed = get_field(text, '车速')
    if gear == 'P' and speed != '驻车':
        text = re.sub(r'(车速:)[^;]+', r'\1驻车', text)
        stats['①档位P车速非驻车'] += 1
    return text

def fix_text_window_controller(text, actual_weather):
    """Fix 9: AC on + window >= 50% in controller state -> clip to 30%"""
    cs_match = re.search(r'(#控制器状态\n.+)', text, re.DOTALL)
    if not cs_match:
        return text
    cs = cs_match.group(1)

    ac_on = '空调开启' in cs
    if not ac_on:
        return text

    # Parse windows in controller state
    win_match = re.search(r'(车窗开度:)([^\n]+)', cs)
    if not win_match:
        return text

    win_str = win_match.group(2)
    changed = False
    new_parts = []

    for m in re.finditer(r'([^\d,;:]+?)(\d+)%', win_str):
        seat = m.group(1).strip()
        pct = int(m.group(2))
        if pct >= 50:
            new_parts.append((m.start(), m.end(), f'{seat}30%'))
            changed = True
        else:
            new_parts.append((m.start(), m.end(), m.group(0)))

    if changed:
        # Rebuild win_str
        result = win_str
        for start, end, new_val in reversed(new_parts):
            result = result[:start] + new_val + result[end:]
        new_cs = cs[:win_match.start(2)] + result + cs[win_match.end(2):]
        text = text[:cs_match.start()] + new_cs
        stats['⑨空调+车窗≥50%'] += 1

    return text

def fix_seat_state(seat_str, seat, action):
    """Remove/replace seat action in 座椅加热或通风 string."""
    # Replace e.g. '主驾加热开启' with '主驾关闭', or '副驾通风开启' with '副驾关闭'
    result = re.sub(rf'{seat}(加热开启|加热\d档|通风开启|通风\d档)', f'{seat}关闭', seat_str)
    return result

def fix_text_seats(text, ac_mode, indoor_temp):
    """
    Fix 2: 低温(≤16°)座椅通风 -> 关闭
    Fix 3: 高温(≥30°)座椅加热 -> 关闭
    Fix 17: 空调制热+座椅通风 -> 关闭通风
    Fix 18: 空调制冷+座椅加热 -> 关闭加热 (make consistent)
    Returns (new_text, seat_changes_dict) where seat_changes_dict maps seat -> 'closed_ventilation' or 'closed_heating'
    """
    sm = re.search(r'(座椅加热或通风:)([^\n;]+)', text)
    if not sm:
        return text, {}

    seat_str = sm.group(2)
    new_seat_str = seat_str
    changes = {}

    for seat in SEATS:
        # Find current state of this seat
        m = re.search(rf'{seat}(\S+)', seat_str)
        if not m:
            continue
        state = m.group(1)

        if '通风' in state:
            # Fix 2: low temp -> close ventilation
            if indoor_temp is not None and indoor_temp <= 16:
                new_seat_str = re.sub(rf'{seat}(通风开启|通风\d档)', f'{seat}关闭', new_seat_str)
                changes[seat] = 'closed_ventilation_lowtemp'
                stats['②低温座椅通风'] += 1
            # Fix 17: 制热 + 通风 -> close ventilation
            elif ac_mode == '制热':
                new_seat_str = re.sub(rf'{seat}(通风开启|通风\d档)', f'{seat}关闭', new_seat_str)
                changes[seat] = 'closed_ventilation_heating'
                stats['⑰制热+座椅通风'] += 1

        if '加热' in state:
            # Fix 3: high temp -> close heating
            if indoor_temp is not None and indoor_temp >= 30:
                new_seat_str = re.sub(rf'{seat}(加热开启|加热\d档)', f'{seat}关闭', new_seat_str)
                changes[seat] = 'closed_heating_hightemp'
                stats['③高温座椅加热'] += 1
            # Fix 18: 制冷 + 加热 -> close heating
            elif ac_mode == '制冷':
                new_seat_str = re.sub(rf'{seat}(加热开启|加热\d档)', f'{seat}关闭', new_seat_str)
                changes[seat] = 'closed_heating_cooling'
                stats['⑱制冷+座椅加热'] += 1

    if new_seat_str != seat_str:
        text = text[:sm.start(2)] + new_seat_str + text[sm.end(2):]

    return text, changes

def fix_text_ac_mode(text, indoor_temp):
    """
    Fix 4: 低温(≤18°)空调制冷 -> 制热
    Fix 5: 高温(≥30°)空调制热 -> 制冷
    Returns (new_text, ac_change) where ac_change is 'to_heat', 'to_cool', or None
    """
    if indoor_temp is None:
        return text, None

    ac_on = '空调开启' in text
    if not ac_on:
        return text, None

    ac_mode = None
    for mode in ['制冷', '制热', '通风']:
        if f'空调开启,{mode}' in text or f'空调开启, {mode}' in text:
            ac_mode = mode
            break
    # Also try without comma
    if not ac_mode:
        m = re.search(r'空调开启[,，]?(制冷|制热|通风)', text)
        if m:
            ac_mode = m.group(1)

    change = None
    if ac_mode == '制冷' and indoor_temp <= 18:
        # Switch to 制热
        text = re.sub(r'(空调开启[,，]?)制冷', r'\1制热', text)
        change = 'to_heat'
        stats['④低温制冷'] += 1
    elif ac_mode == '制热' and indoor_temp >= 30:
        # Switch to 制冷
        text = re.sub(r'(空调开启[,，]?)制热', r'\1制冷', text)
        change = 'to_cool'
        stats['⑤高温制热'] += 1

    return text, change

# ============================================================
# Policy / Logic fix functions
# ============================================================

def remove_waiquxun_from_policy(policy, reason=''):
    """Remove 打开外循环 from policy string."""
    parts = [p.strip() for p in policy.split('，')]
    new_parts = [p for p in parts if p != '打开外循环']
    if len(new_parts) < len(parts):
        stats[f'删除外循环_{reason}'] += 1
    return '，'.join(new_parts)

def fix_policy_window_limit(policy, max_pct, weather):
    """
    Fix 6/7/8: In policy, ensure window open % respects max_pct.
    max_pct=0: remove any open-window instructions
    max_pct=N: cap all window % values to N
    """
    if max_pct is None:
        return policy, False

    changed = False

    if max_pct == 0:
        # Remove any "打开车窗" or "xxx车窗打开N%" instructions
        parts = [p.strip() for p in policy.split('，')]
        new_parts = []
        for p in parts:
            # Keep if it doesn't open windows (i.e., it's closing or unrelated)
            if re.search(r'车窗打开\d+%', p) or re.search(r'打开\S*车窗', p):
                changed = True
                stats['⑥大雨大雪policy开窗'] += 1
                continue
            if re.search(r'车窗\S*打开', p):
                changed = True
                stats['⑥大雨大雪policy开窗'] += 1
                continue
            new_parts.append(p)
        policy = '，'.join(new_parts)
    else:
        # Cap percentages
        def cap_pct(m):
            nonlocal changed
            pct = int(m.group(1))
            if pct > max_pct:
                changed = True
                if max_pct == 10:
                    stats['⑦小雨雪policy开窗超限'] += 1
                else:
                    stats['⑧雾天policy开窗超限'] += 1
                return f'{max_pct}%'
            return m.group(0)
        policy = re.sub(r'(\d+)%', cap_pct, policy)

    return policy, changed

def fix_policy_seats(policy, seat_changes):
    """
    Update policy to reflect seat state changes.
    seat_changes: dict {seat -> reason_code}
    """
    if not seat_changes:
        return policy

    # Build replacements
    for seat, reason in seat_changes.items():
        if 'ventilation' in reason:
            # Remove or replace seat ventilation policy items
            # Pattern: '主驾座椅通风3档' or '主驾座椅通风开启' etc
            policy = re.sub(rf'{seat}座椅通风\S*', f'{seat}座椅通风关闭', policy)
            policy = re.sub(rf'开启{seat}座椅通风', f'关闭{seat}座椅通风', policy)
        elif 'heating' in reason:
            # Remove or replace seat heating policy items
            policy = re.sub(rf'{seat}座椅加热\S*', f'{seat}座椅加热关闭', policy)
            policy = re.sub(rf'开启{seat}座椅加热', f'关闭{seat}座椅加热', policy)

    return policy

def fix_policy_ac_mode(policy, ac_change):
    """Update policy AC mode references."""
    if not ac_change:
        return policy
    if ac_change == 'to_heat':
        policy = policy.replace('空调切换制冷模式', '空调切换制热模式')
        policy = policy.replace('空调制冷', '空调制热')
    elif ac_change == 'to_cool':
        policy = policy.replace('空调切换制热模式', '空调切换制冷模式')
        policy = policy.replace('空调制热', '空调制冷')
    return policy

def fix_logic_weather(logic, actual_weather):
    """
    Fix B: Replace weather-related phrases in logic to match 实拍天气.
    """
    # Get the correct phrase for the actual weather
    correct_phrase = WEATHER_WIN_LOGIC.get(actual_weather, None)

    # Check if any weather phrase exists and doesn't match
    changed = False
    new_logic = logic

    for phrase in ALL_WEATHER_WIN_PHRASES:
        if phrase in logic:
            # Does this phrase match actual weather?
            if correct_phrase and phrase != correct_phrase:
                new_logic = new_logic.replace(phrase, correct_phrase)
                changed = True
            elif correct_phrase is None:
                # No weather restriction needed (晴天/阴天), remove the phrase
                # But be careful - don't leave dangling separators
                parts = [p.strip() for p in new_logic.split('，')]
                parts = [p for p in parts if p != phrase]
                new_logic = '，'.join(parts)
                changed = True

    # Clean up duplicates
    if changed:
        parts = new_logic.split('，')
        seen = []
        for p in parts:
            if p.strip() not in seen:
                seen.append(p.strip())
        new_logic = '，'.join(seen)
        stats['B_logic天气不符'] += 1

    return new_logic

def fix_policy_no_feature_extras(policy):
    """
    Fix A: 缺少特征无推荐执行结果 should not have extra actions like 打开外循环/打开空气净化.
    Keep only 缺少特征... and window-close actions if present, remove others.
    """
    if '缺少特征无推荐执行结果' not in policy:
        return policy

    parts = [p.strip() for p in policy.split('，') if p.strip()]

    # Allowed: 缺少特征..., 关闭所有车窗, 座椅加热关闭类
    # Not allowed: 打开外循环, 打开空气净化, standalone AC actions
    EXTRAS_TO_REMOVE = ['打开外循环', '打开空气净化', '打开内循环']

    new_parts = []
    removed = False
    for p in parts:
        if p in EXTRAS_TO_REMOVE:
            removed = True
            continue
        new_parts.append(p)

    if removed:
        stats['A_缺少特征有额外动作'] += 1

    return '，'.join(new_parts)

# ============================================================
# Main fix logic per record
# ============================================================

def fix_record(rec):
    text = rec['text']
    label = rec['label']

    # Parse environment
    actual_weather = get_field(text, '实拍天气') or ''
    indoor_temp_str = get_field(text, '车内温度') or ''
    indoor_temp = parse_temp(indoor_temp_str)
    air_quality = get_field(text, '车外空气质量') or ''

    policy = label.get('policy', '')
    intent = label.get('intent', '')
    logic = label.get('logic', '')

    # Parse controller state for AC mode (needed for seat fixes)
    cs = parse_controller_state(text)
    ac_mode = cs.get('ac_mode') if cs else None
    ac_on = cs.get('ac_on', False) if cs else False

    # ---- TEXT FIXES ----

    # Fix 1: 档位P + 非驻车车速
    text = fix_text_gear_speed(text)

    # Fix 9: AC on + windows >= 50% in controller state
    if ac_on:
        text = fix_text_window_controller(text, actual_weather)

    # Fix 2, 3, 17, 18: Seat states
    text, seat_changes = fix_text_seats(text, ac_mode, indoor_temp)

    # Fix 4, 5: AC mode
    text, ac_change = fix_text_ac_mode(text, indoor_temp)

    # After AC mode change, update seat fix if needed
    # If we just changed AC to 制热, re-check ventilation seats
    if ac_change == 'to_heat':
        # Need to re-parse and fix seats again for ventilation
        cs2 = parse_controller_state(text)
        ac_mode2 = cs2.get('ac_mode') if cs2 else None
        text, seat_changes2 = fix_text_seats(text, ac_mode2, indoor_temp)
        for k, v in seat_changes2.items():
            seat_changes[k] = v
    elif ac_change == 'to_cool':
        cs2 = parse_controller_state(text)
        ac_mode2 = cs2.get('ac_mode') if cs2 else None
        text, seat_changes2 = fix_text_seats(text, ac_mode2, indoor_temp)
        for k, v in seat_changes2.items():
            seat_changes[k] = v

    # ---- POLICY FIXES ----

    # Fix A: 缺少特征 + extra actions
    policy = fix_policy_no_feature_extras(policy)

    # Fix 10/14: 外循环 in bad weather or bad air quality
    win_max = WEATHER_WIN_POLICY_MAX.get(actual_weather, None)
    bad_weather_for_waiquxun = actual_weather in ['大雨', '大雪', '积雪', '积水']
    bad_air = air_quality == '低'

    if bad_weather_for_waiquxun:
        policy = remove_waiquxun_from_policy(policy, '大雨大雪')
    if bad_air:
        policy = remove_waiquxun_from_policy(policy, '空气差')

    # Fix 6/7/8: Policy window limits by weather
    if win_max is not None:
        policy, _ = fix_policy_window_limit(policy, win_max, actual_weather)

    # Fix seats in policy
    policy = fix_policy_seats(policy, seat_changes)

    # Fix AC mode in policy
    policy = fix_policy_ac_mode(policy, ac_change)

    # ---- LOGIC FIXES ----

    # Fix B: Logic weather mismatch
    logic = fix_logic_weather(logic, actual_weather)

    # Reflect seat changes in logic
    # (Seat-change logic already handled in Phase 2, just keep consistent)

    label['policy'] = policy
    label['logic'] = logic
    rec['text'] = text
    rec['label'] = label

    return rec

# ============================================================
# Main
# ============================================================

def main():
    print(f"Reading {INPUT_FILE}...")
    records = []
    with open(INPUT_FILE, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            # label may be string or dict - normalize to dict
            if isinstance(rec['label'], str):
                rec['label'] = json.loads(rec['label'])
            records.append(rec)

    print(f"Loaded {len(records)} records. Fixing...")

    fixed = [fix_record(rec) for rec in records]

    print(f"Writing {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for rec in fixed:
            # Serialize label back to dict (keep as dict in this version)
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')

    print("\n=== Fix Statistics ===")
    total = 0
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")
        total += v
    print(f"  TOTAL fixes: {total}")
    print("Done.")

if __name__ == '__main__':
    main()
