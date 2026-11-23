import httpx, math
from .config import ALPHA_VANTAGE_API_KEY

DEMO = {
 'NVDA': {'price': 145.20, 'change_pct': 1.42, 'volume': 38200000, 'high': 147.10, 'low': 142.80, 'source':'DEMO_FIXTURE'},
 'AAPL': {'price': 232.10, 'change_pct': 0.63, 'volume': 42100000, 'high': 233.80, 'low': 229.90, 'source':'DEMO_FIXTURE'},
 'MSFT': {'price': 506.30, 'change_pct': -0.34, 'volume': 18900000, 'high': 510.20, 'low': 503.10, 'source':'DEMO_FIXTURE'},
 'TSLA': {'price': 338.40, 'change_pct': 2.18, 'volume': 55700000, 'high': 341.00, 'low': 329.50, 'source':'DEMO_FIXTURE'},
 'AMZN': {'price': 221.70, 'change_pct': -0.72, 'volume': 27400000, 'high': 224.10, 'low': 220.20, 'source':'DEMO_FIXTURE'},
 'GOOGL': {'price': 182.60, 'change_pct': 0.21, 'volume': 16400000, 'high': 184.00, 'low': 181.30, 'source':'DEMO_FIXTURE'},
}

async def get_quote(symbol: str):
    symbol=symbol.upper().strip()
    if ALPHA_VANTAGE_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                r=await client.get('https://www.alphavantage.co/query',params={'function':'GLOBAL_QUOTE','symbol':symbol,'apikey':ALPHA_VANTAGE_API_KEY})
                data=r.json().get('Global Quote',{})
                if data and data.get('05. price'):
                    return {'symbol':symbol,'price':float(data['05. price']),'change_pct':float(data.get('10. change percent','0').replace('%','')),'volume':int(data.get('06. volume','0')),'high':float(data.get('03. high','0')),'low':float(data.get('04. low','0')),'source':'ALPHA_VANTAGE','freshness':'Provider response; free-tier quote may be delayed'}
        except Exception: pass
    d=DEMO.get(symbol)
    if not d: raise ValueError(f'No quote available for {symbol}. Add an Alpha Vantage key or use NVDA, AAPL, MSFT, TSLA, AMZN, GOOGL.')
    return {'symbol':symbol,**d,'freshness':'Illustrative demo fixture — not live market data'}
