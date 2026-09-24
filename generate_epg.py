#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EPG 生成脚本 - 央视/卫视全变体版（OK影视向）
策略：
  1) 央视每个变体都建独立 channel（CCTV-1 / CCTV1 / CCTV1-综合 / CCTV-1综合 ...）
  2) 每个 channel 都带完整 programme
  3) 每个 channel 的 display-name 包含“同编号所有变体”
  4) 卫视同理：湖南卫视 / 湖南 / HunanTV / 湖南卫视HD 都建 channel
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
    "https://live.fanmingming.cn/e.xml",
    "https://epg.112114.xyz/pp.xml",
    "https://proxy.lalifeier.eu.org/https://raw.githubusercontent.com/5iClub/CN.EPG/main/epg.xml",
    "https://gitee.com/taksssss/tv/raw/main/epg/51zmt.xml.gz",
    "https://gitee.com/taksssss/tv/raw/main/epg/51zmte1.xml.gz",
    "https://gitee.com/taksssss/tv/raw/main/epg/51zmte2.xml.gz",
    "https://gitee.com/taksssss/tv/raw/main/epg/erw.xml.gz",
    "https://gitee.com/taksssss/tv/raw/main/epg/epgpw_cn.xml.gz",
    "https://raw.githubusercontent.com/CCSH/IPTV/refs/heads/main/e.xml",
    "https://raw.githubusercontent.com/litiande03/epg/refs/heads/master/pl.xml.gz",
    "https://gitlab.com/Meroser/My-EPG/-/raw/main/tvxml-Meroser.xml.gz",
]

PROVINCE_TV_MAP = {
    "湖南卫视": "HunanTV", "湖南": "HunanTV", "芒果台": "HunanTV",
    "浙江卫视": "ZhejiangTV", "浙江": "ZhejiangTV",
    "江苏卫视": "JiangsuTV", "江苏": "JiangsuTV",
    "东方卫视": "DongfangTV", "东方": "DongfangTV",
    "北京卫视": "BeijingTV", "北京": "BeijingTV",
    "广东卫视": "GuangdongTV", "广东": "GuangdongTV",
    "深圳卫视": "ShenzhenTV", "深圳": "ShenzhenTV",
    "山东卫视": "ShandongTV", "山东": "ShandongTV",
    "安徽卫视": "AnhuiTV", "安徽": "AnhuiTV",
    "四川卫视": "SichuanTV", "四川": "SichuanTV",
    "湖北卫视": "HubeiTV", "湖北": "HubeiTV",
    "天津卫视": "TianjinTV", "天津": "TianjinTV",
    "辽宁卫视": "LiaoningTV", "辽宁": "LiaoningTV",
    "河南卫视": "HenanTV", "河南": "HenanTV",
    "江西卫视": "JiangxiTV", "江西": "JiangxiTV",
    "重庆卫视": "ChongqingTV", "重庆": "ChongqingTV",
    "东南卫视": "FujianTV", "福建": "FujianTV", "福建卫视": "FujianTV",
    "黑龙江卫视": "HeilongjiangTV", "黑龙江": "HeilongjiangTV",
    "河北卫视": "HebeiTV", "河北": "HebeiTV",
    "山西卫视": "ShanxiTV", "山西": "ShanxiTV",
    "陕西卫视": "ShaanxiTV", "陕西": "ShaanxiTV",
    "广西卫视": "GuangxiTV", "广西": "GuangxiTV",
    "云南卫视": "YunnanTV", "云南": "YunnanTV",
    "贵州卫视": "GuizhouTV", "贵州": "GuizhouTV",
    "吉林卫视": "JilinTV", "吉林": "JilinTV",
    "甘肃卫视": "GansuTV", "甘肃": "GansuTV",
    "内蒙古卫视": "NeimengguTV", "内蒙古": "NeimengguTV",
    "新疆卫视": "XinjiangTV", "新疆": "XinjiangTV",
    "宁夏卫视": "NingxiaTV", "宁夏": "NingxiaTV",
    "青海卫视": "QinghaiTV", "青海": "QinghaiTV",
    "西藏卫视": "XizangTV", "西藏": "XizangTV",
    "海南卫视": "HainanTV", "海南": "HainanTV",
    "兵团卫视": "BingtuanTV", "兵团": "BingtuanTV",
    "延边卫视": "YanbianTV", "延边": "YanbianTV",
}

CCTV_NAME_MAP = {
    "1": "综合", "2": "财经", "3": "综艺", "4": "中文国际",
    "5": "体育", "6": "电影", "7": "国防军事", "8": "电视剧",
    "9": "纪录", "10": "科教", "11": "戏曲", "12": "社会与法",
    "13": "新闻", "14": "少儿", "15": "音乐", "16": "奥林匹克",
    "17": "农业农村",
}


def fetch_epg_from_sources(sources):
    for i, url in enumerate(sources, 1):
        try:
            print(f"  [{i}/{len(sources)}] 尝试: {url[:60]}...")
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            c = r.content
            if url.endswith('.gz') or c[:2] == b'\x1f\x8b':
                with gzip.GzipFile(fileobj=io.BytesIO(c)) as gz:
                    return gz.read().decode('utf-8')
            return c.decode('utf-8')
        except Exception as e:
            print(f"  ✗ {e}")
    sys.exit("所有EPG源失败")


def get_cctv_number(text):
    if not text:
        return None
    m = re.search(r'CCTV[-\s]?(\d+\+?|4K|8K)', text, re.IGNORECASE)
    return m.group(1).upper() if m else None


def get_province_canon(name):
    if not name:
        return None
    if name in PROVINCE_TV_MAP:
        return PROVINCE_TV_MAP[name]
    for k, v in PROVINCE_TV_MAP.items():
        if k in name:
            return v
    return None


def gen_all_cctv_aliases(num):
    """
    关键：三段组合
    前缀 × 编号 × 后缀
    后缀包含：
      "" 综合 高清 HD 超高清 中文名
      -综合 -高清 -HD 综合 高清 HD
      " 综合" " 高清"
    """
    aliases = set()
    name = CCTV_NAME_MAP.get(num, "")

    prefixes = ["CCTV", "CCTV-", "cctv", "cctv-"]

    base_suffixes = ["", "综合", "高清", "HD", "超高清"]
    if name:
        base_suffixes.append(name)

    composed = set(base_suffixes)
    for s in base_suffixes:
        if s:
            composed.add(f"-{s}")   # CCTV1-综合 / CCTV1-HD
            composed.add(f" {s}")   # CCTV1 综合 / CCTV1 HD
    # 再补“先横线后中文”已经被上面 -综合 覆盖
    # 显式补一些常见野鸡写法
    composed.update([
        "综合高清", "-综合高清", "综合HD", "-综合HD",
        "高清综合", "-高清综合",
    ])

    for p in prefixes:
        for s in composed:
            aliases.add(f"{p}{num}{s}")

    # 5+
    if num == "5+":
        for p in prefixes:
            for s in ["", "体育", "体育赛事", "高清", "HD", "-体育", "-体育赛事", "-高清", "-HD"]:
                aliases.add(f"{p}5+{s}")

    # 4K / 8K
    if num in ("4K", "8K"):
        for p in prefixes:
            for s in ["", "超高清", "高清", "HD", "-超高清", "-高清", "-HD"]:
                aliases.add(f"{p}{num}{s}")

    # CCTV-1 专属：没有编号只有综合
    if num == "1":
        aliases.update([
            "CCTV综合", "CCTV-综合", "CCTV 综合",
            "cctv综合", "cctv-综合",
            "CCTV综合高清", "CCTV-综合高清",
            "中央电视台综合频道", "央视综合", "央视综合频道",
        ])

    aliases.discard("")
    return aliases


def gen_province_aliases(canon_id, seed_names):
    a = {canon_id}
    for n in seed_names:
        a.add(n)
        if "卫视" in n:
            base = n.replace("卫视", "")
            a.update([base, f"{base}卫视HD", f"{base}卫视高清", f"{base}TV", f"{base}-TV"])
    return a


def _rebuild_channel(existing, new_channels, alias, all_aliases, canon_progs):
    ch = existing.get(alias)
    if ch is None:
        ch = ET.Element('channel')
        ch.set('id', alias)
        new_channels.append(ch)
        existing[alias] = ch
    else:
        for d in ch.findall('display-name'):
            ch.remove(d)

    dn = ET.SubElement(ch, 'display-name')
    dn.text = alias
    dn.set('lang', 'zh')

    for s in sorted(all_aliases):
        if s == alias:
            continue
        d = ET.SubElement(ch, 'display-name')
        d.text = s
        d.set('lang', 'zh')

    for prog in canon_progs:
        np = copy.deepcopy(prog)
        np.set('channel', alias)
        yield np


def process_cctv(root):
    prog_map = {}
    for p in root.findall('programme'):
        prog_map.setdefault(p.get('channel'), []).append(p)

    groups = {}
    for ch in root.findall('channel'):
        cid = ch.get('id')
        if not cid:
            continue
        dns = [e.text for e in ch.findall('display-name') if e.text]
        num = get_cctv_number(cid)
        if not num:
            num = next((get_cctv_number(d) for d in dns), None)
        if not num:
            continue
        groups.setdefault(num, []).append({
            'id': cid,
            'progs': prog_map.get(cid, []),
        })

    if not groups:
        print("· 无央视")
        return

    all_ids = set()
    for num, items in groups.items():
        all_ids |= gen_all_cctv_aliases(num)
        for it in items:
            all_ids.add(it['id'])

    for p in list(root.findall('programme')):
        if p.get('channel') in all_ids:
            root.remove(p)

    existing = {c.get('id'): c for c in root.findall('channel')}
    new_channels = []
    new_progs = []

    for num, items in sorted(groups.items()):
        canon_progs = max((it['progs'] for it in items), key=len) if items else []
        aliases = gen_all_cctv_aliases(num)
        for it in items:
            aliases.add(it['id'])

        for alias in sorted(aliases):
            for np in _rebuild_channel(existing, new_channels, alias, aliases, canon_progs):
                new_progs.append(np)

    _insert(root, new_channels, new_progs)
    print(f"✓ 央视：新增频道 {len(new_channels)}，节目 {len(new_progs)}")


def process_province(root):
    prog_map = {}
    for p in root.findall('programme'):
        prog_map.setdefault(p.get('channel'), []).append(p)

    groups = {}
    for ch in root.findall('channel'):
        cid = ch.get('id')
        if not cid:
            continue
        dns = [e.text for e in ch.findall('display-name') if e.text]
        canon = get_province_canon(cid) or next((get_province_canon(d) for d in dns), None)
        if not canon:
            continue
        g = groups.setdefault(canon, {'seeds': set(), 'progs': []})
        g['seeds'].add(cid)
        g['seeds'].update(dns)
        g['progs'].extend(prog_map.get(cid, []))

    if not groups:
        print("· 无卫视")
        return

    old_ids = set()
    for g in groups.values():
        old_ids.update(g['seeds'])

    for p in list(root.findall('programme')):
        if p.get('channel') in old_ids:
            root.remove(p)

    for ch in list(root.findall('channel')):
        if ch.get('id') in old_ids and ch.get('id') not in groups:
            root.remove(ch)

    existing = {c.get('id'): c for c in root.findall('channel')}
    new_channels = []
    new_progs = []

    for canon, g in sorted(groups.items()):
        aliases = gen_province_aliases(canon, g['seeds'])
        for alias in sorted(aliases):
            for np in _rebuild_channel(existing, new_channels, alias, aliases, g['progs']):
                new_progs.append(np)

    _insert(root, new_channels, new_progs)
    print(f"✓ 卫视：新增频道 {len(new_channels)}，节目 {len(new_progs)}")


def _insert(root, new_channels, new_progs):
    if new_channels:
        idx = len(root)
        for i, child in enumerate(root):
            if child.tag == 'programme':
                idx = i
                break
        for off, ch in enumerate(new_channels):
            root.insert(idx + off, ch)
    root.extend(new_progs)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "epg.xml"
    print("📡 获取EPG...")
    xml_text = fetch_epg_from_sources(EPG_SOURCES)
    root = ET.fromstring(xml_text)

    print("📺 原始:", len(root.findall('channel')), "频道 /",
          len(root.findall('programme')), "节目")

    process_cctv(root)
    process_province(root)

    root.set('generated', datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    ET.ElementTree(root).write(out, encoding='utf-8', xml_declaration=True)
    print(f"✅ {out} | 频道 {len(root.findall('channel') )} / 节目 {len(root.findall('programme'))}")


if __name__ == "__main__":
    main()
