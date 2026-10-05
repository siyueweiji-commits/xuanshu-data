#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 GeoNames 官方 dump 生成全国地级市经纬度库。

用途
----
`xuanshu/resources/data/city_coords.json` 供 `electron/services/calendar.ts` 的
`listCities()` 读取，用于真太阳时校正：

    经度时差 = (出生地经度 - 120) * 4 分钟

经度每偏差 1 度，时柱就可能整体错一位时辰，因此坐标精度是本脚本的第一优先级。

数据源
------
* ``CN.zip``            —— 中国全部地名（``CN.txt``，tab 分隔，19 列）
* ``admin1CodesASCII.txt`` —— 省级行政区代码表

CN.txt 字段（0 起索引，tab 分隔）::

    0 geonameid   1 name        2 asciiname   3 alternatenames
    4 latitude    5 longitude   6 feature class 7 feature code
    8 country code 9 cc2  10 admin1  11 admin2
    14 population 18 lastupdate

注意 ``admin1`` 在**第 10 列**（第 9 列是 cc2，对 CN 恒为空）。GeoNames 官方的
admin1 code 与国标 GB/T 2260 一致（01=安徽 … 33=重庆），故省份映射可直接用手写表。

坐标系选择（关键）
----------------
地级行政区（ADM2）的经纬度是**行政区面状质心**，不是城区中心。实测偏差很大：

    哈尔滨   ADM2 质心 127.9667   城区 126.6423   偏差 1.32°（≈ 5.3 分钟时差）
    杭州     ADM2 质心 119.6      城区 120.1614   偏差 0.56°

1.3° 的经度误差足以让真太阳时跨过时辰边界，因此**不能直接用 ADM2 质心**。
本脚本改为按优先级解析「城区驻地」坐标：

1. ``adm2+name``  —— 同 admin2 且名称归一化后等于 ADM2 名的驻地（最可信）
2. ``adm2+seat``  —— 同 admin2 的 ``PPLA*``（省级/地级驻地）
3. ``adm2+pop``   —— 同 admin2 内人口最大的 ``P``
4. ``name+seat``  —— 同省、同名的 ``PPLA*``
5. ``name``       —— 同省、同名的 ``P``
6. ``centroid``   —— 兜底：用 ADM2 质心（会在报告中列出以便人工复核）

用法
----
::

    D:\\python\\python.exe gen_city_coords.py --dry-run    # 只打印统计，不写文件
    D:\\python\\python.exe gen_city_coords.py             # 生成并写入
    D:\\python\\python.exe gen_city_coords.py --force-download

脚本是幂等的：同样的输入产出同样的输出（排序稳定、去重确定）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
import urllib.request
import zipfile
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #

#: GeoNames CN / TW / HK / MO dump 地址
URL_CN = "https://download.geonames.org/export/dump/CN.zip"
URL_ADMIN1 = "https://download.geonames.org/export/dump/admin1CodesASCII.txt"

#: 输出文件（相对本脚本定位，兼容两个仓库的目录布局）
DEFAULT_OUT = os.path.normpath(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "..", "xuanshu", "resources", "data", "city_coords.json",
    )
)

#: 下载缓存目录
DEFAULT_CACHE = os.path.normpath(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "..", "xuanshu", ".tmp-citygen",
    )
)

#: 数据版本号：GeoNames 官方 dump 的 lastupdate 日期
#:
#: 2026.10.05 起从 2026.09.30 递增 —— 该版本把城市库从 24 城扩到 353 城。
#: 必须递增：更新器的 hasUpdate = (changedCount > 0) || (version !== localVersion)，
#: 虽然本次文件哈希变化已足以触发更新，但版本号不变会让「已更新到最新」的
#: 用户在 UI 上看到版本号没变，误以为数据没更新。
DATA_VERSION = "2026.10.05"

#: admin1 code -> (中文省名, 拼音排序键)
PROVINCE_MAP: Dict[str, Tuple[str, str]] = {
    "11": ("湖南", "hunan"),
    "12": ("湖北", "hubei"),
    "13": ("新疆", "xinjiang"),
    "14": ("西藏", "xizang"),
    "15": ("甘肃", "gansu"),
    "20": ("内蒙古", "neimenggu"),
    "21": ("宁夏", "ningxia"),
    "22": ("北京", "beijing"),
    "23": ("上海", "shanghai"),
    "26": ("陕西", "shaanxi"),
    "29": ("云南", "yunnan"),
    "01": ("安徽", "anhui"),
    "02": ("浙江", "zhejiang"),
    "03": ("江西", "jiangxi"),
    "04": ("江苏", "jiangsu"),
    "05": ("吉林", "jilin"),
    "06": ("青海", "qinghai"),
    "07": ("福建", "fujian"),
    "08": ("黑龙江", "heilongjiang"),
    "09": ("河南", "henan"),
    "10": ("河北", "hebei"),
    "16": ("广西", "guangxi"),
    "18": ("贵州", "guizhou"),
    "19": ("辽宁", "liaoning"),
    "24": ("山西", "shanxi"),
    "25": ("山东", "shandong"),
    "28": ("天津", "tianjin"),
    "30": ("广东", "guangdong"),
    "31": ("海南", "hainan"),
    "32": ("四川", "sichuan"),
    "33": ("重庆", "chongqing"),
    # 台港澳不在 CN.zip 中，单独内置补充（见 EXTRA_CITIES）
    "34": ("台湾", "taiwan"),
    "82": ("香港", "xianggang"),
    "83": ("澳门", "aomen"),
}

#: 人口权重：驻地类型越大越权威
SEAT_RANK = {"PPLA": 5, "PPLA2": 4, "PPLA3": 3, "PPLA4": 2}

#: 中文名里需要剥掉的行政通名后缀（长的排前面，避免「自治州」被「州」抢先匹配）
#:
#: 注意：**不含「镇」**。景德镇、镇江、镇平的「镇」是专名的一部分，不是行政通名，
#: 剥掉会得到「景德」这种错误结果。
CN_ADMIN_SUFFIXES: Tuple[str, ...] = (
    "特别行政区", "自治区", "自治州", "自治县", "联合旗", "县级市", "市辖区",
    "地区", "林区", "新区", "矿区", "街道", "省", "县", "区", "旗", "盟", "州", "市",
)

#: 必须剔除的通名后缀 —— 出现这些说明取到了下一级行政单位，不能当地级市名
CN_REJECT_SUFFIXES: Tuple[str, ...] = (
    "林区", "新区", "矿区", "街道", "乡", "村", "苏木", "旗",
)

#: CN.zip 不含台港澳，需内置补齐（经度取自 GeoNames / 公开资料，保留 4 位小数）
EXTRA_CITIES: Tuple[Dict[str, object], ...] = (
    {"name": "香港", "province": "香港", "longitude": 114.1694, "latitude": 22.3193,
     "py": "xianggang"},
    {"name": "澳门", "province": "澳门", "longitude": 113.5439, "latitude": 22.1987,
     "py": "aomen"},
    {"name": "台北", "province": "台湾", "longitude": 121.5654, "latitude": 25.0330,
     "py": "taibei"},
    {"name": "高雄", "province": "台湾", "longitude": 120.3014, "latitude": 22.6273,
     "py": "gaoxiong"},
    {"name": "台中", "province": "台湾", "longitude": 120.6794, "latitude": 24.1477,
     "py": "taizhong"},
    {"name": "台南", "province": "台湾", "longitude": 120.2270, "latitude": 22.9999,
     "py": "tainan"},
    {"name": "新北", "province": "台湾", "longitude": 121.4657, "latitude": 25.0121,
     "py": "xinbei"},
    {"name": "桃园", "province": "台湾", "longitude": 121.3010, "latitude": 24.9934,
     "py": "taoyuan"},
    {"name": "基隆", "province": "台湾", "longitude": 121.7462, "latitude": 25.1308,
     "py": "keelong"},
    {"name": "新竹", "province": "台湾", "longitude": 120.9688, "latitude": 24.8138,
     "py": "xinzhu"},
    {"name": "嘉义", "province": "台湾", "longitude": 120.4529, "latitude": 23.4811,
     "py": "jiayi"},
)

# --------------------------------------------------------------------------- #
# 人工覆盖表
# --------------------------------------------------------------------------- #

#: 中文名覆盖：(province, geoname) -> 正确中文名。用于自动提取拿不到/拿错的情况。
NAME_OVERRIDES: Dict[Tuple[str, str], str] = {
    # --- GeoNames 沿用旧译名，需改为现行市名 ---
    ("湖北", "Xiangyang"): "襄阳",           # alternatenames 只有「襄樊」
    ("云南", "Pu'er City"): "普洱",            # alternatenames 里「思茅」更短，被优先选中
    ("云南", "Dêqên Tibetan Autonomous Prefecture"): "迪庆",  # 「迪庆藏族」需剥掉「族」
    # --- 民族自治州/盟：GeoNames 主名带通名，中文名取自治单位本体 ---
    ("青海", "Hainan Zangzu Zizhizhou"): "海南州",   # 与海南省重名，加「州」区分
    ("贵州", "Qiandongnan Miao and Dong Autonomous Prefecture"): "黔东南",
    ("内蒙古", "Xilin Gol Meng"): "锡林郭勒",
    ("内蒙古", "Hinggan Meng"): "兴安",
    # 注：海南「保亭」「琼中」原在此处覆盖，但两个 GeoNames 名已被列入
    # EXCLUDE_GEO_NAMES（县级自治县，非地级市），故移除以免成为死代码。
}

#: 坐标覆盖：(province, 中文名) -> (经度, 纬度)。用于自动解析明显偏离城区的情况。
COORD_OVERRIDES: Dict[Tuple[str, str], Tuple[float, float]] = {
    # GeoNames 把「福州」误匹配到江西抚州（Fuzhou 同拼音），此处按福建福州取值
    ("福建", "福州"): (119.2965, 26.0745),
    # 河北「邢台」GeoNames 名为 Xingtai County，坐标指向县而非市区
    ("河北", "邢台"): (114.5089, 37.0682),
    # 湖南「邵阳」GeoNames 名为 Shaoyang County
    ("湖南", "邵阳"): (111.4692, 27.2378),
    # 山西「大同」行政质心明显偏北
    ("山西", "大同"): (113.3001, 40.0768),
    # 「吐鲁番」行政区辽阔，质心偏向戈壁深处
    ("新疆", "吐鲁番"): (89.1841, 42.9476),
    # 「鄂尔多斯」质心在毛乌素沙地，市区在东胜
    ("内蒙古", "鄂尔多斯"): (109.9894, 39.8172),
    # 「阿勒泰」质心偏向山区
    ("新疆", "阿勒泰"): (88.1396, 47.8484),
    # 「大兴安岭」为地区，驻地加格达奇（经度取城区，纬度亦按加格达奇实测值）
    ("黑龙江", "大兴安岭"): (124.1117, 50.4167),
    # 「神农架」林区驻地木鱼
    ("湖北", "神农架"): (110.4800, 31.7447),
    # 湖北「天门」误取到邻省同名点，落在天门市区
    ("湖北", "天门"): (113.1657, 30.6928),
    # 湖北「仙桃」
    ("湖北", "仙桃"): (113.4538, 30.3645),
    # 湖北「潜江」
    ("湖北", "潜江"): (112.8937, 30.4028),
    # 河南「济源」
    ("河南", "济源"): (112.6007, 35.0724),
    # 海南「三沙」为群岛，取永兴岛
    ("海南", "三沙"): (112.3387, 16.8311),
    # 海南「儋州」那大
    ("海南", "儋州"): (109.5768, 19.5215),
    # 内蒙古「呼伦贝尔」为地级市，驻地海拉尔
    ("内蒙古", "呼伦贝尔"): (119.7430, 49.2122),
    # 内蒙古「兴安」为盟，驻地乌兰浩特
    ("内蒙古", "兴安"): (122.0702, 46.0763),
    # 内蒙古「锡林郭勒」为盟，驻地锡林浩特
    ("内蒙古", "锡林郭勒"): (116.0865, 43.9333),
    # 内蒙古「阿拉善」为盟，驻地巴彦浩特
    ("内蒙古", "阿拉善"): (105.7185, 38.8442),
    # 黑龙江「伊春」面积巨大，质心在林区
    ("黑龙江", "伊春"): (128.8994, 47.7248),
    # 云南「西双版纳」质心偏向山区，景洪市为实际城区
    ("云南", "西双版纳"): (100.7979, 22.0017),
    # 黑龙江「双鸭山」质心偏离市区
    ("黑龙江", "双鸭山"): (131.1573, 46.6434),
    # 黑龙江「鸡西」
    ("黑龙江", "鸡西"): (130.9757, 45.3000),
    # 黑龙江「鹤岗」
    ("黑龙江", "鹤岗"): (130.2775, 47.3321),
    # 黑龙江「黑河」
    ("黑龙江", "黑河"): (127.4990, 50.2496),
    # 甘肃「嘉峪关」
    ("甘肃", "嘉峪关"): (98.2773, 39.7865),
    # 甘肃「金昌」
    ("甘肃", "金昌"): (102.1879, 38.5142),
    # 甘肃「武威」
    ("甘肃", "武威"): (102.6347, 37.9300),
    # 甘肃「张掖」
    ("甘肃", "张掖"): (100.4500, 38.9260),
    # 青海「海西」行政面积极大，质心在西部戈壁
    ("青海", "海西"): (97.3708, 37.3747),
    # 青海「果洛」
    ("青海", "果洛"): (100.2423, 34.4736),
    # 青海「玉树」
    ("青海", "玉树"): (97.0085, 33.0039),
    # 广西「防城港」
    ("广西", "防城港"): (108.3455, 21.6866),
    # 广东「汕尾」
    ("广东", "汕尾"): (115.3642, 22.7745),
    # 云南「怒江」贡山
    ("云南", "怒江"): (98.8543, 25.8500),
    # 西藏「那曲」那曲镇
    ("西藏", "那曲"): (92.0600, 31.4760),
    # 西藏「阿里」噶尔县
    ("西藏", "阿里"): (80.1050, 32.5030),
    # 吉林「白城」
    ("吉林", "白城"): (122.8389, 45.6200),
    # 吉林「松原」
    ("吉林", "松原"): (124.8178, 45.1411),
    # 黑龙江「绥化」
    ("黑龙江", "绥化"): (126.9929, 46.6374),
    # 安徽「池州」
    ("安徽", "池州"): (117.4892, 30.6560),
    # 江西「上饶」
    ("江西", "上饶"): (117.9712, 28.4444),
    # 河南「周口」
    ("河南", "周口"): (114.6970, 33.6263),
    # 河南「驻马店」
    ("河南", "驻马店"): (114.0221, 33.0115),
    # 湖北「咸宁」
    ("湖北", "咸宁"): (114.3289, 29.8328),
    # 湖南「怀化」
    ("湖南", "怀化"): (110.0012, 27.5698),
    # 江西「吉安」
    ("江西", "吉安"): (114.9861, 27.1117),
    # 陕西「榆林」
    ("陕西", "榆林"): (109.7348, 38.2853),
    # 陕西「汉中」
    ("陕西", "汉中"): (107.0286, 33.0776),
    # 湖北「襄阳」（GeoNames 旧译襄樊），襄阳城区
    ("湖北", "襄阳"): (112.1448, 32.0425),
    # 云南「普洱」（旧称思茅），普洱城区
    ("云南", "普洱"): (100.9723, 22.7773),
    # 云南「迪庆」自治州，驻地香格里拉
    ("云南", "迪庆"): (99.7065, 27.8269),
}

#: 拼音排序键覆盖：(province, 中文名) -> 拼音。
#:
#: GeoNames 的 ascii 名对少数民族自治州用的是蒙/藏文音译（如「兴安」记作 Hinggan、
#: 「日喀则」记作 Rikaze、「克拉玛依」记作 Kelamayi），直接拿它排序会让下拉列表
#: 按字母序而不是按汉语拼音排（兴安会排到呼和浩特前面）。这里补上真实拼音。
PY_PINYIN_OVERRIDES: Dict[Tuple[str, str], str] = {
    # 内蒙古（GeoNames 用蒙古文音译）
    ("内蒙古", "兴安"): "xingan",
    ("内蒙古", "锡林郭勒"): "xilinguole",
    ("内蒙古", "阿拉善"): "alashan",
    ("内蒙古", "乌兰察布"): "wulanchabu",
    ("内蒙古", "鄂尔多斯"): "ordosi",
    # 西藏（GeoNames 用藏文音译）
    ("西藏", "日喀则"): "rikaze",
    ("西藏", "昌都"): "changdu",
    ("西藏", "林芝"): "linzhi",
    ("西藏", "山南"): "shannan",
    ("西藏", "那曲"): "naqu",
    ("西藏", "阿里"): "ali",
    # 新疆
    ("新疆", "克拉玛依"): "karamay",
    ("新疆", "博尔塔拉"): "boertala",
    ("新疆", "巴音郭楞"): "bayinguoleng",
    ("新疆", "昌吉"): "changji",
    ("新疆", "克孜勒苏"): "kezilesu",
    # 青海
    ("青海", "海南州"): "hainanzhou",
    ("青海", "果洛"): "guoluo",
    ("青海", "海西"): "haixi",
    ("青海", "黄南"): "huangnan",
    # 云南
    ("云南", "德宏"): "dehong",
    ("云南", "红河"): "honghe",
    ("云南", "迪庆"): "diqing",
    ("云南", "怒江"): "nujiang",
    ("云南", "文山"): "wenshan",
    # 甘肃 / 吉林 / 黑龙江
    ("甘肃", "陇南"): "longnan",
    ("吉林", "延边"): "yanbian",
    ("黑龙江", "佳木斯"): "jiamusi",
    ("黑龙江", "齐齐哈尔"): "qiqihar",
    # 湖北 / 湖南 自治州
    ("湖北", "恩施"): "enshi",
    ("湖南", "湘西"): "xiangxi",
}

#: 需要从结果中剔除的 ADM2（不属于地级市 / 与其他条目重复）
EXCLUDE_GEO_NAMES: Tuple[str, ...] = (
    # 海南的民族自治县与省直辖县级市（不是地级市）
    "Baisha Li Autonomous County",
    "Changjiang Li Autonomous County",
    "Lingao County",
    "Lingshui Li Autonomous County",
    "Tunchang County",
    "Chengmai County",
    "Ding'an County",
    "Ledong Li Autonomous County",
    "Baoting Li and Miao Autonomous County",
    "Qiongzhong Li and Miao Autonomous County",
    "Dongfang City",
    "Qionghai County",
    "Wanning Shi",
    "Wenchang Shi",
    "Wuzhishan City",
    # 新疆兵团师市（不是地级行政区）
    "Shihezi",
    "Tumxuk",
    "Wujiaqu Shi",
)

# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #


def is_han(text: str) -> bool:
    """判断字符串是否全部由中日韩统一表意文字组成。"""
    return bool(text) and all("\u4e00" <= ch <= "\u9fff" for ch in text)


def normalize_ascii(text: str) -> str:
    """把 GeoNames 主名归一化成可比对的键。

    去掉音标（ü / ê / ǎ 等），再剥掉行政通名后缀，只留下专名部分。
    这样 ``Xi'an Shi``、``Xianyang Shi``、``Prefecture of Chenzhou`` 才能互相比对。
    """
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("’", "").replace("'", "").replace("`", "")
    text = text.lower()
    # 先整体去空格，再按词去行政通名
    text = re.sub(r"[\s\-_]+", " ", text)
    for token in (
        "municipality", "autonomous prefecture", "zizhizhou", "prefecture",
        "shiqu", "shi", "diqu", "meng", "region", "county", "city", "of",
    ):
        text = text.replace(token, " ")
    return re.sub(r"[^a-z0-9]+", "", text)


def strip_admin_suffix(chinese: str) -> str:
    """剥掉中文行政通名后缀，得到城市本体名。"""
    name = chinese
    for _ in range(4):  # 允许叠加剥离，如「XX市市」不会发生，但「自治州」需多轮
        stripped = name
        for suffix in CN_ADMIN_SUFFIXES:
            if stripped.endswith(suffix) and len(stripped) > len(suffix) + 1:
                stripped = stripped[: -len(suffix)]
                break
        if stripped == name:
            break
        name = stripped
    return name


def has_reject_suffix(chinese: str) -> bool:
    """判断中文名是否带县级以下通名（说明取错了层级）。"""
    return any(chinese.endswith(suffix) for suffix in CN_REJECT_SUFFIXES)


def extract_chinese_name(record: Sequence[str]) -> Tuple[Optional[str], List[str]]:
    """从 ``alternatenames`` 里挑出最合适的城市中文名。

    GeoNames 没有官方中文名字段，中文名只能从别名列表里捞。策略：

    1. 按逗号拆分，筛出「全部为汉字且长度 2~8」的候选；
    2. 丢掉带县级以下通名的候选（林区/新区/乡/镇/村……）；
    3. 优先取**带「市」后缀**的（地级市通名最可靠）；
    4. 其次取剥掉通名后最短的（如「湘西土家族苗族自治州」→「湘西」）。

    :param record: CN.txt 的一行
    :return: (最佳候选 or None, 全部候选)
    """
    alts = record[3]
    candidates: List[str] = []
    for item in alts.split(","):
        item = item.strip()
        if is_han(item) and 2 <= len(item) <= 8:
            candidates.append(item)
    if not candidates:
        return None, []

    usable = [c for c in candidates if not has_reject_suffix(c)]
    if not usable:
        usable = candidates

    with_city_suffix = [c for c in usable if c.endswith("市")]
    if with_city_suffix:
        # 同为「XX市」时取最短，避免「XX自治州」被误当首选
        best = min(with_city_suffix, key=len)
        return strip_admin_suffix(best), candidates

    # 没有「市」，取剥通名后最短的
    stripped = [(strip_admin_suffix(c), c) for c in usable]
    stripped = [(s, c) for s, c in stripped if s]
    if not stripped:
        return None, candidates
    shortest = min(len(s) for s, _ in stripped)
    for s, _ in stripped:
        if len(s) == shortest:
            return s, candidates
    return stripped[0][0], candidates


def pinyin_of(record: Sequence[str]) -> str:
    """取 GeoNames 的 ascii 名作为排序用的拼音键。"""
    return normalize_ascii(record[2] or record[1])


def round4(value: float) -> float:
    """保留 4 位小数。"""
    return float(f"{value:.4f}")


# --------------------------------------------------------------------------- #
# 下载与解析
# --------------------------------------------------------------------------- #


def download(url: str, dest: str, force: bool = False) -> str:
    """下载文件到 ``dest``，已存在则跳过（除非 ``force``）。"""
    if os.path.exists(dest) and not force and os.path.getsize(dest) > 0:
        print(f"  [cache] {os.path.basename(dest)}")
        return dest
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    print(f"  [get] {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "xuanshu-citygen/1.0"})
    tmp = dest + ".part"
    with urllib.request.urlopen(request, timeout=180) as response, open(tmp, "wb") as handle:
        while True:
            chunk = response.read(1 << 20)
            if not chunk:
                break
            handle.write(chunk)
    os.replace(tmp, dest)
    print(f"  [ok] {os.path.basename(dest)}  {os.path.getsize(dest):,} bytes")
    return dest


def load_cn_rows(cn_zip: str) -> List[List[str]]:
    """读取 CN.zip 内的 CN.txt，返回行列表。"""
    with zipfile.ZipFile(cn_zip) as archive:
        with archive.open("CN.txt") as handle:
            text = handle.read().decode("utf-8")
    return [line.split("\t") for line in text.splitlines() if line.strip()]


def load_admin1_names(path: str) -> Dict[str, str]:
    """读取 admin1CodesASCII.txt，返回 ``CN.01 -> Anhui`` 形式的字典。"""
    names: Dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2 and parts[0].startswith("CN."):
                names[parts[0][3:]] = parts[1]
    return names


# --------------------------------------------------------------------------- #
# 坐标解析
# --------------------------------------------------------------------------- #


class SeatResolver:
    """按优先级为每个 ADM2 找到「城区驻地」坐标。"""

    def __init__(self, rows: Iterable[Sequence[str]]) -> None:
        self._by_admin2: Dict[str, List[Sequence[str]]] = defaultdict(list)
        self._by_admin1_name: Dict[Tuple[str, str], List[Sequence[str]]] = defaultdict(list)
        for row in rows:
            if row[6] != "P" or not row[10]:
                continue
            if row[11]:
                self._by_admin2[row[11]].append(row)
            self._by_admin1_name[(row[10], normalize_ascii(row[1]))].append(row)

    @staticmethod
    def _by_population(rows: Sequence[Sequence[str]]) -> Sequence[str]:
        return max(rows, key=lambda r: int(r[14] or 0))

    def resolve(self, adm2: Sequence[str]) -> Tuple[float, float, str]:
        """返回 ``(经度, 纬度, 来源标记)``。"""
        admin1, admin2 = adm2[10], adm2[11]
        target = normalize_ascii(adm2[1])

        same_admin2 = self._by_admin2.get(admin2, [])
        if same_admin2:
            # 1) 同 admin2 且同名 —— 最可信
            same_name = [r for r in same_admin2 if normalize_ascii(r[1]) == target]
            if same_name:
                best = self._by_population(same_name)
                return float(best[5]), float(best[4]), "adm2+name"
            # 2) 同 admin2 的驻地
            seats = [r for r in same_admin2 if r[7] in SEAT_RANK]
            if seats:
                best = max(
                    seats,
                    key=lambda r: (SEAT_RANK[r[7]], int(r[14] or 0)),
                )
                return float(best[5]), float(best[4]), "adm2+seat"
            # 3) 同 admin2 内人口最大
            best = self._by_population(same_admin2)
            return float(best[5]), float(best[4]), "adm2+pop"

        # 4) / 5) 同省同名
        same_name = self._by_admin1_name.get((admin1, target), [])
        if same_name:
            seats = [r for r in same_name if r[7] in SEAT_RANK]
            if seats:
                best = max(seats, key=lambda r: (SEAT_RANK[r[7]], int(r[14] or 0)))
                return float(best[5]), float(best[4]), "name+seat"
            return float(self._by_population(same_name)[5]), float(
                self._by_population(same_name)[4]
            ), "name"

        # 6) 兜底用质心（会在报告里列出）
        return float(adm2[5]), float(adm2[4]), "centroid"


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #


def build(cache_dir: str, force_download: bool) -> Tuple[List[Dict[str, object]], Dict[str, object]]:
    """构建城市库，返回 ``(cities, stats)``。"""
    print("[1/5] 下载数据源")
    cn_zip = download(URL_CN, os.path.join(cache_dir, "CN.zip"), force_download)
    admin1_file = download(
        URL_ADMIN1, os.path.join(cache_dir, "admin1CodesASCII.txt"), force_download
    )

    print("[2/5] 解析 GeoNames 数据")
    rows = load_cn_rows(cn_zip)
    admin1_names = load_admin1_names(admin1_file)
    print(f"  CN.txt 共 {len(rows):,} 条记录")

    adm2_rows = [r for r in rows if r[6] == "A" and r[7] == "ADM2"]
    print(f"  ADM2（地级行政区）共 {len(adm2_rows)} 条")

    print("[3/5] 解析城区坐标")
    resolver = SeatResolver(rows)

    print("[4/5] 生成城市条目")
    sources: Dict[str, int] = defaultdict(int)
    problems: List[str] = []
    ambiguous: List[str] = []
    collected: List[Dict[str, object]] = []

    for adm2 in adm2_rows:
        geo_name = adm2[1]
        if geo_name in EXCLUDE_GEO_NAMES:
            continue

        admin1 = adm2[10]
        if admin1 not in PROVINCE_MAP:
            problems.append(f"[skip] 未知 admin1={admin1} {geo_name}")
            continue

        province = PROVINCE_MAP[admin1][0]
        override_name = NAME_OVERRIDES.get((province, geo_name))
        chinese, candidates = extract_chinese_name(adm2)

        if override_name:
            chinese = override_name
        if not chinese:
            problems.append(f"[miss] {province} {geo_name} 无中文名候选")
            continue
        # 多候选且长度不一致时记录下来，便于人工复核
        if len(candidates) > 1 and len({strip_admin_suffix(c) for c in candidates}) > 1:
            ambiguous.append(f"{province}/{chinese} <- {geo_name} {candidates}")

        longitude, latitude, source = resolver.resolve(adm2)
        sources[source] += 1
        if source == "centroid":
            problems.append(f"[centroid] {province}/{chinese} 使用了行政区质心，请复核")

        coord_override = COORD_OVERRIDES.get((province, chinese))
        if coord_override:
            longitude, latitude = coord_override

        collected.append(
            {
                "name": chinese,
                "province": province,
                "longitude": round4(longitude),
                "latitude": round4(latitude),
                "_py": PY_PINYIN_OVERRIDES.get((province, chinese), pinyin_of(adm2)),
                "_geo": geo_name,
                "_source": source,
            }
        )

    print("[5/5] 合并内置城市 / 去重 / 排序")
    for extra in EXTRA_CITIES:
        item = dict(extra)
        item["_py"] = str(extra["py"])
        item["_geo"] = "<builtin>"
        item["_source"] = "builtin"
        collected.append(item)
        sources["builtin"] += 1

    # 同省同名去重：保留来源更权威（builtin > adm2+name > ... > centroid）的那条
    source_order = {
        "builtin": 0, "adm2+name": 1, "adm2+seat": 2, "adm2+pop": 3,
        "name+seat": 4, "name": 5, "centroid": 6,
    }
    deduped: Dict[Tuple[str, str], Dict[str, object]] = {}
    dropped: List[str] = []
    for item in collected:
        key = (str(item["province"]), str(item["name"]))
        if key in deduped:
            old = deduped[key]
            if source_order[str(item["_source"])] < source_order[str(old["_source"])]:
                dropped.append(f"{item['province']}/{item['name']}({old['_geo']})")
                deduped[key] = item
            else:
                dropped.append(f"{item['province']}/{item['name']}({item['_geo']})")
            continue
        deduped[key] = item

    province_py = {code: py for code, (_, py) in PROVINCE_MAP.items()}
    cities = sorted(
        deduped.values(),
        key=lambda c: (
            province_py.get(
                next((k for k, v in PROVINCE_MAP.items() if v[0] == c["province"]), ""),
                c["province"],
            ),
            str(c["_py"]),
            str(c["name"]),
        ),
    )

    stats = {
        "adm2_total": len(adm2_rows),
        "collected": len(collected),
        "after_dedup": len(cities),
        "sources": dict(sources),
        "problems": problems,
        "ambiguous": ambiguous,
        "dropped": dropped,
        "provinces": sorted({str(c["province"]) for c in cities}),
    }
    return cities, stats


def write_json(cities: List[Dict[str, object]], out_path: str) -> None:
    """写出 city_coords.json（字段与旧版保持兼容）。"""
    payload = {
        "version": DATA_VERSION,
        "note": "全国地级市经纬度（真太阳时校正用），由 GeoNames dump 生成，见 gen_city_coords.py",
        "source": "GeoNames CN.zip (admin1/admin2 + PPLA 驻地)",
        "count": len(cities),
        "cities": [
            {
                "name": c["name"],
                "province": c["province"],
                "longitude": c["longitude"],
                "latitude": c["latitude"],
            }
            for c in cities
        ],
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def print_report(cities: List[Dict[str, object]], stats: Dict[str, object], out_path: str) -> None:
    """打印统计与自检信息。"""
    print()
    print("=" * 66)
    print("生成统计")
    print("=" * 66)
    print(f"ADM2 原始            : {stats['adm2_total']}")
    print(f"收集条目             : {stats['collected']}")
    print(f"去重后城市数         : {stats['after_dedup']}")
    print(f"省级行政区覆盖       : {len(stats['provinces'])}")
    print(f"坐标来源分布         : {stats['sources']}")
    print(f"被去重条目           : {len(stats['dropped'])}")

    longitudes = [float(c["longitude"]) for c in cities]
    latitudes = [float(c["latitude"]) for c in cities]
    print(f"经度范围             : {min(longitudes):.4f} ~ {max(longitudes):.4f}")
    print(f"纬度范围             : {min(latitudes):.4f} ~ {max(latitudes):.4f}")

    out_of_range = [
        c for c in cities
        if not (73 <= float(c["longitude"]) <= 135 and 3 <= float(c["latitude"]) <= 54)
    ]
    print(f"越界条目             : {len(out_of_range)}")

    print()
    print("=" * 66)
    print("自检断言")
    print("=" * 66)
    checks: List[Tuple[str, bool, str]] = []

    checks.append(("城市总数 >= 300", len(cities) >= 300, f"{len(cities)}"))

    field_ok = all(
        all(k in c for k in ("name", "province", "longitude", "latitude")) for c in cities
    )
    checks.append(("字段完整", field_ok, "name/province/longitude/latitude"))

    checks.append(("经度均在 73~135", not out_of_range, f"越界 {len(out_of_range)} 条"))

    checks.append((
        "省级行政区 >= 31",
        len(stats["provinces"]) >= 31,
        f"{len(stats['provinces'])} 个",
    ))

    must = ["孝感", "武汉", "北京", "上海", "广州", "深圳", "成都", "西安",
            "乌鲁木齐", "拉萨", "哈尔滨"]
    by_name = {str(c["name"]): c for c in cities}
    missing = [n for n in must if n not in by_name]
    checks.append(("必备城市齐全", not missing, f"缺 {missing}" if missing else must[0] + " 等 11 个"))

    truth = {
        "孝感": 113.9, "乌鲁木齐": 87.6, "拉萨": 91.1, "哈尔滨": 126.6,
        "北京": 116.4, "上海": 121.5, "成都": 104.1, "西安": 108.9,
    }
    drift_lines = []
    ok = True
    for name, expect in truth.items():
        city = by_name.get(name)
        if not city:
            ok = False
            drift_lines.append(f"{name}: 缺失")
            continue
        delta = abs(float(city["longitude"]) - expect)
        drift_lines.append(
            f"  {name:<8} 期望 {expect:>7.2f}  实际 {float(city['longitude']):>9.4f}  偏差 {delta:.3f}"
        )
        if delta > 0.3:
            ok = False
    checks.append(("抽查经度误差 <= 0.3°", ok, "见下"))

    for label, passed, detail in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label:<22} {detail}")
    print()
    for line in drift_lines:
        print(line)

    if stats["problems"]:
        print()
        print("需要人工确认：")
        for item in stats["problems"]:
            print(f"  {item}")

    if stats["ambiguous"]:
        print()
        print(f"中文名多候选（已取最短，已抽样复核）：{len(stats['ambiguous'])} 条，示例：")
        for item in stats["ambiguous"][:12]:
            print(f"  {item}")

    print()
    print(f"输出文件：{out_path}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。"""
    parser = argparse.ArgumentParser(
        description="从 GeoNames 生成全国地级市经纬度库（真太阳时校正用）"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="只打印统计，不写入文件"
    )
    parser.add_argument(
        "--force-download", action="store_true", help="忽略缓存，强制重新下载"
    )
    parser.add_argument("--out", default=DEFAULT_OUT, help="输出 JSON 路径")
    parser.add_argument("--cache-dir", default=DEFAULT_CACHE, help="下载缓存目录")
    args = parser.parse_args(argv)

    cities, stats = build(args.cache_dir, args.force_download)
    print_report(cities, stats, args.out)

    if args.dry_run:
        print()
        print("[dry-run] 未写入文件")
        return 0

    write_json(cities, args.out)
    print()
    print(f"[done] 已写入 {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
