#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EPG 生成脚本 - 修复 OK影视 匹配问题
策略：
  1) 为每个 CCTV 编号挑选规范源，生成完整的节目数据
  2) 把所有可能出现的变体（CCTV1 / CCTV-1 / CCTV1综合 / CCTV1-综合 / ...）
     作为独立的 <channel> 创建，每个都带完整节目
  3) 同时把这些变体也作为 display-name 附加到每个频道上
     → 无论 OK影视 是按 id 匹配还是按 display-name 匹配，都能命中
  4) 每个 <channel> 的第一个 display-name 严格等于它的 id
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


def get_cctv_number(text):
    """从任意字符串里提取央视编号，如 '1'、'5+'、'4K'。"""
    if not text:
        return None
    m = re.search(r'CCTV[-\s]?(\d+\+?|[48]K|\d+)', text, re.IGNORECASE)
    return m.group(1).upper() if m else None


def gen_all_aliases(num):
    """
    为给定央视编号生成所有可能出现的字符串变体。
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


def process_cctv(root):
    """
    处理所有央视频道：
      1) 按编号分组，选出规范节目源
      2) 为该编号下所有变体（id 别名）创建/更新 <channel>，各带完整节目
      3) 在每个频道上把该编号的所有变体都作为 display-name 附加上去
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
        all_cctv_ids |= gen_all_aliases(num)
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

    # --------- 逐个央视编号处理 ---------
    for num, items in sorted(groups.items()):
        # 规范节目源 = 节目最多的那个
        canon_progs = max((it['progs'] for it in items), key=len) if items else []

        # 该编号下所有可能的字符串（id 别名）
        aliases = gen_all_aliases(num)
        for item in items:
            aliases.add(item['id'])
        aliases.discard('')

        # 保证有一个"主 id"排在最前面（最短的）
        main_id = sorted(aliases, key=lambda s: (len(s), s))[0]

        for alias in sorted(aliases):
            ch = existing.get(alias)
            if ch is None:
                # 新频道
                ch = ET.Element('channel')
                ch.set('id', alias)
                # 第一个 display-name = id
                first_dn = ET.SubElement(ch, 'display-name')
                first_dn.text = alias
                first_dn.set('lang', 'zh')
                # 附加其它变体作为 display-name
                for s in sorted(aliases):
                    if s != alias:
                        dn = ET.SubElement(ch, 'display-name')
                        dn.text = s
                        dn.set('lang', 'zh')
                new_channels.append(ch)
                existing[alias] = ch
            else:
                # 已有频道：确保第一个 display-name = id
                dns = ch.findall('display-name')
                if not dns or (dns[0].text or "") != alias:
                    for d in dns[:]:
                        if (d.text or "") == alias:
                            ch.remove(d)
                    new_dn = ET.Element('display-name')
                    new_dn.text = alias
                    new_dn.set('lang', 'zh')
                    ch.insert(0, new_dn)

            # 复制规范节目到该别名
            for prog in canon_progs:
                np = copy.deepcopy(prog)
                np.set('channel', alias)
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
