#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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

CUSTOM_ALIAS_MAP = {
    # "HUNAN": "湖南卫视",
}
# -----------------------------------------------


def fetch_epg_from_sources(sources):
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
                    print(f"  ✓ 成功获取 (gzip压缩格式)")
                    return xml_content
                except Exception as e:
                    print(f"  ✗ gzip解压失败: {e}")
                    continue

            xml_content = content.decode('utf-8')
            print(f"  ✓ 成功获取 (XML格式)")
            return xml_content
        except Exception as e:
            print(f"  ✗ 失败: {e}")
            continue

    print(f"❌ 所有EPG源均获取失败")
    sys.exit(1)


def get_cctv_info(channel_id, display_names):
    """
    识别央视频道，返回 (num, aliases_id, aliases_display)
    num: 频道数字标识，如 '1'、'5+'、'4K'
    aliases_id: 适合作为 <channel id> 的别名集合
    aliases_display: 适合作为 <display-name> 的别名集合
    """
    text = " ".join([channel_id] + display_names)
    if not re.search(r'CCTV|央视|中央', text, re.IGNORECASE):
        return None, set(), set()

    num = None
    candidates = [channel_id] + display_names
    for c in candidates:
        if not c:
            continue
        c = c.strip()
        # 匹配 CCTV1、CCTV-1、CCTV 1、CCTV5+、CCTV4K、CCTV-4K 等
        m = re.search(r'CCTV[-\s]?(\d+\+?|\d+|[48]K|4K|8K)', c, re.IGNORECASE)
        if m:
            num = m.group(1).upper()
            break

    if not num:
        return None, set(), set()

    aliases_id = set()
    aliases_display = set()

    # ---------- 生成 ID 别名（尽量无空格，适合 tvg-id）----------
    id_bases = [
        f"CCTV{num}", f"CCTV-{num}",
        f"cctv{num}", f"cctv-{num}",
    ]

    if num.isdigit():
        id_bases += [
            f"CCTV{num}综合", f"CCTV-{num}综合",
            f"CCTV{num}高清", f"CCTV-{num}高清",
            f"CCTV{num}HD", f"CCTV-{num}HD",
            f"CCTV{num}综合高清", f"CCTV-{num}综合高清",
        ]
    elif num == "5+":
        id_bases += [
            f"CCTV5+", f"CCTV-5+", f"cctv5+", f"cctv-5+",
            f"CCTV5+体育赛事", f"CCTV-5+体育赛事",
            f"CCTV5+高清", f"CCTV-5+高清",
        ]
    elif num in ("4K", "8K"):
        id_bases += [
            f"CCTV{num}", f"CCTV-{num}", f"cctv{num}", f"cctv-{num}",
            f"CCTV{num}超高清", f"CCTV-{num}超高清",
        ]

    aliases_id.update(id_bases)
    aliases_id.discard(channel_id)

    # ---------- 生成 display-name 别名（可含空格、中文）----------
    display_bases = set(id_bases)

    if num.isdigit():
        cctv_names = {
            "1": "综合", "2": "财经", "3": "综艺", "4": "中文国际",
            "5": "体育", "6": "电影", "7": "国防军事", "8": "电视剧",
            "9": "纪录", "10": "科教", "11": "戏曲", "12": "社会与法",
            "13": "新闻", "14": "少儿", "15": "音乐", "16": "奥林匹克",
            "17": "农业农村"
        }
        name = cctv_names.get(num, "")
        if name:
            display_bases.update([
                f"CCTV{num}{name}", f"CCTV-{num}{name}",
                f"CCTV{num} {name}", f"CCTV-{num} {name}",
                f"CCTV{num}{name}高清", f"CCTV-{num}{name}高清",
                f"CCTV{num} {name} 高清", f"CCTV-{num} {name} 高清",
                f"CCTV{num}{name}HD", f"CCTV-{num}{name}HD",
                f"CCTV{num} {name} HD", f"CCTV-{num} {name} HD",
            ])

    # 通用带空格别名
    display_bases.update([
        f"CCTV{num} 综合", f"CCTV-{num} 综合",
        f"CCTV{num} 高清", f"CCTV-{num} 高清",
        f"CCTV{num} HD", f"CCTV-{num} HD",
    ])

    aliases_display.update(display_bases)
    aliases_display.discard(channel_id)

    return num, aliases_id, aliases_display


def add_cctv_id_aliases(root):
    """
    为央视频道创建多个 <channel id="..."> 别名，并复制对应 <programme>。
    解决 OK影视 用 tvg-id 匹配不到央视的问题。
    修改版：即使别名已存在，也会补充缺失的节目（按 start 去重）。
    """
    channels = root.findall('channel')
    existing_ids = {ch.get('id') for ch in channels if ch.get('id')}

    # 建立原始节目映射，并记录已存在的 (channel, start) 用于去重
    prog_map = {}
    existing_prog_keys = set()
    for prog in root.findall('programme'):
        ch_id = prog.get('channel')
        if ch_id:
            prog_map.setdefault(ch_id, []).append(prog)
            start = prog.get('start')
            existing_prog_keys.add((ch_id, start))

    new_channels = []
    new_progs = []
    added_channels = 0
    added_progs = 0

    for ch in channels:
        cid = ch.get('id')
        if not cid:
            continue

        display_names = [e.text for e in ch.findall('display-name') if e.text]
        num, aliases_id, _ = get_cctv_info(cid, display_names)
        if not aliases_id:
            continue

        progs = prog_map.get(cid, [])
        if not progs:
            continue

        for alias in aliases_id:
            # 如果别名 channel 不存在，则创建
            if alias not in existing_ids:
                new_ch = copy.deepcopy(ch)
                new_ch.set('id', alias)
                new_channels.append(new_ch)
                existing_ids.add(alias)
                added_channels += 1

            # 无论别名是否已存在，都复制节目（按 start 去重）
            for prog in progs:
                start = prog.get('start')
                key = (alias, start)
                if key in existing_prog_keys:
                    continue
                new_prog = copy.deepcopy(prog)
                new_prog.set('channel', alias)
                new_progs.append(new_prog)
                existing_prog_keys.add(key)
                added_progs += 1

    # 将新 channel 插入到第一个 programme 之前，保持 XMLTV 结构整洁
    if new_channels:
        idx = None
        for i, child in enumerate(root):
            if child.tag == 'programme':
                idx = i
                break
        if idx is None:
            root.extend(new_channels)
        else:
            for offset, ch in enumerate(new_channels):
                root.insert(idx + offset, ch)

    root.extend(new_progs)
    print(f"  ✓ 央视 ID 别名: 新增 {added_channels} 个频道, 复制/补充 {added_progs} 条节目")


def add_cctv_display_aliases(root):
    """
    为所有央视频道（包括刚创建的 ID 别名频道）添加丰富的 display-name 别名。
    同时确保频道自身的 id 也作为 display-name，兼容按 tvg-name 匹配的播放器。
    """
    added = 0
    for channel in root.findall('channel'):
        cid = channel.get('id')
        if not cid:
            continue

        existing_names = [e.text for e in channel.findall('display-name') if e.text]
        _, _, aliases_display = get_cctv_info(cid, existing_names)
        if not aliases_display:
            continue

        # 确保自身 id 也作为 display-name
        aliases_display.add(cid)

        for alias in aliases_display:
            if alias and alias not in existing_names:
                new = ET.SubElement(channel, 'display-name')
                new.text = alias
                new.set('lang', 'zh')
                existing_names.append(alias)
                added += 1

    if added:
        print(f"  ✓ 央视 display-name 别名: 添加 {added} 个")


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

    # 1. 央视 ID 别名 + 节目复制（关键修复）
    add_cctv_id_aliases(root)

    # 2. 央视 display-name 别名增强
    add_cctv_display_aliases(root)

    # 3. 自定义映射（保留原功能）
    for channel in root.findall('channel'):
        existing_names = [e.text for e in channel.findall('display-name') if e.text]
        cid = channel.get('id')
        for key, alias in CUSTOM_ALIAS_MAP.items():
            if cid == key or key in existing_names:
                if alias not in existing_names:
                    new = ET.SubElement(channel, 'display-name')
                    new.text = alias
                    new.set('lang', 'zh')
                    print(f"✓ 自定义映射: {key} -> {alias}")
                    existing_names.append(alias)

    # 4. 添加生成时间戳，确保每次内容不同
    root.set('generated', datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    try:
        tree = ET.ElementTree(root)
        tree.write(output_file, encoding='utf-8', xml_declaration=True)
        if os.path.exists(output_file):
            size = os.path.getsize(output_file)
            print(f"✅ 已生成: {output_file} (大小: {size} 字节)")
            print(f"   绝对路径: {os.path.abspath(output_file)}")
        else:
            print(f"❌ 写入失败，文件 {output_file} 不存在！")
            sys.exit(1)
    except Exception as e:
        print(f"❌ 写入文件时出错: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
