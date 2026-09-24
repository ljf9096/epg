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

CCTV_NAME_MAP = {
    "1": "综合", "2": "财经", "3": "综艺", "4": "中文国际",
    "5": "体育", "6": "电影", "7": "国防军事", "8": "电视剧",
    "9": "纪录", "10": "科教", "11": "戏曲", "12": "社会与法",
    "13": "新闻", "14": "少儿", "15": "音乐", "16": "奥林匹克",
    "17": "农业农村"
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


def get_cctv_number(channel_id, display_names):
    """从频道 id 或 display-name 中提取央视编号。"""
    candidates = [channel_id] + list(display_names)
    for text in candidates:
        if not text:
            continue
        m = re.search(r'CCTV[-\s]?(\d+\+?|[48]K|\d+)', text, re.IGNORECASE)
        if m:
            return m.group(1).upper()
    return None


def get_cctv_aliases(num):
    """
    为给定的央视编号生成所有可能的 id 别名。
    覆盖：CCTV1、CCTV-1、CCTV1综合、CCTV-1综合、CCTV1-综合、CCTV-1-综合、
          CCTV1高清、CCTV-1高清、CCTV1HD、CCTV-1HD、CCTV1 综合、CCTV-1 综合 等。
    """
    aliases = set()

    # 基础形式
    for p in ["CCTV", "cctv"]:
        aliases.add(f"{p}{num}")
        aliases.add(f"{p}-{num}")

    if num.isdigit():
        name = CCTV_NAME_MAP.get(num, "")
        suffixes = []
        if name:
            suffixes.append(name)
        suffixes += ["综合", "高清", "HD"]

        for p in ["CCTV", "cctv"]:
            for s in suffixes:
                aliases.add(f"{p}{num}{s}")
                aliases.add(f"{p}-{num}{s}")
                aliases.add(f"{p}{num}-{s}")
                aliases.add(f"{p}-{num}-{s}")
                aliases.add(f"{p}{num} {s}")
                aliases.add(f"{p}-{num} {s}")

        # 综合高清组合
        for p in ["CCTV", "cctv"]:
            aliases.add(f"{p}{num}综合高清")
            aliases.add(f"{p}-{num}综合高清")

    elif num == "5+":
        for p in ["CCTV", "cctv"]:
            for s in ["", "体育", "体育赛事", "高清", "HD"]:
                aliases.add(f"{p}5+{s}")
                aliases.add(f"{p}-5+{s}")

    elif num in ("4K", "8K"):
        for p in ["CCTV", "cctv"]:
            for s in ["", "超高清", "高清", "HD"]:
                aliases.add(f"{p}{num}{s}")
                aliases.add(f"{p}-{num}{s}")

    return aliases


def process_cctv(root):
    """处理所有央视频道：为每个编号生成完整的别名频道集合，并统一节目。"""
    # 1. 构建 id -> 节目列表 的映射
    prog_map = {}
    for prog in root.findall('programme'):
        cid = prog.get('channel')
        if cid:
            prog_map.setdefault(cid, []).append(prog)

    # 2. 按央视编号分组
    groups = {}
    for ch in root.findall('channel'):
        cid = ch.get('id')
        if not cid:
            continue
        dns = [e.text for e in ch.findall('display-name') if e.text]
        num = get_cctv_number(cid, dns)
        if num:
            groups.setdefault(num, []).append({
                'ch': ch, 'id': cid, 'dns': dns,
                'progs': prog_map.get(cid, []),
            })

    if not groups:
        print("  · 未发现央视频道")
        return

    # 3. 收集所有央视相关 id，删除它们的旧节目
    cctv_ids = set()
    for num, items in groups.items():
        cctv_ids |= get_cctv_aliases(num)
        for item in items:
            cctv_ids.add(item['id'])

    removed = 0
    for prog in list(root.findall('programme')):
        if prog.get('channel') in cctv_ids:
            root.remove(prog)
            removed += 1

    # 4. 现有频道索引
    existing = {}
    for ch in root.findall('channel'):
        cid = ch.get('id')
        if cid:
            existing[cid] = ch

    new_channels = []
    new_progs = []

    # 5. 为每个央视编号构建完整的别名频道集合
    for num, items in sorted(groups.items()):
        # 选取该组中节目最多的作为规范源
        canon_progs = max((it['progs'] for it in items), key=len)

        # 所有别名 id
        aliases = get_cctv_aliases(num)
        for item in items:
            aliases.add(item['id'])
        aliases.discard('')

        for alias in sorted(aliases):
            if alias not in existing:
                # 新建频道：只放 id 作为 display-name（放在第一位）
                ch = ET.Element('channel')
                ch.set('id', alias)
                dn = ET.SubElement(ch, 'display-name')
                dn.text = alias
                dn.set('lang', 'zh')
                new_channels.append(ch)
                existing[alias] = ch
            else:
                # 已有频道：确保第一个 display-name == id
                ch = existing[alias]
                dns = ch.findall('display-name')
                if not dns or (dns[0].text or "") != alias:
                    # 移除已有的同名 display-name 避免重复
                    for dn in dns[:]:
                        if (dn.text or "") == alias:
                            ch.remove(dn)
                    new_dn = ET.Element('display-name')
                    new_dn.text = alias
                    new_dn.set('lang', 'zh')
                    ch.insert(0, new_dn)

            # 复制规范源的节目
            for prog in canon_progs:
                np = copy.deepcopy(prog)
                np.set('channel', alias)
                new_progs.append(np)

    # 6. 把新频道插入到第一个 programme 之前
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

    print(f"  ✓ 央视处理: {len(groups)} 个编号组, "
          f"新增 {len(new_channels)} 个频道, "
          f"删除旧节目 {removed} 条, "
          f"写入 {len(new_progs)} 条节目")


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

    # 处理央视
    process_cctv(root)

    # 自定义映射
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

    # 时间戳
    root.set('generated', datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    try:
        tree = ET.ElementTree(root)
        tree.write(output_file, encoding='utf-8', xml_declaration=True)
        if os.path.exists(output_file):
            size = os.path.getsize(output_file)
            print(f"✅ 已生成: {output_file} (大小: {size} 字节)")
            print(f"   绝对路径: {os.path.abspath(output_file)}")
        else:
            print(f"❌ 写入失败，文件不存在")
            sys.exit(1)
    except Exception as e:
        print(f"❌ 写入文件时出错: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
