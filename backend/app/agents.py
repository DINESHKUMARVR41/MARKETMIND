import json, re
from google import genai
from google.genai import types
from .config import GEMINI_API_KEY, GEMINI_MODEL

async def ask_agent(role, instruction, context):
    if GEMINI_API_KEY:
        try:
            client=genai.Client(api_key=GEMINI_API_KEY)
            prompt=f'''You are {role}, a specialist in an investment committee simulation. {instruction}\n\nContext: {json.dumps(context)}\n\nReturn concise, evidence-aware JSON only with keys: headline, argument, risks, confidence (integer 0-100), evidence (array of strings). Never invent news or claim live data not supplied. This is educational simulation, not financial advice.'''
            response=await client.aio.models.generate_content(model=GEMINI_MODEL,contents=prompt,config=types.GenerateContentConfig(response_mime_type='application/json',temperature=0.35))
            data=json.loads(response.text)
            data['agent']=role; data['mode']='GEMINI'
            return data
        except Exception as e:
            err=str(e)[:180]
    else: err='GEMINI_API_KEY not configured'
    return fallback(role, context, err)

def fallback(role, c, reason=''):
    q=c.get('quote',{}); ch=float(q.get('change_pct',0)); price=float(q.get('price',0)); sym=q.get('symbol','ASSET')
    if role=='Market Analyst':
        data=('Price momentum is positive' if ch>=0 else 'Price momentum is negative')+f' for {sym}, with a session change of {ch:.2f}%. Volume and intraday range are context only; no independent news feed was verified.'
        conf=max(35,min(75,55+int(ch*3)))
        headline='Momentum snapshot assembled'; risks=['Single-session movement is not a trend','No verified company-news catalyst in this run']
    elif role=='Bull Advocate':
        data=f'The constructive case is that {sym} is showing {ch:.2f}% session momentum. If the move is supported by durable fundamentals and follow-through, a small staged position could participate without overcommitting.'
        conf=62 if ch>=0 else 43; headline='Conditional upside thesis'; risks=['Momentum can reverse','No fundamental valuation model was run']
    elif role=='Bear Advocate':
        data=f'The counter-case for {sym}: a single-session move of {ch:.2f}% is weak evidence. Chasing a green candle can create poor entry risk; a negative move may reflect unresolved uncertainty. Wait for confirmation.'
        conf=68; headline='Challenge: evidence is thin'; risks=['No earnings or valuation verification','Potential gap and volatility risk']
    else:
        data='Risk review uses fixed portfolio constraints, not model judgement. Proposal must stay within cash, per-position, and total-exposure limits.'
        conf=90; headline='Rule-based risk review'; risks=['Market gaps can exceed modeled loss','Demo capital is not connected to a broker']
    return {'agent':role,'headline':headline,'argument':data,'risks':risks,'confidence':conf,'evidence':[f'{sym} quote source: {q.get("source","unknown")}',f'Observed session change: {ch:.2f}%'],'mode':'RULE_FALLBACK','fallback_reason':reason}
