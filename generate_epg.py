#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import xml.etree.ElementTree as ET
import requests
import sys
import re

# ---------- 配置 ----------
EPG_URL = "https://proxy.lalifeier.eu.org/https://raw.githubusercontent.com/5iClub/CN.EPG/main/epg.xml"

# 自定义映射（用于卫视频道或其他非央视频道）
# 格式：'EPG中的标识' : '直播源中的名称'
CUSTOM_ALIAS_MAP = {
    # 示例（请根据实际直播源取消注释并修改）：
    # "HUNAN": "湖南卫视",
    # "DRAGONTV": "东方卫视",
    # "BTV1": "北京卫视",
    # "ZJTV": "浙江卫视",
    # "JSTV": "江苏卫视",
}
# -----------------------------------------------

def fetch_epg(url):
    try:
        response = requests.get(url, timeout=30)
        response.encoding = 'utf-8'
        return response.text
    except Exception as e:
        print(f"❌ 获取EPG失败: {e}")
        sys.exit(1)

def add_cctv_aliases(channel, num):
    """
    为央视频道添加所有常见别名变体
    """
    existing = [elem.text for elem in channel.findall('display-name') if elem.text]
    # 生成所有变体
    variants = [
        f"CCTV{num}",
        f"CCTV-{num}",
        f"CCTV{num}综合",
        f"CCTV-{num}综合",
        f"CCTV{num}高清",
        f"CCTV-{num}高清",
        f"CCTV{num}HD",
        f"CCTV-{num}HD",
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

        # 1. 自定义映射（非央视频道）
        for key, alias in CUSTOM_ALIAS_MAP.items():
            if cid == key or key in existing_names:
                if alias not in existing_names:
                    new = ET.SubElement(channel, 'display-name')
                    new.text = alias
                    new.set('lang', 'zh')
                    print(f"✓ 自定义映射: {key} -> {alias}")
                    existing_names.append(alias)

        # 2. 自动为央视频道生成所有变体
        # 检查 channel id 是否匹配 CCTV数字
        if cid and re.match(r'^CCTV\d+$', cid, re.IGNORECASE):
            num = re.search(r'\d+', cid).group()
            add_cctv_aliases(channel, num)
            continue  # 避免重复检查 display-name

        # 检查 display-name 是否包含 CCTV数字
        found = False
        for display in channel.findall('display-name'):
            name = display.text
            if name:
                m = re.match(r'^CCTV(\d+)', name, re.IGNORECASE)
                if m:
                    num = m.group(1)
                    add_cctv_aliases(channel, num)
                    found = True
                    break
        if found:
            continue

def main():
    output_file = sys.argv[1] if len(sys.argv) > 1 else "epg.xml"
    print(f"📡 获取EPG: {EPG_URL}")
    xml_content = fetch_epg(EPG_URL)

    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        print(f"❌ XML解析失败: {e}")
        sys.exit(1)

    print(f"📺 原始频道数: {len(root.findall('channel'))}")
    add_aliases(root)

    tree = ET.ElementTree(root)
    tree.write(output_file, encoding='utf-8', xml_declaration=True)
    print(f"✅ 已生成: {output_file}")

if __name__ == "__main__":
    main()
