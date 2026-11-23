import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1]/'.env')
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.models import AnalyzeRequest
from app.database import init_db, save_run, save_trade, list_runs, get_run, list_trades, trade_exists_for_run
from app.services.market_data import get_quote, get_history
from app.services.news import search_news
from app.services.llm import provider_status
from app.services.band_bridge import status as band_status
from app.agents.committee import run_committee, AGENTS

app=FastAPI(title='MARKETMIND API',version='1.1.0',description='Six-agent investment committee with debate, risk gate and paper trading.')
app.add_middleware(CORSMiddleware,allow_origins=[os.getenv('FRONTEND_ORIGIN','http://localhost:5173'),'http://127.0.0.1:5173'],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
@app.on_event('startup')
def startup(): init_db()
@app.get('/api/health')
def health():
    return {'status':'ok','app':'MARKETMIND','agents':len(AGENTS),'providers':provider_status(),'market_data':{'yahoo_chart':'available_without_key_attempted_per_request','alpha_vantage_configured':bool(os.getenv('ALPHA_VANTAGE_API_KEY'))},'news':{'provider':'GDELT DOC 2.0','no_key_required':True},'band':band_status(),'adal_webhook_configured':bool(os.getenv('ADAL_WEBHOOK_URL')),'agent37_deployment_configured':bool(os.getenv('AGENT37_PUBLIC_URL')),'finch_skills':'local SKILL.md packs loaded by agent roles'}
@app.get('/api/agents')
def agents(): return AGENTS
@app.get('/api/quote/{symbol}')
def quote(symbol:str): return get_quote(symbol)
@app.get('/api/history-prices/{symbol}')
def price_history(symbol:str, range_:str='1mo', interval:str='1d'):
    try: return get_history(symbol,range_,interval)
    except Exception as exc: raise HTTPException(502,f'Live price history unavailable: {str(exc)[:180]}')
@app.get('/api/news/{symbol}')
def news(symbol:str, company:str=''):
    return search_news(company or symbol,symbol)
@app.post('/api/analyze')
def analyze(req:AnalyzeRequest):
    quote=get_quote(req.symbol)
    report=run_committee(req,quote)
    run_id=save_run(report); report['run_id']=run_id
    return report
@app.post('/api/paper-trade/{run_id}')
def paper_trade(run_id:int):
    run=get_run(run_id)
    if not run: raise HTTPException(404,'Analysis run not found')
    r=run['report']
    if r['decision']!='BUY' or not r['risk_approved']:
        raise HTTPException(400,'Paper order blocked: decision is not BUY or risk gate did not approve.')
    if trade_exists_for_run(run_id):
        raise HTTPException(409,'A paper trade has already been recorded for this analysis run.')
    q=r['quote']['price']; amount=r['investment_amount']; qty=round(amount/q,6)
    trade_id=save_trade(run_id,r['symbol'],'BUY',qty,q,amount)
    return {'trade_id':trade_id,'run_id':run_id,'symbol':r['symbol'],'side':'BUY','quantity':qty,'price':q,'amount':amount,'status':'PAPER','message':'Simulated order recorded. No real money moved.'}
@app.get('/api/history')
def history(): return list_runs()
@app.get('/api/history/{run_id}')
def history_detail(run_id:int):
    item=get_run(run_id)
    if not item: raise HTTPException(404,'Run not found')
    return item
@app.get('/api/trades')
def trades(): return list_trades()
@app.post('/api/adal/notify/{run_id}')
def adal_notify(run_id:int):
    import requests
    from app.database import get_run
    url=os.getenv('ADAL_WEBHOOK_URL')
    if not url: raise HTTPException(400,'Configure ADAL_WEBHOOK_URL first.')
    item=get_run(run_id)
    if not item: raise HTTPException(404,'Run not found')
    headers={'Content-Type':'application/json'}
    if os.getenv('ADAL_WEBHOOK_TOKEN'): headers['Authorization']='Bearer '+os.getenv('ADAL_WEBHOOK_TOKEN')
    try:
        res=requests.post(url,json={'event':'marketmind.analysis.completed','report':item['report']},headers=headers,timeout=12); res.raise_for_status()
        return {'sent':True,'status_code':res.status_code}
    except Exception as e: raise HTTPException(502,f'AdaL webhook failed: {e}')
