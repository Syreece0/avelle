"""cloudinary_optimised: pure function, loaded without Django."""
import importlib.util, pathlib, sys, types

src = (pathlib.Path(__file__).parent.parent / "apps/core/utils.py").read_text()
start = src.index("def cloudinary_optimised")
ns = {}
exec(src[start:], ns)
f = ns["cloudinary_optimised"]

u = "https://res.cloudinary.com/demo/image/upload/v123/avelle/a.jpg"
assert f(u, 640) == "https://res.cloudinary.com/demo/image/upload/f_auto,q_auto,c_limit,w_640/v123/avelle/a.jpg"
assert f(f(u, 640), 320) == f(u, 640)            # already transformed: untouched
assert f("/media/a.jpg", 640) == "/media/a.jpg"  # local file: untouched
assert f("", 640) == "" and f(None, 640) is None
assert f("https://example.com/image/upload/x.jpg", 640) == "https://example.com/image/upload/x.jpg"
print("cdn tests passed")
