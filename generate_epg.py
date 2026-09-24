#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EPG 生成脚本 - 修复 OK影视 匹配问题（v2）
核心策略：
  1) 每个频道只保留一个"规范ID"（如 CCTV-1），所有变体作为 display-name
  2) programme 只挂在规范ID上
  3) 所有变体（CCTV1 / CCTV-1 / CCTV1综合 / CCTV1-综合 / ...）都作为 display-name
  4) 自动归一化：CCTV1 → CCTV-1，CCTV01 → CCTV-1，CCTV 1 → CCTV-1
  5) 卫视同样处理：湖南卫视 → HunanTV，湖南卫视HD → HunanTV
"""

import xml.etree.ElementTree as ET
import requests
import sys
import re
import gzip
import io
import os
import datetime
import copy

# ---------- 配置 ----------
EPG_SOURCES = [
    "https://proxy.lalifeier.eu.org/https://raw.githubusercontent.com/5iClub/CN.EPG/main/epg.xml",
    "https://gitee.com/taksssss/tv/raw/main/epg/51zmt.xml.gz",
    "https://gitee.com/taksssss/tv/raw/main/epg/51zmte1.xml.gz",
    "https://gitee.com/taksssss/tv/raw/main/epg/51zmte2.xml.gz",
    "https://gitee.com/taksssss/tv/raw/main/epg/erw.xml.gz",
    "https://gitee.com/taksssss/tv/raw/main/epg/epgpw_cn.xml.gz",
    "https://gitee.com/taksssss/tv/raw/main/epg/epgpw_hk.xml.gz",
    "https://gitee.com/taksssss/tv/raw/main/epg/epgpw_tw.xml.gz",
    "https://raw.githubusercontent.com/CCSH/IPTV/refs/heads/main/e.xml",
    "https://raw.githubusercontent.com/litiande03/epg/refs/heads/master/pl.xml.gz",
    "https://gitlab.com/Meroser/My-EPG/-/raw/main/tvxml-Meroser.xml.gz",
    "https://epg.112114.xyz/pp.xml",
    "https://live.fanmingming.cn/e.xml",
]

# 卫视映射表（可自定义添加）
PROVINCE_TV_MAP = {
    "湖南卫视": "HunanTV",
    "湖南": "HunanTV",
    "湖南卫视高清": "HunanTV",
    "芒果台": "HunanTV",
    "浙江卫视": "ZhejiangTV",
    "浙江": "ZhejiangTV",
    "江苏卫视": "JiangsuTV",
    "江苏": "JiangsuTV",
    "东方卫视": "DongfangTV",
    "东方": "DongfangTV",
    "北京卫视": "BeijingTV",
    "北京": "BeijingTV",
    "广东卫视": "GuangdongTV",
    "广东": "GuangdongTV",
    "深圳卫视": "ShenzhenTV",
    "深圳": "ShenzhenTV",
    "山东卫视": "ShandongTV",
    "山东": "ShandongTV",
    "安徽卫视": "AnhuiTV",
    "安徽": "AnhuiTV",
    "四川卫视": "SichuanTV",
    "四川": "SichuanTV",
    "湖北卫视": "HubeiTV",
    "湖北": "HubeiTV",
    "天津卫视": "TianjinTV",
    "天津": "TianjinTV",
    "辽宁卫视": "LiaoningTV",
    "辽宁": "LiaoningTV",
    "河南卫视": "HenanTV",
    "河南": "HenanTV",
    "江西卫视": "JiangxiTV",
    "江西": "JiangxiTV",
    "重庆卫视": "ChongqingTV",
    "重庆": "ChongqingTV",
    "福建东南卫视": "FujianTV",
    "东南卫视": "FujianTV",
    "福建": "FujianTV",
    "黑龙江卫视": "HeilongjiangTV",
    "黑龙江": "HeilongjiangTV",
    "河北卫视": "HebeiTV",
    "河北": "HebeiTV",
    "山西卫视": "ShanxiTV",
    "山西": "ShanxiTV",
    "陕西卫视": "ShaanxiTV",
    "陕西": "ShaanxiTV",
    "广西卫视": "GuangxiTV",
    "广西": "GuangxiTV",
    "云南卫视": "YunnanTV",
    "云南": "YunnanTV",
    "贵州卫视": "GuizhouTV",
    "贵州": "GuizhouTV",
    "吉林卫视": "JilinTV",
    "吉林": "JilinTV",
    "甘肃卫视": "GansuTV",
    "甘肃": "GansuTV",
    "内蒙古卫视": "NeimengguTV",
    "内蒙古": "NeimengguTV",
    "新疆卫视": "XinjiangTV",
    "新疆": "XinjiangTV",
    "宁夏卫视": "NingxiaTV",
    "宁夏": "NingxiaTV",
    "青海卫视": "QinghaiTV",
    "青海": "QinghaiTV",
    "西藏卫视": "XizangTV",
    "西藏": "XizangTV",
    "海南卫视": "HainanTV",
    "海南": "HainanTV",
    "兵团卫视": "BingtuanTV",
    "兵团": "BingtuanTV",
    "延边卫视": "YanbianTV",
    "延边": "YanbianTV",
}

CCTV_NAME_MAP = {
    "1": "综合", "2": "财经", "3": "综艺", "4": "中文国际",
    "5": "体育", "6": "电影", "7": "国防军事", "8": "电视剧",
    "9": "纪录", "10": "科教", "11": "戏曲", "12": "社会与法",
    "13": "新闻", "14": "少儿", "15": "音乐", "16": "奥林匹克",
    "17": "农业农村"
}
# -----------------------------------------------


def fetch_epg_from_sources(sources):
    """从多个源获取EPG数据"""
    for i, url in enumerate(sources, 1):
        try:
            print(f"  [{i}/{len(sources)}] 尝试: {url[:60]}...")
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            content = response.content

            if url.endswith('.gz') or content[:2] == b'\x1f\x8b':
                try:
                    with gzip.GzipFile(fileobj=io.BytesIO(content)) as gz:
                        xml_content = gz.read().decode('utf-8')
                    print(f"  ✓ 成功获取 (gzip)")
                    return xml_content
                except Exception as e:
                    print(f"  ✗ gzip解压失败: {e}")
                    continue

            xml_content = content.decode('utf-8')
            print(f"  ✓ 成功获取 (XML)")
            return xml_content
        except Exception as e:
            print(f"  ✗ 失败: {e}")
            continue

    print(f"❌ 所有EPG源均获取失败")
    sys.exit(1)


def normalize_cctv_name(name):
    """
    归一化央视频道名称
    输入: "CCTV1", "CCTV-1", "CCTV01", "CCTV 1", "CCTV1综合", "CCTV-1综合"
    输出: "CCTV-1" 或 None
    """
    if not name:
        return None
    
    # 统一大小写和空格
    s = name.strip().upper()
    s = s.replace(' ', '').replace('　', '')
    
    # 匹配 CCTV 编号（支持数字、5+、4K、8K）
    m = re.search(r'CCTV0*(\d+\+?|4K|8K)', s)
    if not m:
        return None
    
    num = m.group(1)
    # 去掉前导零
    if num.isdigit():
        num = str(int(num))
    
    return f"CCTV-{num}"


def get_cctv_number(text):
    """从任意字符串里提取央视编号，如 '1'、'5+'、'4K'。"""
    if not text:
        return None
    m = re.search(r'CCTV[-\s]?(\d+\+?|[48]K|\d+)', text, re.IGNORECASE)
    return m.group(1).upper() if m else None


def get_province_tv_name(name):
    """
    识别卫视频道，返回规范ID
    输入: "湖南卫视", "湖南卫视HD", "湖南卫视高清", "芒果台"
    输出: "HunanTV" 或 None
    """
    if not name:
        return None
    
    # 直接匹配映射表
    if name in PROVINCE_TV_MAP:
        return PROVINCE_TV_MAP[name]
    
    # 尝试匹配包含关系
    for key, value in PROVINCE_TV_MAP.items():
        if key in name:
            return value
    
    return None


def gen_all_cctv_aliases(num):
    """
    为给定央视编号生成所有可能的字符串变体。
    举例 num='1'，会返回：
      CCTV1, CCTV-1, cctv1, cctv-1,
      CCTV1综合, CCTV-1综合, CCTV1-综合, CCTV-1-综合,
      CCTV1 综合, CCTV-1 综合,
      CCTV1高清, CCTV-1高清, CCTV1-高清, ...
      CCTV1HD, CCTV-1HD, CCTV1-HD, ...
      CCTV1综合高清, CCTV-1综合高清, ...
      CCTV1超高清, CCTV-1超高清, ...
    """
    aliases = set()
    name = CCTV_NAME_MAP.get(num, "")

    # 前缀（带/不带横线，大小写）
    prefixes = ["CCTV", "CCTV-", "cctv", "cctv-"]

    # 后缀集合
    suffixes = ["", "综合", "高清", "HD", "超高清"]
    if name:
        suffixes.append(name)

    # 加上 "-后缀" 和 " 后缀" 的形式
    extra = []
    for s in suffixes:
        if s:
            extra.append(f"-{s}")
            extra.append(f" {s}")
    all_suffixes = suffixes + extra

    # 组合：前缀 + 编号 + 后缀
    for p in prefixes:
        for s in all_suffixes:
            aliases.add(f"{p}{num}{s}")

    # 5+ 特殊情况
    if num == "5+":
        for p in prefixes:
            for s in ["", "体育", "体育赛事", "高清", "HD",
                      "-体育", "-体育赛事", "-高清", "-HD",
                      " 体育", " 体育赛事", " 高清", " HD"]:
                aliases.add(f"{p}5+{s}")

    # 4K/8K 特殊情况
    if num in ("4K", "8K"):
        for p in prefixes:
            for s in ["", "超高清", "高清", "HD",
                      "-超高清", "-高清", "-HD",
                      " 超高清", " 高清", " HD"]:
                aliases.add(f"{p}{num}{s}")

    aliases.discard("")
    return aliases


def process_cctv_channels(root):
    """
    处理所有央视频道：
      1) 按编号分组，选出规范节目源
      2) 每个编号只保留一个规范ID（如 CCTV-1）
      3) 所有变体作为 display-name
      4) programme 只挂在规范ID上
    """
    # 索引现有节目
    prog_map = {}
    for prog in root.findall('programme'):
        cid = prog.get('channel')
        if cid:
            prog_map.setdefault(cid, []).append(prog)

    # 按 CCTV 编号分组
    groups = {}
    for ch in root.findall('channel'):
        cid = ch.get('id')
        if not cid:
            continue
        dns = [e.text for e in ch.findall('display-name') if e.text]
        num = get_cctv_number(cid)
        if not num:
            for dn in dns:
                num = get_cctv_number(dn)
                if num:
                    break
        if not num:
            continue
        groups.setdefault(num, []).append({
            'ch': ch,
            'id': cid,
            'dns': dns,
            'progs': prog_map.get(cid, []),
        })

    if not groups:
        print("  · 未发现央视频道")
        return

    # 收集所有 CCTV 相关的 id（用于删掉旧节目）
    all_cctv_ids = set()
    for num in groups:
        all_cctv_ids |= gen_all_cctv_aliases(num)
        for item in groups[num]:
            all_cctv_ids.add(item['id'])

    # 删除所有 CCTV id 的旧节目
    removed = 0
    for prog in list(root.findall('programme')):
        if prog.get('channel') in all_cctv_ids:
            root.remove(prog)
            removed += 1

    # 现有频道索引
    existing = {}
    for ch in root.findall('channel'):
        cid = ch.get('id')
        if cid:
            existing[cid] = ch

    new_channels = []
    new_progs = []
    processed_ids = set()  # 记录已处理的规范ID

    # --------- 逐个央视编号处理 ---------
    for num, items in sorted(groups.items()):
        # 规范节目源 = 节目最多的那个
        canon_progs = max((it['progs'] for it in items), key=len) if items else []

        # 规范ID
        canon_id = f"CCTV-{num}"
        
        # 如果规范ID已处理过，跳过
        if canon_id in processed_ids:
            continue
        processed_ids.add(canon_id)

        # 生成所有别名
        aliases = gen_all_cctv_aliases(num)
        for item in items:
            aliases.add(item['id'])
        aliases.discard('')

        # 查找或创建规范频道
        ch = existing.get(canon_id)
        if ch is None:
            # 新频道
            ch = ET.Element('channel')
            ch.set('id', canon_id)
            new_channels.append(ch)
            existing[canon_id] = ch
        else:
            # 已有频道，清空display-name
            for d in ch.findall('display-name'):
                ch.remove(d)

        # 第一个 display-name = 规范ID
        first_dn = ET.SubElement(ch, 'display-name')
        first_dn.text = canon_id
        first_dn.set('lang', 'zh')

        # 附加所有变体作为 display-name
        for s in sorted(aliases):
            if s != canon_id:
                dn = ET.SubElement(ch, 'display-name')
                dn.text = s
                dn.set('lang', 'zh')

        # 复制规范节目到规范ID
        for prog in canon_progs:
            np = copy.deepcopy(prog)
            np.set('channel', canon_id)
            new_progs.append(np)

    # --------- 把新 channel 插到第一个 programme 之前 ---------
    if new_channels:
        idx = len(root)
        for i, child in enumerate(root):
            if child.tag == 'programme':
                idx = i
                break
        for offset, ch in enumerate(new_channels):
            root.insert(idx + offset, ch)

    # 追加节目
    root.extend(new_progs)

    print(f"  ✓ 央视处理完成")
    print(f"     · 编号组: {len(groups)}")
    print(f"     · 新增频道: {len(new_channels)}")
    print(f"     · 删除旧节目: {removed}")
    print(f"     · 写入新节目: {len(new_progs)}")


def process_province_channels(root):
    """
    处理卫视频道：
      1) 识别卫视频道并映射到规范ID
      2) 合并同频道的多个变体
      3) 保留所有变体作为 display-name
    """
    # 索引现有节目
    prog_map = {}
    for prog in root.findall('programme'):
        cid = prog.get('channel')
        if cid:
            prog_map.setdefault(cid, []).append(prog)

    # 收集所有卫视频道
    province_groups = {}  # {规范ID: {aliases: set, progs: list}}
    
    for ch in root.findall('channel'):
        cid = ch.get('id')
        if not cid:
            continue
        dns = [e.text for e in ch.findall('display-name') if e.text]
        
        # 尝试识别卫视
        canon_id = None
        # 先检查id
        canon_id = get_province_tv_name(cid)
        # 再检查display-name
        if not canon_id:
            for dn in dns:
                canon_id = get_province_tv_name(dn)
                if canon_id:
                    break
        
        if not canon_id:
            continue
        
        # 收集该频道的所有别名
        if canon_id not in province_groups:
            province_groups[canon_id] = {
                'aliases': set(),
                'progs': [],
                'channels': []
            }
        
        province_groups[canon_id]['aliases'].add(cid)
        for dn in dns:
            province_groups[canon_id]['aliases'].add(dn)
        province_groups[canon_id]['progs'].extend(prog_map.get(cid, []))
        province_groups[canon_id]['channels'].append(ch)

    if not province_groups:
        print("  · 未发现卫视频道")
        return

    # 收集所有要删除的旧ID
    old_ids = set()
    for group in province_groups.values():
        old_ids.update(group['aliases'])

    # 删除旧节目
    removed = 0
    for prog in list(root.findall('programme')):
        if prog.get('channel') in old_ids:
            root.remove(prog)
            removed += 1

    # 删除旧频道（除了规范ID）
    for ch in list(root.findall('channel')):
        cid = ch.get('id')
        if cid in old_ids and cid not in province_groups:
            root.remove(ch)

    # 现有频道索引
    existing = {}
    for ch in root.findall('channel'):
        cid = ch.get('id')
        if cid:
            existing[cid] = ch

    new_channels = []
    new_progs = []

    # 处理每个卫视
    for canon_id, group in sorted(province_groups.items()):
        # 查找或创建规范频道
        ch = existing.get(canon_id)
        if ch is None:
            ch = ET.Element('channel')
            ch.set('id', canon_id)
            new_channels.append(ch)
            existing[canon_id] = ch
        else:
            # 已有频道，清空display-name
            for d in ch.findall('display-name'):
                ch.remove(d)

        # 第一个 display-name = 规范ID
        first_dn = ET.SubElement(ch, 'display-name')
        first_dn.text = canon_id
        first_dn.set('lang', 'zh')

        # 附加所有变体作为 display-name
        for s in sorted(group['aliases']):
            if s != canon_id:
                dn = ET.SubElement(ch, 'display-name')
                dn.text = s
                dn.set('lang', 'zh')

        # 复制节目到规范ID
        for prog in group['progs']:
            np = copy.deepcopy(prog)
            np.set('channel', canon_id)
            new_progs.append(np)

    # --------- 把新 channel 插到第一个 programme 之前 ---------
    if new_channels:
        idx = len(root)
        for i, child in enumerate(root):
            if child.tag == 'programme':
                idx = i
                break
        for offset, ch in enumerate(new_channels):
            root.insert(idx + offset, ch)

    # 追加节目
    root.extend(new_progs)

    print(f"  ✓ 卫视处理完成")
    print(f"     · 卫视组: {len(province_groups)}")
    print(f"     · 新增频道: {len(new_channels)}")
    print(f"     · 删除旧节目: {removed}")
    print(f"     · 写入新节目: {len(new_progs)}")


def dump_aliases_for_debug(root, num="1"):
    """调试用：输出某个 CCTV 编号下所有已注册的 id 和 display-name。"""
    print(f"\n  --- 调试: CCTV{num} 相关频道 ---")
    for ch in root.findall('channel'):
        cid = ch.get('id') or ''
        if not re.search(rf'CCTV[-\s]?{re.escape(num)}\b', cid, re.IGNORECASE):
            # 也检查 display-name
            dns = [e.text or '' for e in ch.findall('display-name')]
            if not any(re.search(rf'CCTV[-\s]?{re.escape(num)}\b', d, re.IGNORECASE) for d in dns):
                continue
        dns = [e.text or '' for e in ch.findall('display-name')]
        print(f"    id={cid!r}")
        print(f"       display-names={dns}")
    print(f"  --- 调试结束 ---\n")


def main():
    output_file = sys.argv[1] if len(sys.argv) > 1 else "epg.xml"
    print(f"📡 开始获取EPG (共 {len(EPG_SOURCES)} 个备用源)...")
    xml_content = fetch_epg_from_sources(EPG_SOURCES)

    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        print(f"❌ XML解析失败: {e}")
        sys.exit(1)

    print(f"📺 原始频道数: {len(root.findall('channel'))}")
    print(f"📺 原始节目数: {len(root.findall('programme'))}")

    # 核心处理
    process_cctv_channels(root)
    process_province_channels(root)

    # 调试输出 CCTV1 的所有别名
    dump_aliases_for_debug(root, "1")
    dump_aliases_for_debug(root, "5")

    # 时间戳
    root.set('generated', datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    try:
        tree = ET.ElementTree(root)
        tree.write(output_file, encoding='utf-8', xml_declaration=True)
        if os.path.exists(output_file):
            size = os.path.getsize(output_file)
            print(f"✅ 已生成: {output_file} (大小: {size} 字节)")
            print(f"   绝对路径: {os.path.abspath(output_file)}")
            print(f"   总频道数: {len(root.findall('channel'))}")
            print(f"   总节目数: {len(root.findall('programme'))}")
        else:
            print(f"❌ 写入失败，文件不存在")
            sys.exit(1)
    except Exception as e:
        print(f"❌ 写入文件时出错: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
