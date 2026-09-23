from __future__ import annotations
import re
from .js_runtime import eval_js
EXPR = re.compile(r"^\s*=\{\{(.*)\}\}\s*$", re.S)
TEMPLATE = re.compile(r"\{\{(.*?)\}\}", re.S)
def resolve(value, *, current, previous, env, execution):
    if isinstance(value, dict): return {k: resolve(v,current=current,previous=previous,env=env,execution=execution) for k,v in value.items()}
    if isinstance(value, list): return [resolve(v,current=current,previous=previous,env=env,execution=execution) for v in value]
    if not isinstance(value,str): return value
    m=EXPR.match(value)
    if m: return eval_js(m.group(1),current=current,previous=previous,env=env,execution=execution)
    if "{{" in value:
        return TEMPLATE.sub(lambda x: "" if (v:=eval_js(x.group(1),current=current,previous=previous,env=env,execution=execution)) is None else str(v),value)
    return value
