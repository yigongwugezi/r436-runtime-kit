"""GRADE Grading Agent — 自动批改，4维评分+5类错误归类，源自 GRADE (BEA 2025)"""
import json, logging, os, sqlite3, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

_env = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env)
logger = logging.getLogger("grade-agent")
app = FastAPI(title="GRADE Grading Agent", version="2.0.0")

DB = Path(__file__).parent / "data" / "grades.db"
DB.parent.mkdir(parents=True, exist_ok=True)

def _db():
    with sqlite3.connect(str(DB)) as c:
        c.execute("CREATE TABLE IF NOT EXISTS records (id INTEGER PRIMARY KEY AUTOINCREMENT, sid TEXT, qid TEXT, data TEXT, at TEXT)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sid ON records(sid)")
        c.commit()
    return sqlite3.connect(str(DB))

class LLM:
    def chat(self, msgs, t=0.1, mt=2048):
        k = os.getenv("LLM_API_KEY",""); b = os.getenv("LLM_BASE_URL","https://spark-api-open.xf-yun.com/x2"); m = os.getenv("LLM_MODEL","spark-x")
        if not k: return ""
        try:
            r = httpx.post(f"{b}/chat/completions", headers={"Authorization":f"Bearer {k}","Content-Type":"application/json"}, json={"model":m,"messages":msgs,"temperature":t,"max_tokens":mt}, timeout=60)
            if r.status_code==200: return r.json()["choices"][0]["message"]["content"]
        except: pass
        return ""
llm = LLM()

class Req(BaseModel):
    student_id: str=""; question_id: str=""; question_type: str="shortanswer"
    stem: str=""; options: list[str]=[]; correct: str=""; reference_answer: str=""
    explanation: str=""; scoring_rubric: list[dict]=[]; knowledge_points: list[str]=[]
    student_answer: str=""; difficulty: str="medium"

ERROR_LABEL = {"concept":"概念错误","calculation":"计算失误","misreading":"审题偏差","method":"方法不当","forgetting":"知识遗忘","null":"无"}
DIMS = [{"n":"reasoning","l":"思路正确性","w":0.4},{"n":"completeness","l":"步骤完整性","w":0.3},{"n":"calculation","l":"计算准确性","w":0.2},{"n":"expression","l":"表达规范性","w":0.1}]

@app.get("/health")
def health(): return {"status":"ok","agent":"grade-agent"}

@app.post("/api/grade/assess")
def assess(req: Req):
    if not req.student_answer.strip(): raise HTTPException(400,"Answer required")
    # 选择题/判断题 → 规则直判
    if req.question_type=="choice":
        ok = req.student_answer.strip().upper()[:1]==req.correct.strip().upper()[:1]
        r = {"student_id":req.student_id,"question_id":req.question_id,"question_type":req.question_type,"student_answer":req.student_answer,"total_score":100 if ok else 0,"dimension_scores":{d["n"]:100 if ok else 0 for d in DIMS},"error_type":"null" if ok else "concept","error_label":ERROR_LABEL["null" if ok else "concept"],"error_explanation":"" if ok else f"正确答案 {req.correct}","suggestions":[] if ok else ["回顾相关概念"],"strengths":[],"knowledge_points":req.knowledge_points,"source":"rule_based","quality_status":"passed","timestamp":int(time.time())}
    elif req.question_type=="truefalse":
        ok = req.student_answer.strip().lower() in ("true","对","正确","yes","t") == (req.correct.lower() in ("true","对","正确","yes","t"))
        r = {"student_id":req.student_id,"question_id":req.question_id,"question_type":req.question_type,"student_answer":req.student_answer,"total_score":100 if ok else 0,"dimension_scores":{d["n"]:100 if ok else 0 for d in DIMS},"error_type":"null" if ok else "misreading","error_label":ERROR_LABEL["null" if ok else "misreading"],"error_explanation":"" if ok else req.explanation,"suggestions":[] if ok else ["仔细审题"],"strengths":[],"knowledge_points":req.knowledge_points,"source":"rule_based","quality_status":"passed","timestamp":int(time.time())}
    else:
        # LLM 批改
        prompt = f"批改作答。题目({req.question_type}):{req.stem}\n参考答案:{req.reference_answer or req.correct}\n解析:{req.explanation}\n学生作答:{req.student_answer}\n\n输出JSON:{{\"total_score\":0-100,\"dimension_scores\":{{\"reasoning\":0-100,\"completeness\":0-100,\"calculation\":0-100,\"expression\":0-100}},\"error_type\":\"concept|calculation|misreading|method|forgetting|null\",\"error_explanation\":\"原因\",\"suggestions\":[],\"strengths\":[]}}"
        raw = llm.chat([{"role":"system","content":"你是批改专家。只输出JSON。"},{"role":"user","content":prompt}])
        if raw:
            try:
                s=raw.find("{"); e=raw.rfind("}")+1
                if s>=0 and e>s: p=json.loads(raw[s:e])
                r = {"student_id":req.student_id,"question_id":req.question_id,"question_type":req.question_type,"student_answer":req.student_answer,"total_score":int(p.get("total_score",0)),"dimension_scores":p.get("dimension_scores",{}),"error_type":p.get("error_type","null"),"error_label":ERROR_LABEL.get(p.get("error_type","null"),"无"),"error_explanation":p.get("error_explanation",""),"suggestions":p.get("suggestions",[]),"strengths":p.get("strengths",[]),"knowledge_points":req.knowledge_points,"source":"llm_generated","quality_status":"passed","timestamp":int(time.time())}
            except: r = {"total_score":None,"error":"parse_failed","source":"rule_based_fallback"}
        else:
            r = {"total_score":None,"error":"llm_unavailable","source":"rule_based_fallback"}

    # Save
    now = datetime.now(timezone.utc).isoformat()
    with _db() as db:
        db.execute("INSERT INTO records(sid,qid,data,at) VALUES(?,?,?,?)",(req.student_id,req.question_id,json.dumps(r,ensure_ascii=False),now))
        db.commit()
    return r

@app.get("/api/grade/stats/{sid}")
def stats(sid: str):
    with _db() as db:
        rows = db.execute("SELECT data FROM records WHERE sid=?",(sid,)).fetchall()
    if not rows: return {"student_id":sid,"total_questions":0}
    grades = [json.loads(r[0]) for r in rows]
    scores = [g["total_score"] for g in grades if g.get("total_score") is not None]
    ec = {}
    for g in grades:
        et = g.get("error_type","null")
        if et!="null": ec[et]=ec.get(et,0)+1
    return {"student_id":sid,"total_questions":len(grades),"average_score":round(sum(scores)/max(1,len(scores)),1) if scores else None,"error_distribution":ec,"weak_knowledge_points":[]}

@app.get("/api/grade/records/{sid}")
def records(sid: str, limit: int=20):
    with _db() as db:
        return [{"grading":json.loads(r[0]),"recorded_at":r[1]} for r in db.execute("SELECT data,at FROM records WHERE sid=? ORDER BY at DESC LIMIT ?",(sid,limit))]
