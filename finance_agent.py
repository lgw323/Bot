import os
import logging
import asyncio
from datetime import datetime, time, timezone, timedelta

import discord
from discord.ext import commands, tasks
import aiohttp
import yfinance as yf
from dotenv import load_dotenv

# --- 로거 및 상수 설정 ---
logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))

BOT_EMBED_COLOR = 0x00D166

# --- 환경 변수 로드 ---
try:
    FINANCE_CHANNEL_ID = int(os.getenv("FINANCE_CHANNEL_ID", "0"))
except (ValueError, TypeError):
    FINANCE_CHANNEL_ID = 0

# --- 추적할 주식 종목 (여기를 수정하여 종목을 관리합니다) ---
STOCK_TICKERS = {
    "삼성전자": "005930.KS",
    "SK하이닉스": "000660.KS",
    "애플": "AAPL",
    "테슬라": "TSLA",
    "엔비디아": "NVDA",
    "Vanguard S&P 500 ETF": "VOO"
}

# --- 데이터 조회 함수 ---
async def fetch_exchange_rates():
    url = "https://open.er-api.com/v6/latest/KRW"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                if data.get("result") == "success":
                    rates = data.get("rates", {})
                    usd_krw = 1 / rates.get("USD", 1)
                    jpy_krw = 1 / rates.get("JPY", 1) * 100
                    cny_krw = 1 / rates.get("CNY", 1)
                    eur_krw = 1 / rates.get("EUR", 1)
                    gbp_krw = 1 / rates.get("GBP", 1)
                    return {
                        "USD": f"{usd_krw:,.2f}",
                        "JPY": f"{jpy_krw:,.2f}",
                        "CNY": f"{cny_krw:,.2f}",
                        "EUR": f"{eur_krw:,.2f}",
                        "GBP": f"{gbp_krw:,.2f}"
                    }
    except Exception as e:
        logger.error(f"환율 정보 조회 실패: {e}")
        return None

# [수정] 통화 정보 반환 및 변수 정리
async def fetch_stock_data(ticker_symbol: str):
    """주식 정보와 통화를 함께 가져옵니다."""
    try:
        def get_data_sync():
            ticker = yf.Ticker(ticker_symbol)
            info = ticker.info
            history = ticker.history(period="2d")
            return info, history

        stock_info, stock_history = await asyncio.to_thread(get_data_sync)
        
        if len(stock_history) < 2: return None

        currency = stock_info.get("currency", "USD")
        prev_close = stock_history['Close'].iloc[0]
        current_price = stock_history['Close'].iloc[1]
        
        change_value = current_price - prev_close
        change_percent = (change_value / prev_close) * 100
        sign = "▲" if change_value > 0 else "▼" if change_value < 0 else ""
        
        # [수정] 반환하는 딕셔너리에 'currency' 키를 추가합니다.
        return {
            "price": current_price,
            "change": f"{sign} {abs(change_value):,.2f}", # 변수명 통일
            "change_percent": f"({change_percent:+.2f}%)",
            "currency": currency # 누락되었던 통화 정보 추가!
        }
    except Exception as e:
        logger.error(f"주식 정보 조회 실패 ({ticker_symbol}): {e}")
        return None

async def create_briefing_embed() -> discord.Embed:
    """금융 데이터를 조회하고 통화에 맞는 단위를 붙여 Embed를 생성합니다."""
    rates_task = fetch_exchange_rates()
    stocks_tasks = {name: fetch_stock_data(ticker) for name, ticker in STOCK_TICKERS.items()}
    
    rates_result = await rates_task
    stocks_results = await asyncio.gather(*stocks_tasks.values())
    stocks_data = dict(zip(stocks_tasks.keys(), stocks_results))

    today_str = datetime.now(KST).strftime("%Y년 %m월 %d일")
    embed = discord.Embed(title=f"📈 경제 브리핑 ({today_str})", description="현재 시점의 주요 경제 지표입니다.", color=BOT_EMBED_COLOR)

    if rates_result:
        exchange_value = (f"🇺🇸 **달러**: {rates_result['USD']}원\n🇪🇺 **유로**: {rates_result['EUR']}원\n🇬🇧 **파운드**: {rates_result['GBP']}원\n🇯🇵 **엔(100)**: {rates_result['JPY']}원\n🇨🇳 **위안**: {rates_result['CNY']}원")
        embed.add_field(name="💱 주요 환율 (매매기준율)", value=exchange_value, inline=False)
    else:
        embed.add_field(name="💱 주요 환율", value="정보를 가져오는 데 실패했습니다.", inline=False)
        
    stock_value = ""
    currency_symbols = {"USD": "$", "KRW": "원"}
    
    for name, data in stocks_data.items():
        if data:
            price = data['price']
            currency_code = data.get('currency', 'USD') # data에 currency가 있는지 확인
            symbol = currency_symbols.get(currency_code, currency_code)
            price_format = "{:,.2f}" if currency_code == "USD" else "{:,.0f}"
            formatted_price = price_format.format(price)
            
            stock_value += f"**{name}**: {formatted_price}{symbol} ({data['change']} {data['change_percent']})\n"
        else:
            stock_value += f"**{name}**: 정보 조회 실패\n"
    
    if stock_value:
         embed.add_field(name="🌍 주요 주식 (전일 종가 대비)", value=stock_value, inline=False)

    embed.set_footer(text="데이터 출처: er-api, Yahoo Finance | 정보는 실제와 차이가 있을 수 있습니다.")
    return embed

# --- 배경 작업을 위한 Cog 클래스 ---
class FinanceAgentCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if FINANCE_CHANNEL_ID == 0:
            logger.warning("[Finance] FINANCE_CHANNEL_ID가 설정되지 않아 자동 브리핑 기능이 비활성화됩니다.")
        else:
            self.daily_briefing.start()

    def cog_unload(self):
        if self.daily_briefing.is_running():
            self.daily_briefing.cancel()

    @tasks.loop(time=time(hour=9, minute=0, tzinfo=KST))
    async def daily_briefing(self):
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(FINANCE_CHANNEL_ID)
        if not channel: return
        logger.info("[Finance] 오전 9시 자동 금융 브리핑을 시작합니다.")
        embed = await create_briefing_embed()
        await channel.send(embed=embed)

    @daily_briefing.before_loop
    async def before_daily_briefing(self):
        logger.info("[Finance] 금융 브리핑 루프가 준비되었습니다. 매일 오전 9시를 기다립니다.")

async def setup(bot: commands.Bot):
    await bot.add_cog(FinanceAgentCog(bot))
