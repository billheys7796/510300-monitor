"""
510300 沪深300ETF 行情获取 + PushPlus 微信推送
用于 GitHub Actions 定时运行

环境变量：
  PUSHPLUS_TOKEN - PushPlus 推送令牌（必填）
"""
import requests
import json
import pandas as pd
import os
import sys
from datetime import datetime, timezone, timedelta

# ── 时区 ──
BJT = timezone(timedelta(hours=8))

def is_trading_time():
    """判断当前北京时间是否在交易时段（9:25-15:05，周一至周五）"""
    now = datetime.now(BJT)
    if now.weekday() >= 5:  # 周六、周日
        return False
    t = now.hour * 60 + now.minute
    return 9 * 60 + 25 <= t <= 15 * 60 + 5  # 9:25 ~ 15:05


# ── 数据获取 ──

def calc_ma(series, period):
    return series.rolling(window=period).mean()


def get_kline_sina(symbol, count=200, period='30'):
    """从新浪获取K线数据"""
    url = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
    params = {'symbol': symbol, 'scale': period, 'ma': 'no', 'datalen': count}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://finance.sina.com.cn/'
    }
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    data = json.loads(resp.text)
    df = pd.DataFrame(data)
    df.columns = ['day', 'open', 'high', 'low', 'close', 'volume']
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    return df


def get_realtime_sina(symbol):
    """从新浪获取实时行情"""
    url = f"http://hq.sinajs.cn/list={symbol}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://finance.sina.com.cn/'
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.encoding = 'gbk'
    content = resp.text.split('"')[1]
    parts = content.split(',')
    return {
        'name': parts[0],
        'open': float(parts[1]),
        'prev_close': float(parts[2]),
        'price': float(parts[3]),
        'high': float(parts[4]),
        'low': float(parts[5]),
        'volume': float(parts[8]),
        'amount': float(parts[9]),
    }


# ── PushPlus 推送 ──

def push_to_wechat(token, title, content):
    """通过 PushPlus 发送到微信"""
    url = "http://www.pushplus.plus/send"
    payload = {
        "token": token,
        "title": title,
        "content": content,
        "template": "markdown"
    }
    resp = requests.post(url, json=payload, timeout=15)
    result = resp.json()
    if result.get("code") == 200:
        print(f"[PushPlus] 发送成功 → {result.get('data','')}")
    else:
        print(f"[PushPlus] 发送失败: {result}")
    return result


# ── 主流程 ──

def main():
    # 检查交易时间
    if not is_trading_time():
        now = datetime.now(BJT).strftime('%Y-%m-%d %H:%M')
        print(f"[{now}] 非交易时段，跳过推送")
        return

    # 检查 Token
    token = os.environ.get("PUSHPLUS_TOKEN", "")
    if not token:
        print("ERROR: 未设置 PUSHPLUS_TOKEN 环境变量")
        sys.exit(1)

    try:
        # 获取数据
        rt = get_realtime_sina("sh510300")
        df = get_kline_sina("sh510300", count=200, period='30')

        # 计算均线
        df['M5'] = calc_ma(df['close'], 5)
        df['M20'] = calc_ma(df['close'], 20)
        df['M55'] = calc_ma(df['close'], 55)

        last = df.iloc[-1]
        price = rt['price']
        prev = rt['prev_close']
        chg = price - prev
        chg_pct = chg / prev * 100

        # 趋势判断
        trend = '🔴' if chg_pct >= 0 else '🟢'
        sign = '+' if chg_pct >= 0 else ''

        # 成交额（亿）
        amount_yi = rt['amount'] / 1e8

        now_str = datetime.now(BJT).strftime('%Y-%m-%d %H:%M')

        # 构建 Markdown 消息
        msg = f"""## 📊 510300 沪深300ETF

> {now_str}　{trend} **{price:.4f}**　{sign}{chg_pct:.2f}%

| 项目 | 数值 |
|:---|---:|
| 最新价 | **{price:.4f}** |
| 涨跌 | {sign}{chg:.4f}（{sign}{chg_pct:.2f}%） |
| 今开 | {rt['open']:.4f} |
| 昨收 | {prev:.4f} |
| 最高 | {rt['high']:.4f} |
| 最低 | {rt['low']:.4f} |

### 📈 均线（30分钟周期）

| 均线 | 数值 | 与现价差 |
|:---|---:|---:|
| M5 | **{last['M5']:.4f}** | {price - last['M5']:+.4f} |
| M20 | {last['M20']:.4f} | {price - last['M20']:+.4f} |
| M55 | {last['M55']:.4f} | {price - last['M55']:+.4f} |

---
成交量 **{rt['volume']/10000:.1f}** 万手　|　成交额 **{amount_yi:.2f}** 亿
"""

        # 发送
        push_to_wechat(token, f"510300 {price:.4f} {trend}", msg)

    except Exception as e:
        error_msg = f"510300 行情获取失败：{e}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        # 尝试推送错误消息
        if token:
            try:
                push_to_wechat(token, "510300 推送异常", error_msg)
            except:
                pass


if __name__ == "__main__":
    main()
