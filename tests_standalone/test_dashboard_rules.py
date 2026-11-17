import importlib.util, datetime
from decimal import Decimal as D
spec=importlib.util.spec_from_file_location("rules","/home/claude/avelle/apps/dashboard/rules.py"); r=importlib.util.module_from_spec(spec); spec.loader.exec_module(r)

# permissions: cumulative roles, customers get nothing, superuser gets all
assert r.permissions_for("customer")==frozenset()
assert "orders" in r.permissions_for("staff") and "catalogue" not in r.permissions_for("staff")
assert "refunds" not in r.permissions_for("manager") and "catalogue" in r.permissions_for("manager")
assert "refunds" in r.permissions_for("admin") and "team" in r.permissions_for("admin")
assert r.permissions_for("customer", True)==r.ADMIN_PERMS
assert r.permissions_for("nonsense")==frozenset()
assert r.STAFF_PERMS < r.MANAGER_PERMS < r.ADMIN_PERMS

# transitions
assert r.can_transition("paid","processing") and r.can_transition("paid","shipped")
assert r.can_transition("processing","shipped") and r.can_transition("shipped","delivered")
assert r.can_transition("pending_payment","cancelled")
for bad in (("paid","cancelled"),("paid","delivered"),("delivered","shipped"),("cancelled","paid"),("refunded","paid"),("pending_payment","paid"),("shipped","cancelled")):
    assert not r.can_transition(*bad), bad
assert r.next_statuses("delivered")==() and r.next_statuses("unknown")==()
# nothing may move *into* paid/refunded by hand (payments and refunds own those)
assert all(t not in ("paid","refunded","pending_payment") for v in r.TRANSITIONS.values() for t in v)

# refunds
assert r.refundable_amount(D("38500"),[])==D("38500")
assert r.refundable_amount(D("38500"),[D("10000"),D("5000.50")])==D("23499.50")
assert r.refundable_amount(D("100"),[D("100"),D("1")])==D("0.00")
assert r.refund_is_full(D("100"),[D("40"),D("60")]) and not r.refund_is_full(D("100"),[D("40")])

# reporting
assert r.percent_change(150,100)==50.0 and r.percent_change(50,100)==-50.0 and r.percent_change(5,0) is None and r.percent_change(None,None) is None
assert r.period_days("7")==7 and r.period_days("bogus")==30 and r.period_days(None)==30
start=datetime.date(2026,11,1)
s=r.fill_daily_series([(datetime.date(2026,11,2),D("100")),(datetime.date(2026,11,4),None)],start,5)
assert [v for _,v in s]==[D(0),D(100),D(0),D(0),D(0)] and s[0][0]==start and s[-1][0]==datetime.date(2026,11,5)
b=r.scale_bars([(start,D(0)),(start,D(1)),(start,D(1000)),(start,D(500))])
assert [x["pct"] for x in b]==[0,2,100,50]
assert [x["pct"] for x in r.scale_bars([(start,D(0))])]==[0]

# discount code state
n=datetime.datetime(2026,11,15,12,0)
d=datetime.timedelta(days=1)
def st(**k):
    base=dict(is_active=True,starts_at=None,expires_at=None,times_used=0,usage_limit=None,now=n); base.update(k); return r.code_state(**base)
assert st()=="live" and st(is_active=False)=="inactive" and st(times_used=5,usage_limit=5)=="used up" and st(times_used=4,usage_limit=5)=="live"
assert st(expires_at=n-d)=="expired" and st(starts_at=n+d)=="scheduled" and st(expires_at=n+d,starts_at=n-d)=="live"
assert st(is_active=False,expires_at=n-d)=="inactive"

# team guard rails
g=lambda **k: r.can_change_access(**{**dict(actor_id=1,target_id=2,target_role="staff",new_role="manager",new_active=True,active_admins=2),**k})
assert g() is None
assert g(target_id=1) is not None
assert g(target_role="admin",new_role="staff",active_admins=1) is not None
assert g(target_role="admin",new_active=False,active_admins=1) is not None
assert g(target_role="admin",new_role="staff",active_admins=2) is None
assert g(target_role="staff",new_role="admin",active_admins=1) is None

# report ranges
today=datetime.date(2026,11,15)
assert r.parse_range("","",today)==(datetime.date(2026,10,17),today,"")
assert r.parse_range("2026-11-01","2026-11-10",today)==(datetime.date(2026,11,1),datetime.date(2026,11,10),"")
a,b,n=r.parse_range("2026-11-10","2026-11-01",today); assert (a,b)==(datetime.date(2026,11,1),datetime.date(2026,11,10)) and n
assert r.parse_range("garbage","also bad",today)[:2]==(datetime.date(2026,10,17),today)
assert r.parse_range("2026-11-01","2030-01-01",today)[1]==today       # future end clamps to today
a,b,n=r.parse_range("2020-01-01","2026-11-15",today); assert (b-a).days+1==366 and n
assert r.parse_range("2026-11-15","",today)[:2]==(today,today)
# csv safety
assert r.csv_safe("=HYPERLINK(1)")=="'=HYPERLINK(1)" and r.csv_safe("@x")=="'@x" and r.csv_safe("+1")=="'+1" and r.csv_safe("-2")=="'-2"
assert r.csv_safe("Ada Obi")=="Ada Obi" and r.csv_safe(D("12.50"))==D("12.50") and r.csv_safe(5)==5 and r.csv_safe(None)==""
assert r.csv_safe("\tx")=="'\tx"
assert "reports" in r.permissions_for("manager") and "reports" not in r.permissions_for("staff") and "content" in r.permissions_for("manager")
print("dashboard rules tests passed")
