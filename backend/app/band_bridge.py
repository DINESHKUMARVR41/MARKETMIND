import httpx
from .config import BAND_AGENT_API_KEY, BAND_CHAT_ID, BAND_BASE_URL

async def publish_event(agent, content, metadata=None):
    if not (BAND_AGENT_API_KEY and BAND_CHAT_ID):
        return {'connected':False,'reason':'Set BAND_AGENT_API_KEY and BAND_CHAT_ID to publish to a Band room.'}
    headers={'X-API-Key':BAND_AGENT_API_KEY,'Content-Type':'application/json'}
    body={'event':{'content':f'[{agent}] {content}','message_type':'thought','metadata':metadata or {}}}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r=await client.post(f'{BAND_BASE_URL}/chats/{BAND_CHAT_ID}/events',headers=headers,json=body)
            r.raise_for_status()
        return {'connected':True,'status':'published'}
    except Exception as e: return {'connected':False,'reason':str(e)[:220]}
