import ccxt
import pandas as pd
import time
from datetime import datetime
from tabulate import tabulate

# 初始化 OKX 交易所，启用 sandbox 模式
okx = ccxt.okx({
    'apiKey': '<apiKey>',
    'secret': '<Secret',
    'password': '<Password>',
    'enableRateLimit': True,
})

"""隨便你策略怎麼寫，但一定要一定要一定要加這一行，這是使用模擬交易模式-----------------------------------------------------------------------------------------------------------"""

okx.set_sandbox_mode(True)

"""-------------------------------------------------------------------------------------------------------------------------------------------------------------------------"""

symbol = 'BTC/USDT'
timeframe = '1m'  # 時間週期設置為 1 分鐘
sma_short_period = 3    # 短期移動平均線
sma_medium_period = 7  # 中期移動平均線
sma_long_period = 15    # 長期移動平均線

ema_short_period = 3    # 短期指數移動平均線
ema_medium_period = 7  # 中期指數移動平均線
ema_long_period = 15    # 長期指數移動平均線

initial_usdt = 72253  # 初始 USDT 資金
initial_btc = 0      # 初始 BTC 資金
btc_price_at_buy = 0  # 用來追蹤每次買入時的 BTC 價格
profit_loss = 0       # 記錄總的盈虧
max_trade_usdt = 1000  # 每次交易的最大 USDT 金額
min_btc_sell = 0.001  # 最小 BTC 賣出量
batch_buy_usdt = 200  # 每次批量購買的 USDT 金額
reserve_usdt_threshold = 100  # 當 USDT 少於這個數量時自動購買
reserve_btc_threshold = 0.001  # 當 BTC 少於這個數量時自動購買

# 記錄程式開始時間
start_time = time.time()


def fetch_ohlcv(symbol, timeframe):
    """獲取歷史數據"""
    ohlcv = okx.fetch_ohlcv(symbol, timeframe)
    df = pd.DataFrame(
        ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df


def calculate_indicators(df):
    """計算移動平均線和 EMA"""
    df['SMA5'] = df['close'].rolling(window=sma_short_period).mean()
    df['SMA15'] = df['close'].rolling(window=sma_medium_period).mean()
    df['SMA30'] = df['close'].rolling(window=sma_long_period).mean()

    df['EMA5'] = df['close'].ewm(span=ema_short_period, adjust=False).mean()
    df['EMA15'] = df['close'].ewm(span=ema_medium_period, adjust=False).mean()
    df['EMA30'] = df['close'].ewm(span=ema_long_period, adjust=False).mean()
    return df


def get_latest_signal(df):
    """根據 SMA 和 EMA 生成交易信號"""
    latest = df.iloc[-1]

    if latest['SMA5'] > latest['SMA15'] and latest['EMA5'] > latest['EMA15']:
        return 'buy'
    elif latest['SMA5'] < latest['SMA15'] and latest['EMA5'] < latest['EMA15']:
        return 'sell'
    else:
        return 'hold'


def print_balance(balance, current_price):
    """美化輸出帳戶餘額"""
    usdt_balance = balance['total'].get('USDT', 0)
    btc_balance = balance['total'].get('BTC', 0)

    balance_table = [
        ["USDT 餘額", f"{usdt_balance:.2f} USDT"],
        ["BTC 餘額", f"{btc_balance:.6f} BTC"],
        ["BTC/USDT 當前價格", f"{current_price:.2f} USDT"],
    ]

    print("\n" + tabulate(balance_table,
          headers=["資產", "數量"], tablefmt="fancy_grid"))


def buy_in_batches(symbol, total_usdt_to_spend, current_price):
    """分批購買 BTC"""
    global btc_price_at_buy
    remaining_usdt = total_usdt_to_spend
    while remaining_usdt > 0:
        # 每次購買固定批量的 USDT，直到達到總量
        batch_usdt = min(remaining_usdt, batch_buy_usdt)
        btc_amount = batch_usdt / current_price
        order = okx.create_market_buy_order(symbol, btc_amount)
        btc_price_at_buy = current_price  # 記錄買入時價格
        print(
            f"🟢 分批購買: 使用 {batch_usdt:.2f} USDT 購買了 {btc_amount:.6f} BTC，價格為 {current_price:.2f} USDT")
        remaining_usdt -= batch_usdt


def auto_refill_reserves(symbol, current_price):
    """自動補充 USDT 和 BTC 儲備"""
    balance = okx.fetch_balance()
    usdt_balance = balance['total'].get('USDT', 0)
    btc_balance = balance['total'].get('BTC', 0)

    # 自動補充 USDT
    if usdt_balance < reserve_usdt_threshold:
        print(f"⚠️ USDT 低於 {reserve_usdt_threshold}，自動補充")
        # 假設我們可以從其他地方自動獲取 USDT (可根據情況自定義行為)
        # 示例：直接添加 USDT 儲備

    # 自動補充 BTC
    if btc_balance < reserve_btc_threshold:
        print(f"⚠️ BTC 低於 {reserve_btc_threshold}，自動購買 BTC")
        btc_amount = reserve_btc_threshold - btc_balance
        order = okx.create_market_buy_order(symbol, btc_amount)
        print(
            f"🟢 自動購買 BTC: 購買了 {btc_amount:.6f} BTC，價格為 {current_price:.2f} USDT")


def execute_trade(signal, symbol):
    """根據信號進行操作，並處理可能的資金不足情況"""
    global btc_price_at_buy, profit_loss, max_trade_usdt

    try:
        balance = okx.fetch_balance()
        current_price = okx.fetch_ticker(symbol)['last']
        print_balance(balance, current_price)

        usdt_balance = balance['total'].get('USDT', 0)
        btc_balance = balance['total'].get('BTC', 0)

        # 自動檢查儲備
        auto_refill_reserves(symbol, current_price)

        if signal == 'buy':
            if usdt_balance > 10:  # 假設最小交易額為 10 USDT
                total_usdt_to_spend = min(usdt_balance, max_trade_usdt)
                buy_in_batches(symbol, total_usdt_to_spend, current_price)
            else:
                print("\n❌ USDT 餘額不足，無法執行買入操作。")

        elif signal == 'sell':
            # 每次只賣出最小交易量 (0.001 BTC)，如果餘額不足，則賣出所有剩餘的 BTC
            sell_amount = min(min_btc_sell, btc_balance)
            if sell_amount > 0.001:  # 檢查賬戶 BTC 是否足夠
                order = okx.create_market_sell_order(symbol, sell_amount)
                profit_loss += (current_price - btc_price_at_buy) * \
                    sell_amount  # 計算賣出時的盈虧
                print(
                    f"\n🔴 賣出成功: 賣出了 {sell_amount:.6f} BTC，價格為 {current_price:.2f} USDT")
            else:
                print("\n⚠️ BTC 餘額不足，無法執行賣出操作。")
        else:
            print("🟡 持有：不執行任何操作。")
    except ccxt.InsufficientFunds as e:
        print(f"\n❌ 交易失敗: {e} - 賬戶資金不足，無法執行操作。")
    except Exception as e:
        print(f"\n❌ 交易失敗: {e} - 出現了未知錯誤，請檢查系統狀態。")


def calculate_profit():
    """計算總盈利"""
    global initial_usdt, profit_loss

    # 獲取最新餘額
    balance = okx.fetch_balance()
    usdt_balance = balance['total'].get('USDT', 0)
    btc_balance = balance['total'].get('BTC', 0)

    # 假設當前價格賣掉所有 BTC
    current_price = okx.fetch_ticker(symbol)['last']
    total_usdt = usdt_balance + btc_balance * current_price

    # 計算總盈利
    total_profit = total_usdt - initial_usdt + profit_loss
    print(f"\n💰 總盈利: {total_profit:.2f} USDT")
    return total_profit


def calculate_runtime():
    """計算程式運行時間"""
    end_time = time.time()
    runtime_seconds = end_time - start_time
    runtime_minutes = runtime_seconds / 60
    print(f"\n⏳ 程式運行時間: {runtime_minutes:.2f} 分鐘")


def main():
    """持續監控市場及交易"""
    try:
        while True:
            # 獲取當前時間
            current_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"\n⏰ 當前時間: {current_timestamp}")

            # 獲取歷史數據並計算指標
            df = fetch_ohlcv(symbol, timeframe)
            df = calculate_indicators(df)

            # 打印當前價格
            current_price = df['close'].iloc[-1]
            print(f"\n📊 當前 BTC/USDT 價格: {current_price:.2f} USDT")

            # 生成交易信號並執行交易
            signal = get_latest_signal(df)
            print(f"📈 最新信號: {signal}")
            execute_trade(signal, symbol)

            # 計算總盈利
            calculate_profit()

            # 每1分鐘檢查一次
            time.sleep(60)
    except KeyboardInterrupt:
        # 捕捉中斷信號，計算程式運行時間並結束
        print("\n🛑 程式被中斷。")
        calculate_runtime()


if __name__ == '__main__':
    main()
