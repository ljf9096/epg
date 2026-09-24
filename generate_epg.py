#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
终极版：EPG 按 M3U 实际 tvg-id 建 channel
- M3U 里出现过的 id 一定有节目
- 规范ID（CCTV-1）也有节目
OK影视 / TiviMate / OTT Navigator 通吃
"""

import xml.etree.ElementTree as ET
import requests, re, gzip, io, sys, copy, datetime, argparse
from collections import defaultdict

EPG_SOURCES = [
    "https://live.fanmingming.cn/e.xml",
    "https://epg.112114.xyz/pp.xml",
    "https://gitee.com/taksssss/tv/raw/main/epg/51zmt.xml.gz",
    "https://raw.githubusercontent.com/CCSH/IPTV/refs/heads/main/e.xml",
]

CCTV_NAME_MAP = {
    "1":"综合","2":"财经","3":"综艺","4":"中文国际","5":"体育","6":"电影",
    "7":"国防军事","8":"电视剧","9":"纪录","10":"科教","11":"戏曲",
    "12":"社会与法","13":"新闻","14":"少儿","15":"音乐","16":"奥林匹克","17":"农业农村",
}

PROVINCE_TV_MAP = {
    "湖南卫视":"HunanTV","湖南":"HunanTV","芒果台":"HunanTV",
    "浙江卫视":"ZhejiangTV","江苏卫视":"JiangsuTV","东方卫视":"DongfangTV",
    "北京卫视":"BeijingTV","广东卫视":"GuangdongTV","深圳卫视":"ShenzhenTV",
    "山东卫视":"ShandongTV","安徽卫视":"AnhuiTV","四川卫视":"SichuanTV",
    "湖北卫视":"HubeiTV","天津卫视":"TianjinTV","辽宁卫视":"LiaoningTV",
    "河南卫视":"HenanTV","江西卫视":"JiangxiTV","重庆卫视":"ChongqingTV",
    "福建卫视":"FujianTV","东南卫视":"FujianTV","黑龙江卫视":"HeilongjiangTV",
    "河北卫视":"HebeiTV","山西卫视":"ShanxiTV","陕西卫视":"ShaanxiTV",
    "广西卫视":"GuangxiTV","云南卫视":"YunnanTV","贵州卫视":"GuizhouTV",
    "吉林卫视":"JilinTV","甘肃卫视":"GansuTV","内蒙古卫视":"NeimengguTV",
    "新疆卫视":"XinjiangTV","宁夏卫视":"NingxiaTV","青海卫视":"QinghaiTV",
    "西藏卫视":"XizangTV","海南卫视":"HainanTV",
}

def fetch_epg(sources):
    for u in sources:
        try:
            r = requests.get(u, timeout=15)
            c = r.content
            if u.endswith(".gz") or c[:2]==b"\x1f\x8b":
                c = gzip.GzipFile(fileobj=io.BytesIO(c)).read()
            return c.decode("utf-8")
        except Exception as e:
            print("EPG src fail:", e)
    sys.exit("EPG all fail")

def norm_cctv(text):
    if not text: return None
    s = re.sub(r"\s+","",text.upper())
    s = re.sub(r"[\(\[【].*?[\)\]】]","",s)
    if ("央视" in text or "中央" in text) and ("综合" in text or "一套" in text):
        return "CCTV-1"
    m = re.search(r"CCTV-?0*(\d{1,2}|\d+\+?|4K|8K)", s)
    if not m: return None
    n=m.group(1)
    return f"CCTV-{int(n)}" if n.isdigit() else f"CCTV-{n}"

def norm_province(text):
    if not text: return None
    if text in PROVINCE_TV_MAP: return PROVINCE_TV_MAP[text]
    for k,v in PROVINCE_TV_MAP.items():
        if k in text: return v
    return None

def collect_m3u_ids(m3u_path):
    """返回播放器实际会用到的 id 集合"""
    ids=set()
    if not m3u_path or not __import__("os").path.exists(m3u_path):
        return ids
    for line in open(m3u_path,encoding="utf-8",errors="ignore"):
        if line.startswith("#EXTINF"):
            m=re.search(r'tvg-id="([^"]*)"',line)
            if m and m.group(1).strip():
                ids.add(m.group(1).strip())
            m2=re.search(r',([^,]*)$',line)
            if m2:
                ids.add(m2.group(1).strip())
    return ids

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("epg_out",nargs="?",default="epg.xml")
    ap.add_argument("--m3u",default=None)
    args=ap.parse_args()

    root=ET.fromstring(fetch_epg(EPG_SOURCES))

    # 规范ID -> 节目
    prog_map=defaultdict(list)
    for p in root.findall("programme"):
        prog_map[p.get("channel")].append(p)

    canon_progs=defaultdict(list)
    for ch in root.findall("channel"):
        cid=ch.get("id")
        num=norm_cctv(cid) or next((norm_cctv(d.text) for d in ch.findall("display-name") if d.text),None)
        if num:
            ps=prog_map.get(cid,[])
            if len(ps)>len(canon_progs[num]):
                canon_progs[num]=ps
            continue
        pv=norm_province(cid) or next((norm_province(d.text) for d in ch.findall("display-name") if d.text),None)
        if pv:
            ps=prog_map.get(cid,[])
            if len(ps)>len(canon_progs[pv]):
                canon_progs[pv]=ps

    # M3U 实际 id
    m3u_ids=collect_m3u_ids(args.m3u)

    # 要建的 channel：
    # 1) 规范ID CCTV-1 / HunanTV
    # 2) M3U 里出现过的原始 id（如果能归一化出来）
    want=defaultdict(set)  # canon -> {channel ids}
    for cid in m3u_ids:
        c = norm_cctv(cid)
        if c:
            want[c].add(cid)
            want[c].add(c)
        else:
            p = norm_province(cid)
            if p:
                want[p].add(cid)
                want[p].add(p)

    # 再加 EPG 源里本来就有的规范ID
    for c in list(canon_progs):
        want[c].add(c)

    existing={c.get("id"):c for c in root.findall("channel")}
    new_chs=[]
    new_progs=[]

    for canon, ids in want.items():
        progs=canon_progs.get(canon,[])
        if not progs:
            continue
        for vid in sorted(ids):
            ch=existing.get(vid)
            if ch is None:
                ch=ET.Element("channel",{"id":vid})
                new_chs.append(ch)
                existing[vid]=ch
            else:
                for d in ch.findall("display-name"):
                    ch.remove(d)
            dn=ET.SubElement(ch,"display-name")
            dn.text=vid
            dn.set("lang","zh")
            for a in sorted(ids):
                if a==vid: continue
                d=ET.SubElement(ch,"display-name")
                d.text=a
            for p in progs:
                np=copy.deepcopy(p)
                np.set("channel",vid)
                new_progs.append(np)

    # 删掉没被保留的央视/卫视旧 channel（避免重复）
    keep=set(existing.keys())
    for ch in list(root.findall("channel")):
        cid=ch.get("id")
        if (norm_cctv(cid) or norm_province(cid)) and cid not in keep:
            root.remove(ch)

    # 删旧节目
    for p in list(root.findall("programme")):
        pass

    idx=len(root)
    for i,child in enumerate(root):
        if child.tag=="programme":
            idx=i
            break
    for off,ch in enumerate(new_chs):
        root.insert(idx+off,ch)
    root.extend(new_progs)

    root.set("generated",datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    ET.ElementTree(root).write(args.epg_out,encoding="utf-8",xml_declaration=True)
    print("生成",args.epg_out)
    print("M3U id 数:",len(m3u_ids))
    print("建成 channel 数:",len(new_chs))
    print("节目数:",len(new_progs))

if __name__=="__main__":
    main()
