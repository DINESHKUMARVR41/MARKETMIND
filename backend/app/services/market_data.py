"""Market data adapters. Yahoo chart is a no-key convenience source; Alpha Vantage is the keyed fallback.
All returned values identify their source and synthetic fallbacks are explicitly flagged.
"""
import os
import requests
from datetime import datetime, timezone

DEMO = {
 "NVDA":{"price":186.42,"change":2.84,"change_pct":1.55,"volume":42100000,"pe":48.2,"sector":"Semiconductors","summary":"Synthetic sample only."},
 "AAPL":{"price":272.15,"change":-1.08,"change_pct":-0.39,"volume":31800000,"pe":31.4,"sector":"Consumer Technology","summary":"Synthetic sample only."},
 "MSFT":{"price":512.80,"change":3.26,"change_pct":0.64,"volume":19200000,"pe":35.1,"sector":"Software & Cloud","summary":"Synthetic sample only."},
 "TSLA":{"price":348.60,"change":-5.42,"change_pct":-1.53,"volume":55600000,"pe":102.0,"sector":"Automotive & Energy","summary":"Synthetic sample only."},
 "AMZN":{"price":231.75,"change":1.92,"change_pct":0.84,"volume":28700000,"pe":34.8,"sector":"E-commerce & Cloud","summary":"Synthetic sample only."}
}
HEADERS={'User-Agent':'Mozilla/5.0 MARKETMIND/1.0 (educational research app)'}

def _yahoo_quote(symbol):
    url=f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}'
    r=requests.get(url,params={'range':'5d','interval':'1d','events':'history'},headers=HEADERS,timeout=12)
    r.raise_for_status(); data=r.json()['chart']
    if data.get('error') or not data.get('result'): raise ValueError('No Yahoo chart result')
    result=data['result'][0]; meta=result.get('meta',{}); indicators=result.get('indicators',{}).get('quote',[{}])[0]
    closes=[x for x in (indicators.get('close') or []) if x is not None]
    price=float(meta.get('regularMarketPrice') or (closes[-1] if closes else 0))
    previous=float(meta.get('chartPreviousClose') or meta.get('previousClose') or (closes[-2] if len(closes)>1 else price))
    if not price: raise ValueError('Price missing')
    change=price-previous
    return {'symbol':symbol,'price':price,'change':change,'change_pct':(change/previous*100 if previous else 0),
      'volume':int((indicators.get('volume') or [0])[-1] or meta.get('regularMarketVolume') or 0),
      'currency':meta.get('currency','USD'),'exchange':meta.get('exchangeName'),'market_state':meta.get('marketState'),
      'sector':None,'pe':None,'summary':'Quote and volume from Yahoo Finance chart endpoint. Fundamentals are not included.',
      'source':'Yahoo Finance chart','is_demo':False,'data_timestamp':datetime.fromtimestamp(meta.get('regularMarketTime',datetime.now(timezone.utc).timestamp()),timezone.utc).isoformat(),
      'timestamp':datetime.now(timezone.utc).isoformat(),'disclaimer':'Convenience data endpoint; may be delayed, incomplete or unavailable. Not an exchange execution feed.'}

def _alpha_quote(symbol):
    key=os.getenv('ALPHA_VANTAGE_API_KEY')
    if not key: raise ValueError('Alpha Vantage key not configured')
    r=requests.get('https://www.alphavantage.co/query',params={'function':'GLOBAL_QUOTE','symbol':symbol,'apikey':key},timeout=12); r.raise_for_status()
    q=r.json().get('Global Quote',{})
    if not q or not q.get('05. price'): raise ValueError('Alpha Vantage returned no quote (possibly rate limited)')
    price=float(q['05. price']); change=float(q.get('09. change','0')); pct=float(q.get('10. change percent','0').replace('%',''))
    return {'symbol':symbol,'price':price,'change':change,'change_pct':pct,'volume':int(q.get('06. volume','0') or 0),'currency':'USD','sector':None,'pe':None,'summary':'Quote supplied by Alpha Vantage.','source':'Alpha Vantage','is_demo':False,'timestamp':datetime.now(timezone.utc).isoformat(),'disclaimer':'Check provider delay and plan limits before relying on this quote.'}

def get_quote(symbol):
    symbol=symbol.upper().strip()
    if not symbol.replace('.','').replace('-','').isalnum(): raise ValueError('Invalid ticker symbol')
    errors=[]
    for provider in (_yahoo_quote,_alpha_quote):
        try: return provider(symbol)
        except Exception as exc: errors.append(f'{getattr(provider, "__name__", provider.__class__.__name__)}: {str(exc)[:180]}')
    q=DEMO.get(symbol,{'price':100+sum(map(ord,symbol))%150,'change':1.2,'change_pct':0.8,'volume':12000000,'pe':None,'sector':'Demo universe','summary':'Synthetic sample quote; not live market data.'})
    return {'symbol':symbol,**q,'currency':'USD','source':'Synthetic demo data','timestamp':datetime.now(timezone.utc).isoformat(),'is_demo':True,'provider_errors':errors,'disclaimer':'SYNTHETIC DATA. Do not treat as a current market quote.'}

def get_history(symbol,range_='1mo',interval='1d'):
    symbol=symbol.upper().strip()
    r=requests.get(f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}',params={'range':range_,'interval':interval},headers=HEADERS,timeout=15); r.raise_for_status()
    result=r.json()['chart']['result'][0]; q=result['indicators']['quote'][0]
    points=[]
    for i,ts in enumerate(result.get('timestamp',[])):
        close=(q.get('close') or [None]*len(result.get('timestamp',[])))[i]
        if close is not None: points.append({'time':datetime.fromtimestamp(ts,timezone.utc).isoformat(),'close':close,'volume':(q.get('volume') or [None]*len(result.get('timestamp',[])))[i]})
    return {'symbol':symbol,'source':'Yahoo Finance chart','range':range_,'interval':interval,'points':points,'is_demo':False}
