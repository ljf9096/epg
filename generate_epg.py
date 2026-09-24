#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EPG + M3U 整合生成脚本（OK影视向）

功能：
  1) 拉取 EPG 源，解析成 ElementTree
  2) 归一化 M3U 里的 tvg-id → 规范ID（CCTV-1 / HunanTV ...）
     - 读取 --m3u 指定的播放列表（不指定则跳过）
     - 写回 --m3u-out（默认在原名后加 .norm）
  3) 处理央视：变体建独立 channel，节目复用（兜底）
     - 同时只保留规范ID频道，其余变体channel删掉，节目挂在规范ID上
  4) 处理卫视：同上
  5) 写出最终 epg.xml

用法：
  python generate_epg.py epg.xml --m3u iptv.m3u --m3u-out iptv.norm.m3u
  python generate_epg.py epg.xml                # 只生成EPG
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
import argparse
from collections import defaultdict

# ---------- 配置 ----------
EPG_SOURCES = [
    "https://live.fanmingming.cn/e.xml",
    "https://epg.112114.xyz/pp.xml",
    "https://gitee.com/taksssss/tv/raw/main/epg/51zmt.xml.gz",
    "https://gitee.com/taksssss/tv/raw/main/epg/51zmte1.xml.gz",
    "https://gitee.com/taksssss/tv/raw/main/epg/51zmte2.xml.gz",
    "https://raw.githubusercontent.com/CCSH/IPTV/refs/heads/main/e.xml",
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
    "东南卫视": "FujianTV", "福建": "FujianTV",
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
}

CCTV_NAME_MAP = {
    "1": "综合", "2": "财经", "3": "综艺", "4": "中文国际",
    "5": "体育", "6": "电影", "7": "国防军事", "8": "电视剧",
    "9": "纪录", "10": "科教", "11": "戏曲", "12": "社会与法",
    "13": "新闻", "14": "少儿", "15": "音乐", "16": "奥林匹克",
    "17": "农业农村",
}


# ==================== EPG 拉取 ====================

def fetch_epg(sources):
    for url in sources:
        try:
            print("拉取:", url[:70])
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            c = r.content
            if url.endswith(".gz") or c[:2] == b"\x1f\x8b":
                c = gzip.GzipFile(fileobj=io.BytesIO(c)).read()
            return c.decode("utf-8")
        except Exception as e:
            print("  失败:", e)
    sys.exit("❌ EPG 源全部失败")


# ==================== 归一化 ====================

def norm_cctv(text):
    """任意央视名字 -> 规范ID，如 CCTV-1 / CCTV-5+ / CCTV-4K"""
    if not text:
        return None
    s = text.strip().upper()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[\(\[【].*?[\)\]】]", "", s)
    if ("央视" in s or "中央" in s) and ("综合" in s or "一套" in s):
        return "CCTV-1"
    m = re.search(r"CCTV-?0*(\d{1,2}|\d+\+?|4K|8K)", s)
    if not m:
        return None
    num = m.group(1)
    if num.isdigit():
        num = str(int(num))
    return f"CCTV-{num}"


def province_canon(name):
    """卫视频道名 -> 规范ID"""
    if not name:
        return None
    if name in PROVINCE_TV_MAP:
        return PROVINCE_TV_MAP[name]
    for k, v in PROVINCE_TV_MAP.items():
        if k in name:
            return v
    return None


def variants(num):
    """生成某个央视编号的所有常见变体"""
    name = CCTV_NAME_MAP.get(num, "")
    pres = ["CCTV", "CCTV-", "cctv", "cctv-"]
    sufs = ["", "综合", "高清", "HD", "超高清", name]
    out = set()
    for p in pres:
        for s in sufs:
            out.add(f"{p}{num}{s}")
            if s:
                out.add(f"{p}{num}-{s}")
                out.add(f"{p}{num} {s}")
    if num == "1":
        out.update(["CCTV综合", "CCTV-综合", "央视综合", "中央一台", "中央电视台综合频道"])
    if num == "5+":
        out.update(["CCTV5+", "CCTV-5+", "CCTV5加", "CCTV体育赛事"])
    if num in ("4K", "8K"):
        out.update([f"CCTV{num}", f"CCTV-{num}", f"CCTV{num}超高清"])
    out.discard("")
    return out


# ==================== EPG 处理 ====================

def _insert_channels(root, new_chs):
    """把新 channel 插到第一个 programme 之前"""
    if not new_chs:
        return
    idx = len(root)
    for i, child in enumerate(root):
        if child.tag == "programme":
            idx = i
            break
    for off, ch in enumerate(new_chs):
        root.insert(idx + off, ch)


def process_cctv(root):
    """
    央视处理（兜底策略）：
      - 选节目最多的原频道作为节目源
      - 为“规范ID + 所有变体”各建一个 channel
      - 每个 channel 都挂同一份完整节目
    这样无论 M3U 的 tvg-id 是 CCTV1 / CCTV-1 / CCTV1-综合 都能中
    """
    prog_map = defaultdict(list)
    for p in root.findall("programme"):
        prog_map[p.get("channel")].append(p)

    # 收集每个编号对应的所有原始 channel 与节目
    num_info = defaultdict(lambda: {"progs": [], "ids": set()})
    for ch in root.findall("channel"):
        cid = ch.get("id")
        num = norm_cctv(cid) or next(
            (norm_cctv(d.text) for d in ch.findall("display-name") if d.text), None)
        if not num:
            continue
        num_info[num]["ids"].add(cid)
        num_info[num]["progs"] += prog_map.get(cid, [])

    if not num_info:
        print("· 未发现央视频道")
        return

    # 删掉所有央视相关旧节目
    old_ids = set()
    for info in num_info.values():
        old_ids.update(info["ids"])
        old_ids.update(variants(next(iter(num_info))))  # 占位，下面重算
    old_ids = set()
    for num, info in num_info.items():
        old_ids.update(info["ids"])
        old_ids.update(variants(num))

    for p in list(root.findall("programme")):
        if p.get("channel") in old_ids:
            root.remove(p)

    existing = {c.get("id"): c for c in root.findall("channel")}
    new_chs = []
    new_progs = []
    kept_ids = set()

    for num, info in sorted(num_info.items()):
        canon = f"CCTV-{num}"
        progs = info["progs"]
        all_ids = {canon} | info["ids"] | variants(num)
        kept_ids.update(all_ids)

        for vid in sorted(all_ids):
            ch = existing.get(vid)
            if ch is None:
                ch = ET.Element("channel", {"id": vid})
                new_chs.append(ch)
            else:
                for d in ch.findall("display-name"):
                    ch.remove(d)
            existing[vid] = ch

            dn = ET.SubElement(ch, "display-name")
            dn.text = vid
            dn.set("lang", "zh")
            for a in sorted(all_ids):
                if a == vid:
                    continue
                d = ET.SubElement(ch, "display-name")
                d.text = a
                d.set("lang", "zh")

            for p in progs:
                np = copy.deepcopy(p)
                np.set("channel", vid)
                new_progs.append(np)

    # 删除已经被合并掉的旧央视 channel
    for ch in list(root.findall("channel")):
        if ch.get("id") in old_ids and ch.get("id") not in kept_ids:
            root.remove(ch)

    _insert_channels(root, new_chs)
    root.extend(new_progs)
    print(f"✓ 央视：{len(new_chs)} 个变体频道，{len(new_progs)} 条节目")


def process_province(root):
    """卫视处理：规范ID + 变体 display-name，节目挂规范ID"""
    prog_map = defaultdict(list)
    for p in root.findall("programme"):
        prog_map[p.get("channel")].append(p)

    groups = defaultdict(lambda: {"ids": set(), "progs": []})
    for ch in root.findall("channel"):
        cid = ch.get("id")
        dns = [d.text for d in ch.findall("display-name") if d.text]
        canon = province_canon(cid) or next((province_canon(d) for d in dns), None)
        if not canon:
            continue
        groups[canon]["ids"].add(cid)
        groups[canon]["ids"].update(dns)
        groups[canon]["progs"] += prog_map.get(cid, [])

    if not groups:
        print("· 未发现卫视频道")
        return

    old = set()
    for g in groups.values():
        old.update(g["ids"])
    for p in list(root.findall("programme")):
        if p.get("channel") in old:
            root.remove(p)

    existing = {c.get("id"): c for c in root.findall("channel")}
    new_chs = []
    new_progs = []

    for canon, g in sorted(groups.items()):
        ch = existing.get(canon)
        if ch is None:
            ch = ET.Element("channel", {"id": canon})
            new_chs.append(ch)
            existing[canon] = ch
        else:
            for d in ch.findall("display-name"):
                ch.remove(d)

        dn = ET.SubElement(ch, "display-name")
        dn.text = canon
        dn.set("lang", "zh")
        for a in sorted(g["ids"]):
            if a == canon:
                continue
            d = ET.SubElement(ch, "display-name")
            d.text = a
            d.set("lang", "zh")

        for p in g["progs"]:
            np = copy.deepcopy(p)
            np.set("channel", canon)
            new_progs.append(np)

    _insert_channels(root, new_chs)
    root.extend(new_progs)
    print(f"✓ 卫视：{len(new_chs)} 个规范频道，{len(new_progs)} 条节目")


# ==================== M3U 归一化 ====================

def normalize_m3u(in_path, out_path):
    """
    读取 M3U，把 tvg-id 归一化：
      CCTV1 / CCTV 1 / cctv01 / CCTV1-综合  ->  CCTV-1
      湖南卫视HD / 芒果台                    ->  HunanTV
    写回 out_path
    """
    if not os.path.exists(in_path):
        print(f"· M3U 不存在，跳过: {in_path}")
        return

    lines = open(in_path, encoding="utf-8", errors="ignore").read().splitlines()
    out = []
    changed = 0
    for line in lines:
        if line.startswith("#EXTINF"):
            # 取频道名（逗号后最后一段）
            m = re.search(r',([^,]*)$', line)
            name = m.group(1).strip() if m else ""

            cid = norm_cctv(name) or province_canon(name) or ""
            if cid:
                if 'tvg-id="' in line:
                    new_line = re.sub(r'tvg-id="[^"]*"', f'tvg-id="{cid}"', line)
                else:
                    new_line = line.replace("#EXTINF:-1", f'#EXTINF:-1 tvg-id="{cid}"', 1)
                if new_line != line:
                    changed += 1
                line = new_line
        out.append(line)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"✓ M3U 归一化完成：{changed} 行 tvg-id 已修正 → {out_path}")


# ==================== 主流程 ====================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("epg_out", nargs="?", default="epg.xml", help="输出EPG文件")
    ap.add_argument("--m3u", help="输入 M3U 文件（可选）")
    ap.add_argument("--m3u-out", help="归一化后 M3U 输出（默认自动命名）")
    args = ap.parse_args()

    # 1) 归一化 M3U（先做，让 tvg-id 对得上 EPG）
    if args.m3u:
        m3u_out = args.m3u_out or (os.path.splitext(args.m3u)[0] + ".norm.m3u")
        normalize_m3u(args.m3u, m3u_out)

    # 2) 拉取并处理 EPG
    print("📡 拉取EPG...")
    root = ET.fromstring(fetch_epg(EPG_SOURCES))
    print(f"📺 原始: {len(root.findall('channel'))} 频道 / "
          f"{len(root.findall('programme'))} 节目")

    process_cctv(root)
    process_province(root)

    root.set("generated", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    ET.ElementTree(root).write(args.epg_out, encoding="utf-8", xml_declaration=True)
    print(f"✅ 生成 {args.epg_out}："
          f"{len(root.findall('channel'))} 频道 / "
          f"{len(root.findall('programme'))} 节目")


if __name__ == "__main__":
    main()
