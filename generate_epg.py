#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import xml.etree.ElementTree as ET
import requests
import sys
import re

# ---------- 配置 ----------
EPG_URL = "https://proxy.lalifeier.eu.org/https://raw.githubusercontent.com/5iClub/CN.EPG/main/epg.xml"

# 自定义映射（除央视外，如卫视），格式：EPG中的名称 -> 需要添加的显示名
CUSTOM_ALIAS_MAP = {
    # 卫视频道示例（根据实际情况增删）
    # "HUNAN": "湖南卫视",
    # "DRAGONTV": "东方卫视",
    # "BTV1": "北京卫视",
    # "ZJTV": "浙江卫视",
}

# 是否自动为所有CCTV频道生成带横杠别名（推荐开启）
AUTO_CCTV_ALIAS = True
# -------------------------

def fetch_epg(url):
    try:
        response = requests.get(url, timeout=30)
        response.encoding = 'utf-8'
        return response.text
    except Exception as e:
        print(f"❌ 获取EPG失败: {e}")
        sys.exit(1)

def add_aliases(root, custom_map, auto_cctv):
    # 收集所有已存在的 display-name，避免重复添加
    for channel in root.findall('channel'):
        existing_names = [elem.text for elem in channel.findall('display-name') if elem.text]
        cid = channel.get('id')

        # 1. 自定义映射（手动添加）
        for key, alias in custom_map.items():
            if cid == key or key in existing_names:
                if alias not in existing_names:
                    new = ET.SubElement(channel, 'display-name')
                    new.text = alias
                    new.set('lang', 'zh')
                    print(f"✓ 自定义映射: {key} -> {alias}")

        # 2. 自动为央视生成带横杠别名
        if auto_cctv:
            # 处理每个 display-name
            for display in channel.findall('display-name'):
                name = display.text
                if not name:
                    continue
                # 匹配 "CCTV" 后跟一个或多个数字，可能后接汉字或字母
                m = re.match(r'^(CCTV)(\d+)(.*)$', name, re.IGNORECASE)
                if m:
                    prefix = m.group(1)      # "CCTV"
                    num = m.group(2)         # 数字
                    suffix = m.group(3)      # 后续字符（如"综合"、"财经"或无）
                    # 生成带横杠的别名：CCTV-数字 + 后缀
                    alias = f"CCTV-{num}{suffix}"
                    if alias not in existing_names and alias != name:
                        new = ET.SubElement(channel, 'display-name')
                        new.text = alias
                        new.set('lang', 'zh')
                        print(f"✓ 自动央视别名: {name} -> {alias}")
                        existing_names.append(alias)  # 更新集合避免重复

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
    add_aliases(root, CUSTOM_ALIAS_MAP, AUTO_CCTV_ALIAS)

    tree = ET.ElementTree(root)
    tree.write(output_file, encoding='utf-8', xml_declaration=True)
    print(f"✅ 已生成: {output_file}")

if __name__ == "__main__":
    main()
