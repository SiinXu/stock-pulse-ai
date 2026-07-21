#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tushare stock list retrieval script

Gets A-shares, Hong Kong stocks, U.S. stocks lists from Tushare Pro, saves them as CSV files.

Method:
    python3 scripts/fetch_tushare_stock_list.py
    python3 scripts/fetch_tushare_stock_list.py --a-rk

Environment Requirements:
    - Needs to be configured TUSHARE_TOKEN in .env
    - Install tushare: pip install tushare
    - Account point requirements:
        * A-shares/Hong Kong stocks: 2000 points
        * U.S. stocks: 120 points trial, 5000 points formal permission

Output file:
    - data/stock_list_a.csv      A-shares list(--a-rk Will Override with Corrected Name)
    - data/stock_list_hk.csv     Hong Kong stock list
    - data/stock_list_us.csv     U.S. stocks List
    - data/README_stock_list.md  Data Description Document
"""

import argparse
import os
import sys
import time
import random
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

import pandas as pd
from dotenv import load_dotenv

# Add project root directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import tushare as ts
except ImportError:
    print("[错误] 未安装 tushare 库")
    print("请执行: pip install tushare")
    sys.exit(1)


# Configuration
load_dotenv()

TUSHARE_TOKEN = os.getenv('TUSHARE_TOKEN')
OUTPUT_DIR = Path(__file__).parent.parent / "data"
PAGE_SIZE = 5000  # Number of records read per page from U.S. stocks (API max 6000, set 5000 with margin)
SLEEP_MIN = 5     # Minimum sleep time (seconds)
SLEEP_MAX = 10    # Maximum sleep time (seconds)
A_RK_BATCH_SIZE = 200
A_RK_FIELDS = "ts_code,name,close,pre_close,trade_time"
A_RK_NAME_PREFIX_RE = re.compile(r"^(XD|XR|DR|N|C)")


def get_tushare_api() -> Optional[ts.pro_api]:
    """
    Get Tushare API instance

    Returns:
        Tushare API instance, or None on failure
    """
    if not TUSHARE_TOKEN:
        print("[错误] 未找到 TUSHARE_TOKEN")
        print("请在 .env 文件中配置: TUSHARE_TOKEN=你的token")
        return None

    try:
        api = ts.pro_api(TUSHARE_TOKEN)
        # Test connection.
        api.trade_cal(exchange='SSE', start_date='20240101', end_date='20240101')
        print("✓ Tushare API 连接成功")
        return api
    except Exception as e:
        print(f"[错误] Tushare API 连接失败: {e}")
        print("请检查：")
        print("  1. TUSHARE_TOKEN 是否正确")
        print("  2. 账号积分是否足够（A股/港股需要2000积分）")
        return None


def random_sleep(min_seconds: int = SLEEP_MIN, max_seconds: int = SLEEP_MAX):
    """
    Random sleep, avoid frequent requests

    Args:
        min_seconds: Minimum sleep time
        max_seconds: maximum sleep time
    """
    sleep_time = random.uniform(min_seconds, max_seconds)
    print(f"  ⏱  休息 {sleep_time:.1f} 秒...")
    time.sleep(sleep_time)


def fetch_a_stock_list(api: ts.pro_api) -> Optional[pd.DataFrame]:
    """
    Get A-shares list

    Interface: stock_basic
    Limited: Maximum 6000 rows (covers the entire A-shares market)

    Args:
        api: Tushare API instance

    Returns:
        DataFrame containing A-share data, or None on failure
    """
    print("\n[1/3] 正在获取 A股列表...")

    try:
        # Get all normally listed stocks
        df = api.stock_basic(
            exchange='',        # Empty: All exchanges.
            list_status='L',    # L: Listed, D: Delisted, P: Suspended Listing
            fields='ts_code,symbol,name,area,industry,fullname,enname,cnspell,market,exchange,curr_type,list_status,list_date,delist_date,is_hs,act_name,act_ent_type'
        )

        if df is not None and len(df) > 0:
            print(f"✓ A股列表获取成功，共 {len(df)} 只股票")
            print("  - 交易所分布：")
            for exchange, count in df['exchange'].value_counts().items():
                print(f"    {exchange}: {count} 只")
            return df
        else:
            print("[错误] A股数据为空")
            return None

    except Exception as e:
        print(f"[错误] 获取 A股列表失败: {e}")
        return None


def should_fix_a_stock_name(name: str) -> bool:
    """
    Check if the A-shares name belongs to a state that needs correction.

    Primarily covers new stock and ex-dividend adjustments prefixes:
    XD / XR / DR / N / C
    """
    if name is None:
        return False

    text = str(name).strip()
    if not text or text.lower() in {"nan", "none"}:
        return False

    return bool(A_RK_NAME_PREFIX_RE.match(text))


def chunk_list(items: List[str], chunk_size: int) -> List[List[str]]:
    """Split the list into chunks of a fixed size."""
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


def fetch_rt_k_names(api: ts.pro_api, ts_codes: List[str]) -> Dict[str, str]:
    """
    Batch retrieve stock names returned by rt_k.

    Refer to the official documentation:
    https://tushare.pro/wctapi/documents/372.md

    rt_k is a real-time daily candlestick interface for A-shares, supporting extraction by stock code and wildcard stock code.
    Real-time daily K-line data. This script only uses it as an auxiliary source for name backfill correction.
    stock_basic returns short-term trading status prefix name.
    """
    if not ts_codes:
        return {}

    name_map: Dict[str, str] = {}
    batches = chunk_list(ts_codes, A_RK_BATCH_SIZE)

    print(f"\n[rt_k] 待修正股票数：{len(ts_codes)}，分 {len(batches)} 批获取...")

    for index, batch in enumerate(batches, start=1):
        ts_code_param = ",".join(batch)
        print(f"  [rt_k] 第 {index}/{len(batches)} 批：{len(batch)} 只股票")

        try:
            df = api.rt_k(ts_code=ts_code_param, fields=A_RK_FIELDS)
        except Exception as e:
            print(f"  [警告] rt_k 批次 {index} 获取失败: {e}")
            continue

        if df is None or len(df) == 0:
            print(f"  [警告] rt_k 批次 {index} 无返回数据")
            continue

        for _, row in df.iterrows():
            code_value = row.get("ts_code", "")
            name_value = row.get("name", "")

            if pd.isna(code_value) or pd.isna(name_value):
                continue

            code = str(code_value).strip()
            name = str(name_value).strip()
            if code and name and code.lower() not in {"nan", "none"} and name.lower() not in {"nan", "none"}:
                name_map[code] = name

        if index < len(batches):
            random_sleep(1, 2)

    print(f"[rt_k] 成功获取 {len(name_map)} 条名称映射")
    return name_map


def fix_a_stock_names_with_rt_k(api: ts.pro_api, df: pd.DataFrame) -> pd.DataFrame:
    """
    Use rt_k to correct A-shares name.

    Corrects names with XD / XR / DR / N / C prefixes.
    """
    if df is None or len(df) == 0:
        return df

    if "name" not in df.columns or "ts_code" not in df.columns:
        print("[警告] A股数据缺少 ts_code/name 列，跳过 rt_k 名称修正")
        return df

    fix_mask = df["name"].astype(str).map(should_fix_a_stock_name)
    fix_df = df.loc[fix_mask, ["ts_code", "name"]].copy()

    if fix_df.empty:
        print("[rt_k] 未发现需要修正的 A 股名称")
        return df

    ts_codes = fix_df["ts_code"].astype(str).tolist()
    print(f"[rt_k] 发现 {len(ts_codes)} 只待修正 A 股：")
    print("  " + ", ".join(ts_codes[:20]) + (" ..." if len(ts_codes) > 20 else ""))

    name_map = fetch_rt_k_names(api, ts_codes)
    if not name_map:
        print("[警告] rt_k 未返回可用名称，保留原始 A 股名称")
        return df

    fixed_df = df.copy()
    fixed_count = 0
    for code, new_name in name_map.items():
        if not new_name:
            continue
        match_index = fixed_df.index[fixed_df["ts_code"].astype(str) == code]
        if len(match_index) == 0:
            continue

        old_name = str(fixed_df.loc[match_index[0], "name"])
        if old_name != new_name:
            fixed_df.loc[match_index[0], "name"] = new_name
            fixed_count += 1
            print(f"  ✓ {code}: {old_name} -> {new_name}")

    print(f"[rt_k] A 股名称修正完成，共修正 {fixed_count} 只股票")
    return fixed_df


def fetch_hk_stock_list(api: ts.pro_api) -> Optional[pd.DataFrame]:
    """
    Get the list of Hong Kong stocks

    Interface: hk_basic
    Limited: All stocks in trading within Hong Kong stocks

    Args:
        api: Tushare API instance

    Returns:
        DataFrame containing Hong Kong stock data, or None on failure
    """
    print("\n[2/3] 正在获取港股列表...")

    try:
        # Get all normally listed Hong Kong stocks
        df = api.hk_basic(
            list_status='L'    # L: Listed, D: Delisted
        )

        if df is not None and len(df) > 0:
            print(f"✓ 港股列表获取成功，共 {len(df)} 只股票")
            return df
        else:
            print("[错误] 港股数据为空")
            return None

    except Exception as e:
        print(f"[错误] 获取港股列表失败: {e}")
        return None


def fetch_us_stock_list(api: ts.pro_api) -> Optional[pd.DataFrame]:
    """
    Get US stock list (pagination read)

    Interface: us_basic
    Limited: Maximum 6000, requires pagination extraction

    Args:
        api: Tushare API instance

    Returns:
    DataFrame containing U.S. stock data, or None on failure
    """
    print("\n[3/3] 正在获取美股列表（分页读取）...")

    all_data = []
    offset = 0
    page = 1

    try:
        while True:
            print(f"  第 {page} 页（offset={offset}）...")

            df = api.us_basic(
                offset=offset,
                limit=PAGE_SIZE
            )

            if df is None or len(df) == 0:
                print(f"  ✓ 第 {page} 页无数据，读取完成")
                break

            all_data.append(df)
            print(f"  ✓ 第 {page} 页获取 {len(df)} 只股票")

            # If the returned data is less than page size, it indicates reaching the last page.
            if len(df) < PAGE_SIZE:
                break

            offset += PAGE_SIZE
            page += 1

            # Random pause (last page does not need to pause)
            random_sleep()

        if all_data:
            result_df = pd.concat(all_data, ignore_index=True)
            print(f"✓ 美股列表获取成功，共 {len(result_df)} 只股票（{page} 页）")

            # Statistics by category.
            if 'classify' in result_df.columns:
                print("  - 分类分布：")
                for classify, count in result_df['classify'].value_counts().items():
                    print(f"    {classify}: {count} 只")

            return result_df
        else:
            print("[错误] 美股数据为空")
            return None

    except Exception as e:
        print(f"[错误] 获取美股列表失败: {e}")
        return None


def save_to_csv(df: pd.DataFrame, filename: str, market_name: str) -> bool:
    """
    Save data to CSV file

    Args:
        df: Input DataFrame
        filename: Filename
        market_name: market name (for logging)

    Returns:
        Whether saved successfully
    """
    if df is None or len(df) == 0:
        print(f"[跳过] {market_name} 数据为空，不保存文件")
        return False

    try:
        output_path = OUTPUT_DIR / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        df.to_csv(output_path, index=False, encoding='utf-8-sig')

        file_size = output_path.stat().st_size / 1024  # KB
        print(f"✓ {market_name} 数据已保存：{output_path} ({file_size:.2f} KB)")
        return True

    except Exception as e:
        print(f"[错误] 保存 {market_name} 数据失败: {e}")
        return False


def generate_data_documentation(
    a_df: Optional[pd.DataFrame],
    hk_df: Optional[pd.DataFrame],
    us_df: Optional[pd.DataFrame],
    a_filename: str = "stock_list_a.csv",
    a_title: str = "A股列表"
):
    """
    Generate data documentation

    Args:
        a_df: A-shares data
        hk_df: Hong Kong stock data
        us_df: U.S. stock data
    """
    doc_path = OUTPUT_DIR / "README_stock_list.md"

    content = f"""# Tushare 股票列表数据说明

> 数据来源：[Tushare Pro](https://tushare.pro)
> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 文件说明

| 文件 | 说明 | 记录数 |
|------|------|--------|
| `{a_filename}` | {a_title} | {len(a_df) if a_df is not None else 0} |
| `stock_list_hk.csv` | 港股列表 | {len(hk_df) if hk_df is not None else 0} |
| `stock_list_us.csv` | 美股列表 | {len(us_df) if us_df is not None else 0} |

---

## A股数据（{a_filename}）

### 数据接口
- **接口名称**：`stock_basic`
- **数据权限**：2000积分起，每分钟请求50次
- **数据限量**：单次最多6000行（覆盖全市场A股）

### 字段说明

| 字段名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| ts_code | str | TS代码 | 000001.SZ |
| symbol | str | 股票代码 | 000001 |
| name | str | 股票名称 | 平安银行 |
| area | str | 地域 | 深圳 |
| industry | str | 所属行业 | 银行 |
| fullname | str | 股票全称 | 平安银行股份有限公司 |
| enname | str | 英文全称 | Ping An Bank Co., Ltd. |
| cnspell | str | 拼音缩写 | PAYH |
| market | str | 市场类型 | 主板/创业板/科创板/CDR |
| exchange | str | 交易所代码 | SSE上交所/SZSE深交所/BSE北交所 |
| curr_type | str | 交易货币 | CNY |
| list_status | str | 上市状态 | L上市/D退市/P暂停上市 |
| list_date | str | 上市日期 | 19910403 |
| delist_date | str | 退市日期 | - |
| is_hs | str | 是否沪深港通标的 | N否/H沪股通/S深股通 |
| act_name | str | 实控人名称 | - |
| act_ent_type | str | 实控人企业性质 | - |

### 数据样例
```csv
ts_code,symbol,name,area,industry,fullname,enname,cnspell,market,exchange,curr_type,list_status,list_date,delist_date,is_hs,act_name,act_ent_type
000001.SZ,000001,平安银行,深圳,银行,平安银行股份有限公司,Ping An Bank Co., Ltd.,PAYH,主板,SZSE,CNY,L,19910403,,S,,
000002.SZ,000002,万科A,深圳,全国地产,万科企业股份有限公司,China Vanke Co., Ltd.,ZKA,主板,SZSE,CNY,L,19910129,,S,,
```

---

## 港股数据（stock_list_hk.csv）

### 数据接口
- **接口名称**：`hk_basic`
- **数据权限**：用户需要至少2000积分才可以调取
- **数据限量**：单次可提取全部在交易的港股列表数据

### 字段说明

| 字段名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| ts_code | str | TS代码 | 00001.HK |
| name | str | 股票简称 | 长和 |
| fullname | str | 公司全称 | 长江和记实业有限公司 |
| enname | str | 英文名称 | CK Hutchison Holdings Ltd. |
| cn_spell | str | 拼音 | ZH |
| market | str | 市场类别 | 主板/创业板 |
| list_status | str | 上市状态 | L上市/D退市/P暂停上市 |
| list_date | str | 上市日期 | 19720731 |
| delist_date | str | 退市日期 | - |
| trade_unit | float | 交易单位 | 1000 |
| isin | str | ISIN代码 | KYG217651051 |
| curr_type | str | 货币代码 | HKD |

### 数据样例
```csv
ts_code,name,fullname,enname,cn_spell,market,list_status,list_date,delist_date,trade_unit,isin,curr_type
00001.HK,长和,长江和记实业有限公司,CK Hutchison Holdings Ltd.,ZH,主板,L,19720731,,1000,KYG217651051,HKD
00002.HK,中电控股,中华电力有限公司,CLP Holdings Ltd.,ZDKG,主板,L,19860125,,1000,HK0002007356,HKD
```

---

## 美股数据（stock_list_us.csv）

### 数据接口
- **接口名称**：`us_basic`
- **数据权限**：120积分可以试用，5000积分有正式权限
- **数据限量**：单次最大6000，可分页提取

### 字段说明

| 字段名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| ts_code | str | 美股代码 | AAPL |
| name | str | 中文名称 | 苹果 |
| enname | str | 英文名称 | Apple Inc. |
| classify | str | 分类 | ADR/GDR/EQT |
| list_date | str | 上市日期 | 19801212 |
| delist_date | str | 退市日期 | - |

### 分类说明
- **ADR**：美国存托凭证（American Depositary Receipt）
- **GDR**：全球存托凭证（Global Depositary Receipt）
- **EQT**：普通股（Equity）

### 数据样例
```csv
ts_code,name,enname,classify,list_date,delist_date
AAPL,苹果,Apple Inc.,EQT,19801212,
TSLA,特斯拉,Tesla Inc.,EQT,20100629,
BABA,阿里巴巴,Alibaba Group Holding Ltd.,ADR,20140919,
```

---

## 使用说明

### 读取数据

```python
import pandas as pd

# 读取 A股数据
a_stocks = pd.read_csv('data/{a_filename}')

# 读取港股数据
hk_stocks = pd.read_csv('data/stock_list_hk.csv')

# 读取美股数据
us_stocks = pd.read_csv('data/stock_list_us.csv')
```

### 代码格式说明

**A股代码格式**：
- 沪市：`600000.SH`（主板）、`688xxx.SH`（科创板）、`900xxx.SH`（B股）
- 深市：`000001.SZ`（主板）、`300xxx.SZ`（创业板）、`200xxx.SZ`（B股）
- 北交所：`8xxxxx.BJ`、`4xxxxx.BJ`、`920xxx.BJ`

**港股代码格式**：
- 格式：`xxxxx.HK`（5位数字 + .HK）
- 示例：`00700.HK`（腾讯控股）

**美股代码格式**：
- 格式：代码字母（无后缀）
- 示例：`AAPL`（苹果）、`TSLA`（特斯拉）

---

## 注意事项

1. **数据更新**：建议定期更新数据（如每月一次）
2. **积分要求**：
   - A股/港股：需要2000积分
   - 美股：120积分试用，5000积分正式权限
3. **请求限制**：注意 API 的每分钟请求次数限制
4. **数据完整性**：本数据仅包含基础信息，如需更多数据请参考 Tushare 官方文档

---

## 相关链接

- [Tushare 官网](https://tushare.pro)
- [Tushare 文档](https://tushare.pro/document/2)
- [积分获取办法](https://tushare.pro/document/1)
- [API 数据调试](https://tushare.pro/document/2)
"""

    try:
        with open(doc_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✓ 数据说明文档已生成：{doc_path}")
    except Exception as e:
        print(f"[错误] 生成说明文档失败: {e}")


def build_arg_parser() -> argparse.ArgumentParser:
    """Build command-line parameters."""
    parser = argparse.ArgumentParser(description="Tushare 股票列表获取工具")
    parser.add_argument(
        "--a-rk",
        action="store_true",
        help="使用 rt_k 修正 A 股中带 XD/XR/DR/N/C 前缀的名称，并覆盖输出到 stock_list_a.csv",
    )
    return parser


def main(argv: Optional[List[str]] = None):
    """Main Function"""
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    print("=" * 60)
    print("Tushare 股票列表获取工具")
    print("=" * 60)
    print(f"[信息] A股名称修正模式：{'开启' if args.a_rk else '关闭'}")

    # 1. Get API instance
    api = get_tushare_api()
    if not api:
        return 1

    # 2. Get A-shares data
    a_df = fetch_a_stock_list(api)
    if a_df is not None:
        a_filename = 'stock_list_a.csv'
        a_title = 'A股列表'
        a_market_name = 'A股'

        if args.a_rk:
            a_df = fix_a_stock_names_with_rt_k(api, a_df)
            a_title = 'A股列表（修正后）'

        save_to_csv(a_df, a_filename, a_market_name)

    # 3. Get Hong Kong stock data
    random_sleep()  # Rest after getting Hong Kong stocks
    hk_df = fetch_hk_stock_list(api)
    if hk_df is not None:
        save_to_csv(hk_df, 'stock_list_hk.csv', '港股')

    # 4. Get US stock data (pagination)
    random_sleep()  # Get US stocks after rest
    us_df = fetch_us_stock_list(api)
    if us_df is not None:
        save_to_csv(us_df, 'stock_list_us.csv', '美股')

    # 5. Generate data documentation
    print("\n正在生成数据说明文档...")
    a_filename = 'stock_list_a.csv'
    a_title = 'A股列表（修正后）' if args.a_rk else 'A股列表'
    generate_data_documentation(a_df, hk_df, us_df, a_filename=a_filename, a_title=a_title)

    # 6. Summary
    print("\n" + "=" * 60)
    print("任务完成！")
    print("=" * 60)

    total_count = 0
    if a_df is not None:
        total_count += len(a_df)
        print(f"  ✓ A股：{len(a_df)} 只")
    if hk_df is not None:
        total_count += len(hk_df)
        print(f"  ✓ 港股：{len(hk_df)} 只")
    if us_df is not None:
        total_count += len(us_df)
        print(f"  ✓ 美股：{len(us_df)} 只")

    print(f"\n总计：{total_count} 只股票")
    print(f"输出目录：{OUTPUT_DIR}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n[中断] 用户取消操作")
        sys.exit(1)
    except Exception as e:
        print(f"\n[错误] 未预期的异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
