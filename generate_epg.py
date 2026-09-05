#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EPG 生成器 - 为 OK 影视添加频道别名兼容性
- 自动为所有 CCTV 频道生成带横杠别名（CCTV-1、CCTV-2...）
- 通过 CUSTOM_ALIAS_MAP 添加直播源实际使用的频道名称（包括后缀）
- 每日定时运行，输出 epg.xml
"""

import xml.etree.ElementTree as ET
import requests
import sys
import re

# ---------- 配置 ----------
EPG_URL = "https://proxy.lalifeier.eu.org/https://raw.githubusercontent.com/5iClub/CN.EPG/main/epg.xml"

# ==================== 核心频道别名映射 ====================
# 格式：'EPG中的标识' : '需要添加的别名'
# EPG中的标识可以是 channel id 或已有的 display-name 文本
# 别名需与您的直播源中的频道名称完全一致（包括空格、标点）
CUSTOM_ALIAS_MAP = {
    # ---------- 央视频道（带后缀，适配直播源常见命名） ----------
    "CCTV1": "CCTV1综合",
    "CCTV2": "CCTV2财经",
    "CCTV3": "CCTV3综艺",
    "CCTV4": "CCTV4中文国际",
    "CCTV5": "CCTV5体育",
    "CCTV6": "CCTV6电影",
    "CCTV7": "CCTV7国防军事",
    "CCTV8": "CCTV8电视剧",
    "CCTV9": "CCTV9纪录",
    "CCTV10": "CCTV10科教",
    "CCTV11": "CCTV11戏曲",
    "CCTV12": "CCTV12社会与法",
    "CCTV13": "CCTV13新闻",
    "CCTV14": "CCTV14少儿",
    "CCTV15": "CCTV15音乐",
    "CCTV16": "CCTV16奥林匹克",
    "CCTV17": "CCTV17农业农村",

    # ---------- 卫视频道（示例，按需添加） ----------
    # 如果您的直播源使用卫视全称，可在此映射
    # 例如 EPG 中为 "HUNAN"，直播源为 "湖南卫视" 则添加：
    # "HUNAN": "湖南卫视",
    # "DRAGONTV": "东方卫视",
    # "BTV1": "北京卫视",
    # "ZJTV": "浙江卫视",
    # "JSTV": "江苏卫视",
    # "SHENZHEN": "深圳卫视",
    # 更多卫视请根据实际情况自行添加
}

# 是否自动为所有 CCTV 频道生成横杠别名（如 CCTV-1、CCTV-2...）
AUTO_CCTV_HYPHEN = True
# ---------------------------------------------------------

def fetch_epg(url):
    try:
        response = requests.get(url, timeout=30)
        response.encoding = 'utf-8'
        return response.text
    except Exception as e:
        print(f"❌ 获取EPG失败: {e}")
        sys.exit(1)

def add_aliases(root, custom_map, auto_hyphen):
    for channel in root.findall('channel'):
        existing_names = [elem.text for elem in channel.findall('display-name') if elem.text]
        cid = channel.get('id')

        # 1. 自定义映射（添加直播源实际频道名）
        for key, alias in custom_map.items():
            # 匹配 channel id 或任意已存在的 display-name
            if cid == key or key in existing_names:
                if alias not in existing_names:
                    new = ET.SubElement(channel, 'display-name')
                    new.text = alias
                    new.set('lang', 'zh')
                    print(f"✓ 自定义映射: {key} -> {alias}")
                    existing_names.append(alias)  # 避免后续重复

        # 2. 自动生成横杠别名（CCTV-数字、CCTV-数字+后缀）
        if auto_hyphen:
            for display in channel.findall('display-name'):
                name = display.text
                if not name:
                    continue
                # 匹配 "CCTV" + 数字 + 任意后缀（可选）
                m = re.match(r'^(CCTV)(\d+)(.*)$', name, re.IGNORECASE)
                if m:
                    num = m.group(2)
                    suffix = m.group(3)          # 如 "综合"、"财经" 或无
                    # 生成横杠版本：CCTV-数字 + 后缀
                    alias = f"CCTV-{num}{suffix}"
                    if alias not in existing_names and alias != name:
                        new = ET.SubElement(channel, 'display-name')
                        new.text = alias
                        new.set('lang', 'zh')
                        print(f"✓ 自动横杠: {name} -> {alias}")
                        existing_names.append(alias)

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
    add_aliases(root, CUSTOM_ALIAS_MAP, AUTO_CCTV_HYPHEN)

    tree = ET.ElementTree(root)
    tree.write(output_file, encoding='utf-8', xml_declaration=True)
    print(f"✅ 已生成: {output_file}")

if __name__ == "__main__":
    main()
