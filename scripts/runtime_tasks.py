"""Small executable repair tasks derived from retained failures; stdlib only."""
from __future__ import annotations
import hashlib
import json

PRELUDE = "import json,sys,re,hashlib\n"
MAIN = """
try:
    value = solve(json.loads(sys.stdin.read()))
    print(json.dumps({"ok": True, "value": value}, ensure_ascii=False))
except Exception as exc:
    print(json.dumps({"ok": False, "error": type(exc).__name__}))
"""
def worker(body):
    return PRELUDE + body.strip() + "\n" + MAIN

def ok(value):
    return {"ok": True, "value": value}

def case(name, data, expected):
    return {"name": name, "input": data, "expected": expected}

def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def task_specs():
    tasks = []
    def add(task_id, contract, broken, partial, fixed, cases, incident, origin="observed_failure_minimal_reproduction"):
        tasks.append(dict(task_id=task_id, instruction=contract, initial=worker(broken),
                          partial=worker(partial), reference=worker(fixed), cases=cases,
                          source_incident=incident, origin=origin))
    add("jsonl-unicode",
        "修复 worker.py 的 solve(data)。data.text 是 JSONL 文本，只有 LF 分隔记录；"
        "接受 CRLF 和空行，字符串里的 U+2028/U+2029 必须原样保留。返回解析后的列表。"
        "任意非空记录无效时整个请求失败，不能跳过坏记录。保持 JSON stdin/stdout 接口。",
        "def solve(data):\n    return [json.loads(x) for x in data['text'].splitlines() if x.strip()]",
        "def solve(data):\n    return [json.loads(x) for x in data['text'].replace('\\u2028','').replace('\\u2029','').splitlines() if x.strip()]",
        "def solve(data):\n    return [json.loads(x) for x in data['text'].split('\\n') if x.strip()]",
        [case("ordinary", {"text":'{"a":1}\n{"a":2}\n'}, ok([{"a":1},{"a":2}])),
         case("unicode-separators", {"text":'{"a":"甲\u2028乙\u2029丙"}\n'}, ok([{"a":"甲\u2028乙\u2029丙"}])),
         case("blank-crlf", {"text":'\r\n {"b":null}\r\n \r\n'}, ok([{"b":None}])),
         case("invalid-tail", {"text":'{"a":1}\n{"a":'}, {"ok":False,"error":"JSONDecodeError"}),
         case("empty", {"text":" \n"}, ok([]))], "jsonl-observation")
    add("native-footer",
        "提取 records 中 role=assistant 且 channel 或 phase 为 commentary/final/final_answer 的消息。"
        "channel 优先于 phase，final_answer 归一为 final。只删除正文末尾完整的 "
        "<oai-mem-citation>...</oai-mem-citation> 客户端附注及其紧邻前面的空白。"
        "正文中部同名标签、其他正文与空白保持不变；输出 text/channel/removed。"
        "忽略其他角色、隐藏字段和 reasoning 记录。data.records 的消息正文位于 text。",
        """def solve(data):
    return [{"text":r["text"],"channel":r["channel"],"removed":False}
            for r in data["records"] if r.get("role")=="assistant" and r.get("channel") in ("commentary","final")]""",
        """def solve(data):
    out=[]
    for r in data["records"]:
        p=r.get("channel") or r.get("phase")
        if r.get("role")=="assistant" and p in ("commentary","final","final_answer"):
            t=re.sub(r"\\s*<oai-mem-citation>[\\s\\S]*?</oai-mem-citation>","",r["text"])
            out.append({"text":t,"channel":"final" if p=="final_answer" else p,"removed":t!=r["text"]})
    return out""",
        """def solve(data):
    out=[]
    for r in data["records"]:
        p=r.get("channel") or r.get("phase")
        if r.get("role")=="assistant" and p in ("commentary","final","final_answer"):
            t=re.sub(r"\\s*<oai-mem-citation>[\\s\\S]*?</oai-mem-citation>\\s*$","",r["text"])
            out.append({"text":t,"channel":"final" if p=="final_answer" else p,"removed":t!=r["text"]})
    return out""",
        [case("phase-footer",{"records":[{"role":"assistant","phase":"final_answer","text":"报告\n<oai-mem-citation>x</oai-mem-citation>"}]},
              ok([{"text":"报告","channel":"final","removed":True}])),
         case("inline-tag",{"records":[{"role":"assistant","channel":"final","text":"前<oai-mem-citation>x</oai-mem-citation>后"}]},
              ok([{"text":"前<oai-mem-citation>x</oai-mem-citation>后","channel":"final","removed":False}])),
         case("roles",{"records":[{"role":"system","text":"SECRET"},{"role":"assistant","phase":"analysis","text":"hidden"}]},ok([])),
         case("whitespace",{"records":[{"role":"assistant","phase":"commentary","text":"x  \n"}]},ok([{"text":"x  \n","channel":"commentary","removed":False}])),
         case("precedence",{"records":[{"role":"assistant","phase":"analysis","channel":"final","text":"yes"}]},ok([{"text":"yes","channel":"final","removed":False}]))],
        "native-final-mismatch")
    content="甲\r\n乙\r丙\n"
    lf=content.replace("\r\n","\n").replace("\r","\n")
    add("manifest-hashes",
        "校验 data.text 的 UTF-8 内容和 data.ref。sha256_lf 必须存在且等于 CRLF/CR 归一为 LF 后的 SHA256；"
        "sha256_bytes 可选，存在时也必须匹配原字节。返回布尔值。缺少两个哈希、缺少 LF 哈希或任何不匹配均返回 false。"
        "不能因旧记录没有 byte 哈希而抛出异常，也不能跳过 LF 校验。",
        """def solve(data):
    raw=data["text"]
    return hashlib.sha256(raw.encode()).hexdigest()==data["ref"]["sha256_bytes"]""",
        """def solve(data):
    raw=data["text"]; ref=data["ref"]
    return "sha256_bytes" not in ref or hashlib.sha256(raw.encode()).hexdigest()==ref["sha256_bytes"]""",
        """def solve(data):
    raw=data["text"]; ref=data["ref"]
    normalized=raw.replace("\\r\\n","\\n").replace("\\r","\\n")
    return (ref.get("sha256_lf")==hashlib.sha256(normalized.encode()).hexdigest()
        and ("sha256_bytes" not in ref or ref["sha256_bytes"]==hashlib.sha256(raw.encode()).hexdigest()))""",
        [case("legacy-lf",{"text":content,"ref":{"sha256_lf":digest(lf)}},ok(True)),
         case("both",{"text":content,"ref":{"sha256_lf":digest(lf),"sha256_bytes":digest(content)}},ok(True)),
         case("wrong-lf",{"text":content,"ref":{"sha256_lf":"0"*64}},ok(False)),
         case("wrong-bytes",{"text":content,"ref":{"sha256_lf":digest(lf),"sha256_bytes":"0"*64}},ok(False)),
         case("missing",{"text":content,"ref":{}},ok(False)),
         case("bytes-only",{"text":content,"ref":{"sha256_bytes":digest(content)}},ok(False))],
        "legacy-hash-key")
    payload={"system":"审查", "user":"BRIEF\n简报\nREPORT\n正文\nEVIDENCE\n来源"}
    def packet_record(style):
        serialized=json.dumps(payload,ensure_ascii=False,sort_keys=True,**({"separators":(",",":")} if style=="compact" else {}))
        return {"payload":dict(payload),"payload_sha256":digest(serialized)}
    compact=packet_record("compact")
    formal={"plan":{"packet":packet_record("default"),"model_specs":{"thinking":"high"}}, "components":{"brief":"简报","report":"正文","evidence":"来源"}}
    corrupted=json.loads(json.dumps(formal));corrupted["components"]["report"]="改过"
    unsafe=json.loads(json.dumps(compact));unsafe["payload"]["grading_labels"]={"pass":True}
    wrong=json.loads(json.dumps(formal));wrong["plan"]["packet"]["payload_sha256"]="f"*64
    add("packet-projection",
        "把两种冻结格式导出为恰含 system/user 的输入。development 格式为 data.packet（紧凑排序 JSON 哈希）；"
        "formal 格式 payload 在 data.plan.packet（默认空格排序 JSON 哈希），且 user 必须等于 "
        "'BRIEF\\n'+brief+'\\nREPORT\\n'+report+'\\nEVIDENCE\\n'+evidence。components 在 data.components。"
        "两类都校验 payload_sha256，拒绝 payload 的额外字段，非法时抛 ValueError。"
        "只导出 payload；不要导出 plan 的配置或答案字段。",
        """def solve(data):
    return data["packet"]["payload"]""",
        """def solve(data):
    p=data.get("packet",data.get("plan",{}).get("packet"))
    return {k:p["payload"][k] for k in ("system","user")}""",
        """def solve(data):
    formal="plan" in data
    p=data["plan"]["packet"] if formal else data["packet"]
    value=p["payload"]
    if set(value)!={"system","user"} or not all(isinstance(v,str) for v in value.values()): raise ValueError("fields")
    opts={} if formal else {"separators":(",",":")}
    h=hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,**opts).encode()).hexdigest()
    if h!=p["payload_sha256"]: raise ValueError("hash")
    if formal:
        c=data["components"]
        expected="BRIEF\\n"+c["brief"]+"\\nREPORT\\n"+c["report"]+"\\nEVIDENCE\\n"+c["evidence"]
        if value["user"]!=expected: raise ValueError("components")
    return value""",
        [case("compact",{"packet":compact},ok(payload)),case("formal",formal,ok(payload)),
         case("extra-field",{"packet":unsafe},{"ok":False,"error":"ValueError"}),
         case("tampered-components",corrupted,{"ok":False,"error":"ValueError"}),
         case("bad-digest",wrong,{"ok":False,"error":"ValueError"})],
        "formal-packet-binding")
    add("attempt-retention",
        "从 data.attempts 按输入顺序输出所有 attempts，原字段和值必须保留；"
        "另输出 current 为每个 task_id 最后一次 status=completed 的 attempt_id 映射。"
        "失败与 usage_limit 等未完成尝试不能被后来的成功覆盖，也不能覆盖已有 current。"
        "任何重复 attempt_id 都抛 ValueError。不要把 completed 解释为质量通过。",
        """def solve(data):
    latest={a["task_id"]:a for a in data["attempts"]}
    return {"attempts":list(latest.values()),"current":{k:a["attempt_id"] for k,a in latest.items()}}""",
        """def solve(data):
    rows=data["attempts"]
    return {"attempts":rows,"current":{a["task_id"]:a["attempt_id"] for a in rows}}""",
        """def solve(data):
    rows=data["attempts"]; seen=set(); current={}
    for a in rows:
        if a["attempt_id"] in seen: raise ValueError("duplicate")
        seen.add(a["attempt_id"])
        if a["status"]=="completed": current[a["task_id"]]=a["attempt_id"]
    return {"attempts":rows,"current":current}""",
        [],"archived-author-usage-limit","artifact_derived_failure_retention")
    a={"task_id":"T","attempt_id":"a1","status":"usage_limit","error":"quota"}
    b={"task_id":"T","attempt_id":"a2","status":"completed","quality":"not_assessed"}
    c={"task_id":"T","attempt_id":"a3","status":"failed"}
    d={"task_id":"U","attempt_id":"b1","status":"failed"}
    tasks[-1]["cases"]=[
        case("failure-then-success",{"attempts":[a,b]},ok({"attempts":[a,b],"current":{"T":"a2"}})),
        case("late-failure",{"attempts":[a,b,c]},ok({"attempts":[a,b,c],"current":{"T":"a2"}})),
        case("all-failed",{"attempts":[a,d]},ok({"attempts":[a,d],"current":{}})),
        case("duplicate-id",{"attempts":[b,b]},{"ok":False,"error":"ValueError"}),
        case("empty",{"attempts":[]},ok({"attempts":[],"current":{}}))]
    add("credential-boundary",
        "返回 data.text 是否包含独立凭据样式：sk- 后跟至少 20 个 ASCII 字母/数字/_/-；"
        "sk- 左边不能是字母、数字、下划线或连字符。URL 或普通产品名中的 zendesk- 片段不能误报。"
        "不要删除检查；标准是字符串模式检测，不是判断令牌是否真实可用。",
        """def solve(data):
    return bool(re.search(r"sk-[A-Za-z0-9_-]{20,}",data["text"]))""",
        """def solve(data):
    return False""",
        """def solve(data):
    return bool(re.search(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}",data["text"]))""",
        [case("product-url",{"text":"https://example.test/zendesk-"+"a"*24},ok(False)),
         case("standalone",{"text":"token: sk-"+"x"*24},ok(True)),
         case("short",{"text":"sk-abcd"},ok(False)),
         case("embedded",{"text":"prefix_sk-"+"a"*24},ok(False)),
         case("quoted",{"text":'"sk-'+"A"*32+'"'},ok(True))],
        "credential-product-false-positive")
    add("stable-observations",
        "修复工作区搜索：从 data.documents_json（JSON 对象字符串）中选出 data.role 有权限且 effective_at 不晚于 data.as_of 的文档。"
        "返回按 document ID 字典序排序的 ID 列表。保存和加载 JSON 后，同一次搜索的结果及顺序必须一致。"
        "不可按标题排序，也不能返回将来才可见或无权访问的条目。",
        """def solve(data):
    return [i for i,d in json.loads(data["documents_json"]).items()
            if data["role"] in d["roles"] and d["effective_at"]<=data["as_of"]]""",
        """def solve(data):
    return [i for i,d in sorted(json.loads(data["documents_json"]).items(),key=lambda item:item[1]["title"])
            if data["role"] in d["roles"] and d["effective_at"]<=data["as_of"]]""",
        """def solve(data):
    return [i for i,d in sorted(json.loads(data["documents_json"]).items())
            if data["role"] in d["roles"] and d["effective_at"]<=data["as_of"]]""",
        [case("reordered-objects",{"documents":{
              "b":{"title":"A","roles":["analyst"],"effective_at":"2026-09-01"},
              "a":{"title":"Z","roles":["analyst"],"effective_at":"2026-09-01"}},
              "role":"analyst","as_of":"2026-09-07"},ok(["a","b"])),
         case("permission",{"documents":{"x":{"title":"X","roles":["finance"],"effective_at":"2026-09-01"}},
              "role":"analyst","as_of":"2026-09-07"},ok([])),
         case("future",{"documents":{"x":{"title":"X","roles":["analyst"],"effective_at":"2026-09-08"}},
              "role":"analyst","as_of":"2026-09-07"},ok([])),
         case("empty",{"documents":{},"role":"analyst","as_of":"2026-09-07"},ok([]))],
        "serialized-observation-order")
    for item in tasks[-1]["cases"]:
        item["input"]["documents_json"]=json.dumps(item["input"].pop("documents"),ensure_ascii=False)
    return tasks

VERIFIER = r'''"""Private test runner. Execute only trusted repair candidates on a local host."""
import argparse,hashlib,json,os,pathlib,subprocess,sys,time
def grade(workspace):
    base=pathlib.Path(__file__).parent
    cases=json.loads((base/"cases.json").read_text(encoding="utf-8"))
    workspace=pathlib.Path(workspace).resolve()
    target=workspace/"worker.py"
    records=[]
    for c in cases:
        start=time.monotonic()
        try:
            run=subprocess.run([sys.executable,"-X","utf8","-I","-B",str(target)],
                input=json.dumps(c["input"],ensure_ascii=False),text=True,encoding="utf-8",
                capture_output=True,cwd=workspace,timeout=3,
                env={k:v for k,v in os.environ.items() if k.upper() in {"SYSTEMROOT","WINDIR","TEMP","TMP","PATH"}})
            try: result=json.loads(run.stdout)
            except ValueError: result=None
            passed=run.returncode==0 and result==c["expected"]
            records.append({"case":c["name"],"passed":passed,"exit_code":run.returncode,
                "stdout":run.stdout,"stderr":run.stderr,"expected":c["expected"],
                "elapsed_seconds":round(time.monotonic()-start,6),"timeout":False})
        except subprocess.TimeoutExpired as exc:
            records.append({"case":c["name"],"passed":False,"exit_code":None,
                "stdout":str(exc.stdout or ""),"stderr":str(exc.stderr or ""),"timeout":True})
    passed=sum(r["passed"] for r in records)
    return {"reward":int(passed==len(records)),"passed":passed,"total":len(records),
        "diagnostic_fraction":passed/len(records),"cases":records,
        "worker_sha256":hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None}
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("workspace");p.add_argument("--output")
    a=p.parse_args();result=grade(a.workspace);body=json.dumps(result,ensure_ascii=False,indent=2)+"\n"
    if a.output:pathlib.Path(a.output).write_text(body,encoding="utf-8")
    else:print(body)
    raise SystemExit(0 if result["reward"] else 1)
'''
SOLVER = '''import argparse,pathlib,shutil
p=argparse.ArgumentParser();p.add_argument("workspace");a=p.parse_args()
target=pathlib.Path(a.workspace).resolve();target.mkdir(parents=True,exist_ok=True)
shutil.copyfile(pathlib.Path(__file__).with_name("worker.py"),target/"worker.py")
'''
