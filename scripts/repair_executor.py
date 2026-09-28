"""Bounded pure-function Python execution for small archived repair reproductions.
This accepts a documented Python subset, not general repository or shell execution.
"""
from __future__ import annotations
import ast,copy,hashlib,json,sys,types
from research_env_v3 import check,equal
NODES={"Module","FunctionDef","arguments","arg","Return","Assign","Name","Load","Store","Constant","Dict","List","Tuple","Set","Subscript","Slice","Call","Attribute","ListComp","DictComp","SetComp","GeneratorExp","comprehension","Compare","Eq","NotEq","LtE","Lt","Gt","GtE","In","NotIn","Is","IsNot","BoolOp","And","Or","UnaryOp","Not","USub","If","IfExp","For","Expr","Raise","Lambda","keyword","BinOp","Add","Pass"}
BUILTINS={"len":len,"sorted":sorted,"list":list,"dict":dict,"set":set,"tuple":tuple,"bool":bool,"str":str,"int":int,"any":any,"all":all,"isinstance":isinstance,"ValueError":ValueError}
ATTRS={"loads","dumps","sha256","hexdigest","encode","replace","split","splitlines","strip","get","items","values","keys","append","add","lower","join"}
class ExecutionLimit(Exception):pass

def validate(source):
    check(isinstance(source,str) and len(source)<=8000,"candidate_size")
    tree=ast.parse(source);check(len(tree.body)==1 and isinstance(tree.body[0],ast.FunctionDef) and tree.body[0].name=="solve","single_solve_function_required")
    fn=tree.body[0];check(len(fn.args.args)==1 and not fn.args.posonlyargs and not fn.args.kwonlyargs and not fn.args.vararg and not fn.args.kwarg and not fn.args.defaults and not fn.decorator_list and fn.returns is None and all(a.annotation is None for a in fn.args.args),"function_contract")
    nodes=list(ast.walk(tree));check(len(nodes)<=500,"candidate_complexity")
    for n in nodes:
        check(type(n).__name__ in NODES,"unsupported_python_node:"+type(n).__name__)
        if isinstance(n,ast.FunctionDef):check(n is fn,"nested_function_forbidden")
        if isinstance(n,(ast.Name,ast.arg)):check(not getattr(n,"id",getattr(n,"arg","")).startswith("_"),"private_name_forbidden")
        if isinstance(n,ast.Attribute):check(n.attr in ATTRS,"attribute_not_allowed:"+n.attr)
        if isinstance(n,ast.Call):check(isinstance(n.func,ast.Attribute) or isinstance(n.func,ast.Name) and n.func.id in BUILTINS,"call_not_allowed")
        if isinstance(n,ast.Constant):check(not isinstance(n.value,(int,float)) or abs(n.value)<=1000000,"constant_limit")
        if isinstance(n,ast.comprehension):check(not n.is_async,"async_forbidden")
    return tree

def execute(source,data):
    tree=validate(source);check(len(json.dumps(data,ensure_ascii=False))<=20000,"input_limit")
    namespace={"__builtins__":BUILTINS,"json":types.SimpleNamespace(loads=json.loads,dumps=json.dumps),"hashlib":types.SimpleNamespace(sha256=hashlib.sha256)}
    filename="<bounded-repair>";exec(compile(tree,filename,"exec"),namespace)
    budget=[20000]
    def trace(frame,event,arg):
        if frame.f_code.co_filename==filename:
            frame.f_trace_opcodes=True;budget[0]-=1
            if budget[0]<=0:raise ExecutionLimit("instruction_budget")
        return trace
    previous=sys.gettrace()
    try:
        sys.settrace(trace);value=namespace["solve"](copy.deepcopy(data));json.dumps(value,allow_nan=False)
        return {"ok":True,"value":value}
    except Exception as error:return {"ok":False,"error":type(error).__name__}
    finally:sys.settrace(previous)

def run_cases(source,cases):
    records=[]
    for case in cases:
        try:actual=execute(source,case["input"])
        except (ValueError,SyntaxError) as error:actual={"ok":False,"error":type(error).__name__}
        records.append({"name":case["name"],"passed":equal(actual,case["expected"]),"actual":actual,"expected":case["expected"]})
    return {"passed":all(r["passed"] for r in records),"cases":records}
