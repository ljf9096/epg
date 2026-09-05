#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import xml.etree.ElementTree as ET
import requests
import sys
import re
import gzip
import io

# ---------- 配置 ----------
# EPG源列表（按优先级排序，首选源失效后自动切换）
EPG_SOURCES = [
    # 1. 5iClub（原首选源）
    "https://proxy.lalifeier.eu.org/https://raw.githubusercontent.com/5iClub/CN.EPG/main/epg.xml",
    # 2. 老张的EPG（51zmt）[reference:0][reference:1]
    "https://gitee.com/taksssss/tv/raw/main/epg/51zmt.xml.gz",
    # 3. 老张的EPG 国内四天版（带节目介绍）[reference:2]
    "https://gitee.com/taksssss/tv/raw/main/epg/51zmte1.xml.gz",
    # 4. 老张的EPG 海外版[reference:3]
    "https://gitee.com/taksssss/tv/raw/main/epg/51zmte2.xml.gz",
    # 5. ERW源[reference:4][reference:5]
    "https://gitee.com/taksssss/tv/raw/main/epg/erw.xml.gz",
    # 6. epg.pw 国内源[reference:6]
    "https://gitee.com/taksssss/tv/raw/main/epg/epgpw_cn.xml.gz",
    # 7. epg.pw 香港源[reference:7]
    "https://gitee.com/taksssss/tv/raw/main/epg/epgpw_hk.xml.gz",
    # 8. epg.pw 台湾源[reference:8]
    "https://gitee.com/taksssss/tv/raw/main/epg/epgpw_tw.xml.gz",
    # 9. CCSH/IPTV 项目EPG
    "https://raw.githubusercontent.com/CCSH/IPTV/refs/heads/main/e.xml",
    # 10. litiande03 EPG[reference:11]
    "https://raw.githubusercontent.com/litiande03/epg/refs/heads/master/pl.xml.gz",
    # 11. Meroser EPG 稳定版
    "https://gitlab.com/Meroser/My-EPG/-/raw/main/tvxml-Meroser.xml.gz",
    # 12. 112114 EPG（经典源）[reference:14][reference:15]
    "https://epg.112114.xyz/pp.xml",
    # 13. fanmingming EPG[reference:16]
    "https://live.fanmingming.cn/e.xml",
]

# 自定义映射（卫视频道等）
CUSTOM_ALIAS_MAP = {
    # "HUNAN": "湖南卫视",
    # "DRAGONTV": "东方卫视",
}
# -----------------------------------------------


def fetch_epg_from_sources(sources):
    """从多个源依次尝试获取EPG数据，成功则返回XML内容"""
    for i, url in enumerate(sources, 1):
        try:
            print(f"  [{i}/{len(sources)}] 尝试: {url[:60]}...")
            response = requests.get(url, timeout=15)
            response.raise_for_status()

            content = response.content

            # 判断是否为gzip压缩格式
            if url.endswith('.gz') or content[:2] == b'\x1f\x8b':
                try:
                    with gzip.GzipFile(fileobj=io.BytesIO(content)) as gz:
                        xml_content = gz.read().decode('utf-8')
                    print(f"  ✓ 成功获取 (gzip压缩格式)")
                    return xml_content
                except Exception as e:
                    print(f"  ✗ gzip解压失败: {e}")
                    continue

            # 普通XML
            xml_content = content.decode('utf-8')
            print(f"  ✓ 成功获取 (XML格式)")
            return xml_content

        except Exception as e:
            print(f"  ✗ 失败: {e}")
            continue

    print(f"❌ 所有EPG源均获取失败")
    sys.exit(1)


def add_cctv_aliases(channel, num):
    """为央视频道添加所有常见别名变体（含空格版本）"""
    existing = [elem.text for elem in channel.findall('display-name') if elem.text]
    variants = [
        f"CCTV{num}",
        f"CCTV-{num}",
        f"CCTV{num}综合",
        f"CCTV-{num}综合",
        f"CCTV{num} 综合",
        f"CCTV-{num} 综合",
        f"CCTV{num}高清",
        f"CCTV-{num}高清",
        f"CCTV{num} 高清",
        f"CCTV-{num} 高清",
        f"CCTV{num}HD",
        f"CCTV-{num}HD",
        f"CCTV{num} HD",
        f"CCTV-{num} HD",
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

        # 1. 自定义映射
        for key, alias in CUSTOM_ALIAS_MAP.items():
            if cid == key or key in existing_names:
                if alias not in existing_names:
                    new = ET.SubElement(channel, 'display-name')
                    new.text = alias
                    new.set('lang', 'zh')
                    print(f"✓ 自定义映射: {key} -> {alias}")
                    existing_names.append(alias)

        # 2. 自动识别央视频道（兼容带横杠）
        if cid and re.match(r'^CCTV-?\d+$', cid, re.IGNORECASE):
            num = re.search(r'\d+', cid).group()
            add_cctv_aliases(channel, num)
            continue

        found = False
        for display in channel.findall('display-name'):
            name = display.text
            if name:
                m = re.match(r'^CCTV-?(\d+)', name, re.IGNORECASE)
                if m:
                    num = m.group(1)
                    add_cctv_aliases(channel, num)
                    found = True
                    break
        if found:
            continue


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

    tree = ET.ElementTree(root)
    tree.write(output_file, encoding='utf-8', xml_declaration=True)
    print(f"✅ 已生成: {output_file}")


if __name__ == "__main__":
    main()
