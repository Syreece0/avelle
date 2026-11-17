import sys, json, threading, hmac, hashlib
sys.path.insert(0,"/home/claude/avelle")
import importlib.util
spec=importlib.util.spec_from_file_location("ps","/home/claude/avelle/apps/payments/paystack.py"); ps=importlib.util.module_from_spec(spec); spec.loader.exec_module(ps)
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
assert ps.to_kobo(Decimal("38500"))==3850000 and ps.to_kobo("1234.565")==123457 and ps.to_kobo(Decimal("0.005"))==1
body=b'{"event":"charge.success"}'; sig=hmac.new(b"sk",body,hashlib.sha512).hexdigest()
assert ps.verify_signature(body,sig,"sk") and not ps.verify_signature(body,sig,"other") and not ps.verify_signature(body,"","sk") and not ps.verify_signature(b"x",sig,"sk") and ps.verify_signature(body,sig.upper(),"sk")
seen=[]
class H(BaseHTTPRequestHandler):
    def log_message(s,*a): pass
    def reply(s,code,obj): b=json.dumps(obj).encode(); s.send_response(code); s.send_header("Content-Type","application/json"); s.send_header("Content-Length",str(len(b))); s.end_headers(); s.wfile.write(b)
    def do_POST(s):
        n=int(s.headers["Content-Length"]); d=json.loads(s.rfile.read(n)); seen.append((s.path,s.headers["Authorization"],d))
        if d["email"]=="bad@x.com": return s.reply(400,{"status":False,"message":"Invalid email"})
        s.reply(200,{"status":True,"data":{"authorization_url":"https://checkout.paystack.com/abc","reference":d["reference"]}})
    def do_GET(s):
        if s.path.endswith("boom"): return s.reply(200,{"status":False,"message":"nope"})
        if s.path.endswith("html"): s.send_response(502); s.end_headers(); s.wfile.write(b"<html>"); return
        s.reply(200,{"status":True,"data":{"status":"success","amount":3850000,"reference":s.path.split("/")[-1]}})
srv=HTTPServer(("127.0.0.1",8799),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
c=ps.PaystackClient("sk_test","http://127.0.0.1:8799")
d=c.initialize(email="a@b.com",amount=Decimal("38500"),reference="R1",callback_url="http://x/cb",metadata={"order":"AV-1"})
assert d["authorization_url"].startswith("https://") and seen[0][2]["amount"]==3850000 and seen[0][1]=="Bearer sk_test" and seen[0][0]=="/transaction/initialize"
for fn,args in ((c.initialize,dict(email="bad@x.com",amount=1,reference="R",callback_url="u")),(c.verify,("boom",)),(c.verify,("html",))):
    try: fn(**args) if isinstance(args,dict) else fn(*args); raise SystemExit("expected failure")
    except ps.PaystackError as e: print("ok error:",str(e)[:70])
assert c.verify("R1")["amount"]==3850000
try: ps.PaystackClient(""); raise SystemExit("should fail")
except ps.PaystackError: pass
c2=ps.PaystackClient("sk","http://127.0.0.1:1",timeout=1)
try: c2.verify("x"); raise SystemExit("should fail")
except ps.PaystackError as e: print("ok network:",str(e)[:50])
print("PAYSTACK CLIENT OK")

# ---- refunds (added in Phase 9)
seen.clear()
class R(H):
    def do_POST(s):
        n=int(s.headers["Content-Length"]); d=json.loads(s.rfile.read(n)); seen.append((s.path,d))
        if s.path=="/refund":
            if d["transaction"]=="BAD": return s.reply(400,{"status":False,"message":"Transaction not found"})
            return s.reply(200,{"status":True,"data":{"status":"pending","id":991,"amount":d["amount"]}})
        s.reply(200,{"status":True,"data":{}})
srv2=HTTPServer(("127.0.0.1",8798),R); threading.Thread(target=srv2.serve_forever,daemon=True).start()
c2=ps.PaystackClient("sk_test","http://127.0.0.1:8798")
r=c2.refund(transaction="AVP-1",amount=Decimal("1250.50"),note="Customer changed mind")
assert r["status"]=="pending" and seen[0][0]=="/refund" and seen[0][1]=={"transaction":"AVP-1","amount":125050,"merchant_note":"Customer changed mind"}
try: c2.refund(transaction="BAD",amount=1); raise SystemExit("expected failure")
except ps.PaystackError as e: print("ok refund error:",str(e)[:60])
print("refund tests passed")
