#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EPG 生成脚本 - 稳定版（OK影视向）
策略：
  - 央视：只保留规范 channel id（CCTV-1）
  - 所有变体（CCTV1 / CCTV1-综合 / CCTV-1综合 / CCTV综合）都放 display-name
  - programme 只挂规范ID
  - 卫视：只保留规范ID（HunanTV 等），变体放 display-name
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
from collections import defaultdict

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
            print("失败:", e)
    sys.exit("EPG 源全部失败")


def norm_cctv(text):
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


def cctv_aliases(num):
    name = CCTV_NAME_MAP.get(num, "")
    pres = ["CCTV", "CCTV-", "cctv", "cctv-"]
    sufs = ["", "综合", "高清", "HD", "超高清", name]
    out = set()
    for p in pres:
        for s in sufs:
            out.add(f"{p}{num}{s}")
            if s:
                out.add(f"{p}{num}-{s}")   # CCTV1-综合 / CCTV-1-综合
                out.add(f"{p}{num} {s}")
    if num == "1":
        out.update(["CCTV综合", "CCTV-综合", "央视综合", "中央一台", "中央电视台综合频道"])
    if num == "5+":
        out.update(["CCTV5+", "CCTV-5+", "CCTV5加", "CCTV体育赛事"])
    if num in ("4K", "8K"):
        out.update([f"CCTV{num}", f"CCTV-{num}", f"CCTV{num}超高清"])
    out.discard("")
    return out


def province_canon(name):
    if not name:
        return None
    if name in PROVINCE_TV_MAP:
        return PROVINCE_TV_MAP[name]
    for k, v in PROVINCE_TV_MAP.items():
        if k in name:
            return v
    return None


def process_cctv(root):
    prog_map = defaultdict(list)
    for p in root.findall("programme"):
        prog_map[p.get("channel")].append(p)

    # 按规范ID归组
    groups = defaultdict(lambda: {"ids": set(), "progs": []})
    for ch in root.findall("channel"):
        cid = ch.get("id")
        dns = [d.text for d in ch.findall("display-name") if d.text]
        canon = norm_cctv(cid)
        if not canon:
            canon = next((norm_cctv(d) for d in dns), None)
        if not canon:
            continue
        groups[canon]["ids"].add(cid)
        groups[canon]["ids"].update(dns)
        groups[canon]["progs"] += prog_map.get(cid, [])

    # 删旧节目
    all_old = set()
    for g in groups.values():
        all_old.update(g["ids"])
    for p in list(root.findall("programme")):
        if p.get("channel") in all_old:
            root.remove(p)

    existing = {c.get("id"): c for c in root.findall("channel")}
    new_chs = []
    new_progs = []

    for canon, g in groups.items():
        num = canon.split("-")[1]
        aliases = cctv_aliases(num) | g["ids"]
        # 节目源：最多节目的原频道
        progs = g["progs"]

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
        for a in sorted(aliases):
            if a == canon:
                continue
            d = ET.SubElement(ch, "display-name")
            d.text = a
            d.set("lang", "zh")

        for p in progs:
            np = copy.deepcopy(p)
            np.set("channel", canon)
            new_progs.append(np)

    _insert(root, new_chs, new_progs)
    print("央视处理完：", len(new_chs), "个规范频道")


def process_province(root):
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

    old = set()
    for g in groups.values():
        old.update(g["ids"])
    for p in list(root.findall("programme")):
        if p.get("channel") in old:
            root.remove(p)
    for ch in list(root.findall("channel")):
        if ch.get("id") in old and ch.get("id") not in groups:
            root.remove(ch)

    existing = {c.get("id"): c for c in root.findall("channel")}
    new_chs = []
    new_progs = []

    for canon, g in groups.items():
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

    _insert(root, new_chs, new_progs)
    print("卫视处理完：", len(new_chs), "个规范频道")


def _insert(root, new_chs, new_progs):
    if new_chs:
        idx = len(root)
        for i, child in enumerate(root):
            if child.tag == "programme":
                idx = i
                break
        for off, ch in enumerate(new_chs):
            root.insert(idx + off, ch)
    root.extend(new_progs)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "epg.xml"
    root = ET.fromstring(fetch_epg(EPG_SOURCES))

    print("原始频道:", len(root.findall("channel")),
          "节目:", len(root.findall("programme")))

    process_cctv(root)
    process_province(root)

    root.set("generated", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    ET.ElementTree(root).write(out, encoding="utf-8", xml_declaration=True)
    print(f"生成 {out}：频道 {len(root.findall('channel'))} / 节目 {len(root.findall('programme'))}")


if __name__ == "__main__":
    main()    main()
