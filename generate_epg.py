#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import xml.etree.ElementTree as ET
import requests
import sys
import re
import gzip
import io
import os

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


def add_cctv_aliases(channel, num):
    existing = [elem.text for elem in channel.findall('display-name') if elem.text]
    variants = [
        f"CCTV{num}", f"CCTV-{num}",
        f"CCTV{num}综合", f"CCTV-{num}综合",
        f"CCTV{num} 综合", f"CCTV-{num} 综合",
        f"CCTV{num}高清", f"CCTV-{num}高清",
        f"CCTV{num} 高清", f"CCTV-{num} 高清",
        f"CCTV{num}HD", f"CCTV-{num}HD",
        f"CCTV{num} HD", f"CCTV-{num} HD",
    ]
    added = 0
    for alias in variants:
        if alias not in existing:
            new = ET.SubElement(channel, 'display-name')
            new.text = alias
            new.set('lang', 'zh')
            existing.append(alias)
            added += 1
    if added:
        print(f"  ✓ 为 CCTV{num} 添加了 {added} 个别名")


def add_aliases(root):
    for channel in root.findall('channel'):
        existing_names = [elem.text for elem in channel.findall('display-name') if elem.text]
        cid = channel.get('id')

        for key, alias in CUSTOM_ALIAS_MAP.items():
            if cid == key or key in existing_names:
                if alias not in existing_names:
                    new = ET.SubElement(channel, 'display-name')
                    new.text = alias
                    new.set('lang', 'zh')
                    print(f"✓ 自定义映射: {key} -> {alias}")
                    existing_names.append(alias)

        if cid and re.match(r'^CCTV-?\d+$', cid, re.IGNORECASE):
            num = re.search(r'\d+', cid).group()
            add_cctv_aliases(channel, num)
            continue

        for display in channel.findall('display-name'):
            name = display.text
            if name:
                m = re.match(r'^CCTV-?(\d+)', name, re.IGNORECASE)
                if m:
                    num = m.group(1)
                    add_cctv_aliases(channel, num)
                    break


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
    add_aliases(root)

    # 写入文件（强制覆盖）
    try:
        tree = ET.ElementTree(root)
        tree.write(output_file, encoding='utf-8', xml_declaration=True)
        # 检查文件是否真的存在
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
