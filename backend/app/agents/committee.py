from app.services.llm import generate_result
from app.services.band_bridge import send_handoff
from app.services.news import search_news
from pathlib import Path
from datetime import datetime, timezone

AGENTS=[
 {'id':'analyst','name':'Market Analyst','role':'Quantitative research','color':'cyan','description':'Reads price action, valuation and momentum.'},
 {'id':'news','name':'News Intelligence','role':'Catalyst research','color':'violet','description':'Searches current news coverage and extracts catalysts.'},
 {'id':'bull','name':'Bull Advocate','role':'Upside thesis','color':'green','description':'Builds the strongest evidence-backed upside case.'},
 {'id':'bear','name':'Bear Challenger','role':'Downside thesis','color':'rose','description':'Stress-tests assumptions and identifies downside.'},
 {'id':'risk','name':'Risk Guardian','role':'Independent risk control','color':'amber','description':'Applies hard portfolio and position constraints.'},
 {'id':'chair','name':'Portfolio Chair','role':'Decision synthesis','color':'blue','description':'Synthesizes the committee into a final decision.'}
]

def load_skill(name):
    path=Path(__file__).resolve().parents[1]/'skills'/name/'SKILL.md'
    try: return path.read_text(encoding='utf-8')
    except Exception: return ''

def run_committee(req, quote):
    sym=req.symbol.upper(); price=quote['price']; pct=quote['change_pct']; amount=req.investment_amount
    events=[]; handoffs=[]; model_calls=[]
    def emit(agent,stage,title,body,meta,evidence=None,confidence=None,start_time=None,completion_time=None,status='completed'):
        now=datetime.now(timezone.utc).isoformat()
        start=start_time or now
        if status == 'completed' and not meta.get('live'):
            status='completed_with_fallback'
        event={'agent':agent,'stage':stage,'title':title,'body':body,'confidence':confidence,'provider':meta['provider'],'live_reasoning':meta['live'],'provider_error':meta.get('error'),
          'execution_status':status,'started_at':start,'completed_at':completion_time or now,'evidence_references':evidence or []}
        events.append(event)
        model_calls.append({'agent':agent,'provider':meta['provider'],'live_reasoning':meta['live'],'status_code':meta.get('status_code'),'error_code':meta.get('error_code'),'error':meta.get('error'),'started_at':start,'completed_at':completion_time or now,'execution_status':status})
    def think(role,system,prompt,fallback):
        result=generate_result(system,prompt,use_lyzr=True,agent_role=role)
        result['text']=result['text'].strip() if result['text'] else fallback
        return result
    def handoff(sender,recipient,payload):
        result={'from':sender,'to':recipient,'payload':payload[:500]}
        result['band']=send_handoff(sender,recipient,result['payload']); handoffs.append(result)
    analyst_fallback=(f'{sym} is quoted at {quote["currency"]} {price:,.2f}, session move {pct:+.2f}%. Source: {quote["source"]}. '
      f'Volume: {quote.get("volume",0):,}. The feed does not supply complete fundamentals. Treat this as a price snapshot, not a forecast. '
      'Review trend persistence, liquidity, earnings revisions and valuation before acting.')
    analyst_start=datetime.now(timezone.utc).isoformat()
    analyst=think('analyst','You are a cautious equity research analyst. Separate observed facts from assumptions; never invent data.\n\nFinch-style skill:\n'+load_skill('market-research'),
      f'Analyze {sym} ({req.company}). Verified quote payload: {quote}. Horizon: {req.horizon}. Give observations, limitations and three watchpoints.',analyst_fallback)
    analyst_status='completed' if analyst['text'] else 'failed'
    emit('analyst','research','Market structure mapped',analyst['text'],analyst,[{'type':'quote','source':quote['source'],'symbol':sym,'timestamp':quote.get('timestamp')}],None,analyst_start,datetime.now(timezone.utc).isoformat(),analyst_status)
    news_start=datetime.now(timezone.utc).isoformat()
    try:
        news_data=search_news(req.company or sym,sym)
    except Exception as exc:
        news_data={'source':'GDELT DOC 2.0','status':'PROVIDER_UNAVAILABLE','is_live':False,'articles':[],'count':0,'error':str(exc)[:220],'warning':'Live news lookup failed; do not infer that no news exists.'}
    news_evidence=[{'type':'article','title':a.get('title'),'source':a.get('source'),'url':a.get('url'),'published_at':a.get('published_at')} for a in news_data.get('articles',[])]
    headlines='\n'.join(f"- {a.get('title')} | {a.get('source')} | {a.get('published_at')} | {a.get('url')}" for a in news_data.get('articles',[])) or 'No current headlines were returned.'
    news=think('news','You are a financial catalyst researcher. Only cite supplied articles; distinguish headline claims from verified facts.\n\nFinch-style research skill:\n'+load_skill('market-research'),
      f'Assess catalysts for {sym} ({req.company}). Current article search source={news_data.get("source")}, live={news_data.get("is_live")}. Articles:\n{headlines}\nIdentify themes, possible event risks, and what must be verified. Never invent article content.',
      (f'Live news search returned {news_data.get("count",0)} articles.' if news_data.get('is_live') else 'Live news search unavailable. ') + ' Do not infer that no news exists. Verify earnings, guidance, regulatory notices and sector developments from primary sources.')
    emit('news','research','Catalyst scan completed',news['text'],news,news_evidence,None,news_start,datetime.now(timezone.utc).isoformat(),'completed')
    handoff('analyst','bull',analyst['text']); handoff('news','bull',news['text'])
    bull_start=datetime.now(timezone.utc).isoformat()
    bull=think('bull','You are the bullish member of an investment committee. Make a strong but evidence-bounded case. No fabricated facts.',
      f'Build the upside case for {sym}. Analyst: {analyst["text"]}. News brief: {news["text"]}. Quote change: {pct:+.2f}%. Provide thesis, catalysts, invalidation and conviction 0-100.',
      f'UPSIDE CASE: {sym} may benefit if its core growth narrative converts into durable earnings and the trend persists. This is a hypothesis, not a verified forecast. Invalidation: weaker guidance, margin compression or sustained loss of momentum.')
    emit('bull','debate','Bull case submitted',bull['text'],bull,[{'type':'analyst_output','agent':'analyst'},{'type':'news_output','agent':'news'}],None,bull_start,datetime.now(timezone.utc).isoformat())
    handoff('bull','bear',bull['text'])
    bear_start=datetime.now(timezone.utc).isoformat()
    bear=think('bear','You are a skeptical short-side analyst. Challenge the bull case with specific risks. Do not fabricate news or numbers.',
      f'Challenge this bull case for {sym}: {bull["text"]}. Quote: {quote}. Headlines: {headlines}. Consider valuation, downside, concentration, macro and missing evidence.',
      f'DOWNSIDE CASE: the thesis may already be priced in. A {pct:+.2f}% session move is not proof of durable momentum. Valuation, execution and macro sensitivity can compress multiples. Missing verified filings and detailed fundamentals are material blind spots.')
    emit('bear','debate','Bear case challenges assumptions',bear['text'],bear,[{'type':'bull_output','agent':'bull'},{'type':'quote','symbol':sym},{'type':'news_status','status':news_data.get('status')}],None,bear_start,datetime.now(timezone.utc).isoformat())
    handoff('bear','risk',bear['text'])
    risk_pct=min(req.max_position_pct,8 if req.risk_tolerance=='conservative' else 15 if req.risk_tolerance=='balanced' else 20)
    allocation_cap=round(req.portfolio_value*risk_pct/100,2)
    approved_amount=round(min(amount,allocation_cap),2)
    flags=[]
    if approved_amount < amount: flags.append(f'Requested amount capped from ${amount:,.2f} to ${approved_amount:,.2f} ({risk_pct}% of ${req.portfolio_value:,.2f} portfolio).')
    if quote.get('is_demo'): flags.append('Synthetic quote: paper simulation only; live market price unavailable.')
    if not news_data.get('is_live'): flags.append('Live news unavailable; catalyst coverage is incomplete.')
    if news_data.get('is_live') and not news_data.get('count'): flags.append('News provider returned zero matching articles; this does not prove no relevant news exists.')
    if abs(pct)>5: flags.append('Elevated single-session move; consider waiting for confirmation.')
    if req.max_position_pct>risk_pct: flags.append(f'Position limit reduced to {risk_pct}% under {req.risk_tolerance} policy.')
    risk_ok=not (req.risk_tolerance=='conservative' and abs(pct)>3) and price>0 and amount<=1000000
    risk_fallback=f"RISK REVIEW: {'PASS for paper simulation' if risk_ok else 'VETO'}. Position policy ceiling {risk_pct}%. {' '.join(flags) if flags else 'No deterministic policy breach detected.'} This is not a probability-of-loss estimate."
    risk_start=datetime.now(timezone.utc).isoformat()
    risk=think('risk','You are an independent risk officer. You may veto. Prioritize capital preservation. Your prose cannot override deterministic gate.\n\nFinch risk skill:\n'+load_skill('risk-check'),
      f'Evaluate {sym}. Requested amount {amount}; portfolio value {req.portfolio_value}; hard allowed amount {approved_amount}; max position {risk_pct}%. Risk tolerance {req.risk_tolerance}. Quote {quote}. Bull: {bull["text"]}. Bear: {bear["text"]}. Live news={news_data.get("is_live")}. Explain risks and controls.',risk_fallback)
    emit('risk','control','Independent risk gate evaluated',risk['text'],risk,[{'type':'bull_output','agent':'bull'},{'type':'bear_output','agent':'bear'},{'type':'risk_policy','position_cap_pct':risk_pct,'risk_tolerance':req.risk_tolerance,'gate_pass':risk_ok}],None,risk_start,datetime.now(timezone.utc).isoformat())
    handoff('risk','chair',risk['text'])
    # Transparent rule-based committee signal, never represented as predictive accuracy.
    bull_score=max(35,min(85,62+max(-8,min(8,pct))*1.8)); bear_score=max(35,min(90,61+max(-8,min(8,-pct))*1.8+(5 if (quote.get('pe') or 0)>45 else 0)))
    decision='REJECT' if not risk_ok else ('BUY' if bull_score>=bear_score+1 else 'HOLD')
    chair_start=datetime.now(timezone.utc).isoformat()
    confidence=None
    chair=think('chair','You are chair of an investment committee. Give a balanced decision, never claim certainty, and obey deterministic risk veto.',
      f'Decide BUY/HOLD/REJECT for {sym}. Bull: {bull["text"]}. Bear: {bear["text"]}. Risk: {risk["text"]}. Hard risk gate pass={risk_ok}. Rule-based signal={decision}. Live quote={not quote.get("is_demo")}; live news={news_data.get("is_live")}. Give rationale, revisit triggers and data caveats. Do not change the hard decision.',
      f'COMMITTEE DECISION: {decision}. The decision follows the transparent rule-based committee signal and deterministic risk gate. Revisit after confirming price, primary filings, earnings guidance and catalyst calendar. Paper simulation only; not investment advice.')
    emit('chair','decision',f'Committee decision: {decision}',chair['text'],chair,[{'type':'bull_output','agent':'bull'},{'type':'bear_output','agent':'bear'},{'type':'risk_output','agent':'risk','gate_pass':risk_ok},{'type':'deterministic_decision','decision':decision}],None,chair_start,datetime.now(timezone.utc).isoformat())
    handoff('chair','analyst',f'Decision {decision}; monitor invalidation and refresh evidence.')
    return {'symbol':sym,'company':req.company,'quote':quote,'news':news_data,'investment_amount':approved_amount,'requested_investment_amount':amount,'portfolio_value':req.portfolio_value,'allocation_cap_amount':allocation_cap,'horizon':req.horizon,'risk_tolerance':req.risk_tolerance,
      'decision':decision,'confidence':confidence,'risk_approved':risk_ok,'suggested_allocation_pct':risk_pct,'suggested_shares':round(approved_amount/price,6) if decision=='BUY' and price else 0,
      'agents':AGENTS,'events':events,'handoffs':handoffs,'theses':{'bull':bull['text'],'bear':bear['text']},'risk_report':risk['text'],'chair_report':chair['text'],
      'data_caveats':flags,'execution':'PAPER_ONLY','model_calls':model_calls,
      'integration_summary':{'live_quote':not quote.get('is_demo'),'live_news':news_data.get('is_live',False),'llm_agents':sum(1 for x in model_calls if x['live_reasoning']),'total_agents':6,
        'band_messages_sent':sum(1 for h in handoffs if h['band'].get('sent')),'band_handoffs_attempted':len(handoffs)}}
