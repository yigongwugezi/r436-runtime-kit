"""Socratic Profiler — 学生画像构建服务，源自 Socratic Education System (MIT)"""
import json, logging, os, sqlite3, uuid, re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

_env = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env)
logger = logging.getLogger("socratic-profiler")
app = FastAPI(title="Socratic Profiler", version="2.0.0")

DB = Path(__file__).parent / "data" / "profiles.db"
DB.parent.mkdir(parents=True, exist_ok=True)

def _db():
    with sqlite3.connect(str(DB)) as c:
        c.execute("CREATE TABLE IF NOT EXISTS profiles (id TEXT PRIMARY KEY, data TEXT, ver INT DEFAULT 1, created TEXT, updated TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS weakness (id INTEGER PRIMARY KEY AUTOINCREMENT, sid TEXT, log TEXT, at TEXT)")
        c.commit()
    return sqlite3.connect(str(DB))

class LLM:
    def chat(self, msgs, t=0.2, mt=2048):
        k = os.getenv("LLM_API_KEY",""); b = os.getenv("LLM_BASE_URL","https://spark-api-open.xf-yun.com/x2"); m = os.getenv("LLM_MODEL","spark-x")
        if not k: return ""
        try:
            r = httpx.post(f"{b}/chat/completions", headers={"Authorization":f"Bearer {k}","Content-Type":"application/json"}, json={"model":m,"messages":msgs,"temperature":t,"max_tokens":mt}, timeout=60)
            if r.status_code==200: return r.json()["choices"][0]["message"]["content"]
        except: pass
        return ""

llm = LLM()

class Note(BaseModel):
    student_id: str=""; session_id: str=""; background: str=""; knowledge_base: str=""
    learning_goal: str=""; time_budget: str=""; cognitive_preference: str=""

class Feedback(BaseModel):
    student_id: str; error_types: list[str]=[]; weak_topics: list[str]=[]; mastery_scores: dict[str,int]={}

DIMS = ["major_background","knowledge_base","learning_goal","cognitive_style","error_patterns","learning_progress"]
LABELS = {"major_background":"专业背景","knowledge_base":"知识基础","learning_goal":"学习目标","cognitive_style":"认知风格","error_patterns":"易错点","learning_progress":"学习进度"}

def _build_dim(key, value, score=50, conf=0.5, expl="", ev="", src="inferred"):
    return {"key":key,"label":LABELS.get(key,key),"value":value or "待补充","score":max(0,min(100,score)),"confidence":max(0,min(1,conf)),"explanation":expl or value or "","evidence":ev,"source":src}

@app.get("/health")
def health(): return {"status":"ok","agent":"socratic-profiler"}

@app.post("/api/profile/analyze")
def analyze(note: Note):
    sid = note.student_id or f"s_{uuid.uuid4().hex[:8]}"
    # LLM 画像
    prompt = f"你是教育心理学家。根据以下信息输出6维画像JSON：\n背景:{note.background}\n基础:{note.knowledge_base}\n目标:{note.learning_goal}\n偏好:{note.cognitive_preference}\n\n每个维度含value/score/confidence/explanation/evidence/source。只输出JSON。"
    raw = llm.chat([{"role":"system","content":"你是教育心理学家。只输出JSON。"},{"role":"user","content":prompt}])
    dims = {}
    if raw:
        try:
            s=raw.find("{"); e=raw.rfind("}")+1
            if s>=0 and e>s: parsed=json.loads(raw[s:e])
            for k in DIMS:
                d=parsed.get(k,{})
                dims[k]=_build_dim(k,str(d.get("value","")),int(d.get("score",50)),float(d.get("confidence",0.5)),str(d.get("explanation","")),str(d.get("evidence","")),str(d.get("source","llm_generated")))
        except: pass
    # 兜底
    if not dims:
        dims={k:_build_dim(k,getattr(note,k.replace("major_background","background").replace("knowledge_base","knowledge_base").replace("learning_goal","learning_goal").replace("cognitive_style","cognitive_preference").replace("error_patterns",""),""),src="rule_based_fallback") for k in DIMS}
        if note.background: dims["major_background"]=_build_dim("major_background",note.background,82,0.92,"从对话提取","", "user_input")

    now = datetime.now(timezone.utc).isoformat()
    profile = {"student_id":sid,"dimensions":dims,"version":1,"created_at":now,"updated_at":now}
    with _db() as db:
        db.execute("INSERT OR REPLACE INTO profiles VALUES(?,?,?,?,?)",(sid,json.dumps(profile,ensure_ascii=False),1,now,now))
        db.commit()
    return profile

@app.post("/api/profile/update")
def update(fb: Feedback):
    with _db() as db:
        row = db.execute("SELECT data FROM profiles WHERE id=?",(fb.student_id,)).fetchone()
        if not row: raise HTTPException(404,"Profile not found")
        profile = json.loads(row[0])
        dims = profile["dimensions"]
        if fb.error_types or fb.weak_topics:
            e = dims.get("error_patterns",_build_dim("error_patterns",""))
            e["value"]="、".join(fb.weak_topics[:8]) or "待诊断"
            e["score"]=max(30,e.get("score",50)-len(fb.error_types)*5)
            e["confidence"]=0.85; e["source"]="grading_feedback"
            dims["error_patterns"]=e
        profile["dimensions"]=dims; profile["updated_at"]=datetime.now(timezone.utc).isoformat()
        db.execute("UPDATE profiles SET data=?,ver=ver+1,at=? WHERE id=?",(json.dumps(profile,ensure_ascii=False),profile["updated_at"],fb.student_id))
        db.execute("INSERT INTO weakness(sid,log,at) VALUES(?,?,?)",(fb.student_id,json.dumps({"error_types":fb.error_types,"weak_topics":fb.weak_topics},ensure_ascii=False),profile["updated_at"]))
        db.commit()
    return profile

@app.get("/api/profile/{sid}")
def get_profile(sid: str):
    with _db() as db:
        row = db.execute("SELECT data FROM profiles WHERE id=?",(sid,)).fetchone()
        if row: return json.loads(row[0])
    raise HTTPException(404,"Not found")

@app.get("/api/profile/{sid}/history")
def history(sid: str):
    with _db() as db:
        return [{"log":json.loads(r[0]),"at":r[1]} for r in db.execute("SELECT log,at FROM weakness WHERE sid=? ORDER BY at DESC LIMIT 20",(sid,))]
