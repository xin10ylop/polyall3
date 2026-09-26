"""Minimal Jev (TypeSafe System One via OpenRouter Decisions API) client with cost tracking."""
import os, json, requests, time
URL="https://openrouter.ai/api/alpha/decisions"
KEY=os.environ.get('OPENROUTER_API_KEY')
SPENT={'usd':0.0,'calls':0}
def decide(state, questions, model="~typesafe/jev-latest", tries=3):
    for i in range(tries):
        try:
            r=requests.post(URL,headers={"Authorization":f"Bearer {KEY}","Content-Type":"application/json","X-Title":"pm-research"},
                            json=dict(model=model,state=state,questions=questions),timeout=30)
            d=r.json()
            if 'answers' in d:
                SPENT['usd']+=float((d.get('usage') or {}).get('cost') or 0); SPENT['calls']+=1
                return d['answers']
            time.sleep(1+i)
        except Exception: time.sleep(1+i)
    return None
def same_event(a, b):
    ans=decide({"listing_A":a,"listing_B":b},{
        "same":{"type":"noul","instructions":"Do listing_A and listing_B refer to the same real-world sporting match (same competitors, same date)? Team names may be abbreviated, translated, or include suffixes like FC, W (women), U21, II/B (reserve teams).",
                "criteria":{"true":"Same match between the same two competitors","false":"Different match, different teams, or one is a women/youth/reserve team while the other is not"}}})
    return None if ans is None else ans['same']['noul']
