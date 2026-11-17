#!/usr/bin/env python3
"""Static consistency checker for AVELLE. Needs only the Python standard library (no Django).

It cannot replace running the project, but it catches the mistakes that otherwise only show up as a 500 page:

  urls       every {% url %} / reverse() / redirect() name exists and gets the right number of arguments
  templates  extends/include/static targets exist, tags are balanced, filters and {% load %} libraries exist,
             child templates only fill blocks their parent really defines
  orm        field names used in filter()/order_by()/values()/select_related()/Q()/F()/Sum()..., create() and
             Model(...) kwargs, and ModelForm Meta.fields all exist on the model (relations followed)
  settings   INSTALLED_APPS, context processors and middleware point at real modules

Usage:  python tools/check_project.py            (exit status 1 if anything is found)
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"
problems = []


def report(kind, where, message):
    problems.append((kind, where, message))


def rel(path):
    return str(Path(path).relative_to(ROOT))


# =============================================================================================== URL registry
CONVERTER = re.compile(r"<(?:\w+:)?(\w+)>")


def parse_urls():
    """{'ns:name' or 'name': [param names]} built from the urls.py files."""
    names = {}

    def module_for(dotted):
        return ROOT / (dotted.replace(".", "/") + ".py")

    def walk(module_path, prefix_ns, seen=()):
        tree = ast.parse(module_path.read_text())
        app_name = None
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "app_name" for t in node.targets):
                app_name = node.value.value
        ns = app_name or prefix_ns
        patterns = next((n.value for n in tree.body if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "urlpatterns" for t in n.targets)), None)
        if patterns is None:
            return
        elements = patterns.elts if isinstance(patterns, ast.List) else []
        for call in elements:
            if not (isinstance(call, ast.Call) and getattr(call.func, "id", "") == "path"):
                continue
            route = call.args[0].value if call.args and isinstance(call.args[0], ast.Constant) else ""
            target = call.args[1] if len(call.args) > 1 else None
            kw = {k.arg: k.value for k in call.keywords}
            if isinstance(target, ast.Call) and getattr(target.func, "id", "") == "include":
                inc = target.args[0].value
                if inc not in seen and module_for(inc).exists():
                    walk(module_for(inc), ns, seen + (inc,))
                continue
            name = kw.get("name")
            if isinstance(name, ast.Constant):
                full = f"{ns}:{name.value}" if app_name else name.value
                names[full] = CONVERTER.findall(route)
                # an include() prefix can add parameters; none of our includes do

    walk(ROOT / "config" / "urls.py", None)
    return names


URLS = parse_urls()


def check_url_use(name, nargs, kwargs, where):
    if name not in URLS:
        report("urls", where, f"URL name '{name}' is not defined")
        return
    params = URLS[name]
    if kwargs is not None:
        if set(kwargs) != set(params):
            report("urls", where, f"'{name}' takes {params or 'no arguments'}, got keywords {sorted(kwargs)}")
    elif nargs is not None and nargs != len(params):
        report("urls", where, f"'{name}' takes {len(params)} argument(s) {params}, got {nargs}")


# =============================================================================================== templates
BUILTIN_FILTERS = set("""add addslashes capfirst center cut date default default_if_none dictsort dictsortreversed divisibleby escape escapejs
 escapeseq filesizeformat first floatformat force_escape get_digit iriencode join json_script last length linebreaks linebreaksbr linenumbers
 ljust lower make_list phone2numeric pluralize pprint random rjust safe safeseq slice slugify stringformat striptags time timesince timeuntil
 title truncatechars truncatechars_html truncatewords truncatewords_html unordered_list upper urlencode urlize urlizetrunc wordcount wordwrap yesno""".split())
BLOCK_TAGS = {"if": "endif", "for": "endfor", "block": "endblock", "with": "endwith", "comment": "endcomment", "autoescape": "endautoescape",
              "spaceless": "endspaceless", "verbatim": "endverbatim", "filter": "endfilter", "ifchanged": "endifchanged"}
END_TAGS = {v: k for k, v in BLOCK_TAGS.items()}
BUILTIN_LIBS = {"static", "i18n", "l10n", "humanize", "cache", "tz"}
KNOWN_SIMPLE_TAGS = {"extends", "include", "load", "url", "static", "csrf_token", "now", "icon", "empty", "else", "elif", "firstof", "cycle",
                     "lorem", "templatetag", "debug", "widthratio", "regroup", "resetcycle", "querystring", "trans", "blocktrans", "endblocktrans"}
TAG = re.compile(r"\{%\s*(.*?)\s*%\}", re.S)
VAR = re.compile(r"\{\{\s*(.*?)\s*\}\}", re.S)
# Fetched during the build (manage.py fetch_vendor), so absent from the repo by design.
BUILD_TIME_STATIC = ("vendor/gsap/",)
STRING = re.compile(r"""("[^"\\]*(?:\\.[^"\\]*)*"|'[^'\\]*(?:\\.[^'\\]*)*')""")


def custom_template_tags():
    filters, tags, libs = set(), set(), set()
    for path in ROOT.glob("apps/*/templatetags/*.py"):
        if path.stem == "__init__":
            continue
        libs.add(path.stem)
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.FunctionDef):
                for dec in node.decorator_list:
                    d = dec.func if isinstance(dec, ast.Call) else dec
                    if isinstance(d, ast.Attribute) and d.attr in ("filter", "simple_tag", "inclusion_tag", "tag"):
                        (filters if d.attr == "filter" else tags).add(node.name)
    return filters, tags, libs


CUSTOM_FILTERS, CUSTOM_TAGS, CUSTOM_LIBS = custom_template_tags()


def template_exists(name):
    return (TEMPLATES / name).exists() or any(ROOT.glob(f"apps/*/templates/{name}"))


def static_exists(name):
    return (STATIC / name).exists()


def lineno(text, pos):
    return text.count("\n", 0, pos) + 1


def blocks_of(text):
    return {m.group(1) for m in re.finditer(r"\{%\s*block\s+(\w+)\s*%\}", text)}


def top_level_blocks(text):
    """Blocks that are not nested inside another block (those must exist in the parent template)."""
    out, depth = set(), 0
    for m in re.finditer(r"\{%\s*(block\s+(\w+)|endblock)[^%]*%\}", text):
        if m.group(1) == "endblock":
            depth -= 1
        else:
            if depth == 0:
                out.add(m.group(2))
            depth += 1
    return out


def extends_of(text):
    m = re.search(r"^\s*\{%\s*extends\s+[\"']([^\"']+)[\"']", text)
    return m.group(1) if m else None


def check_templates():
    all_blocks = {}
    texts = {}
    for path in sorted(TEMPLATES.rglob("*.html")) + sorted(TEMPLATES.rglob("*.txt")):
        texts[path] = path.read_text()
        all_blocks[str(path.relative_to(TEMPLATES))] = blocks_of(texts[path])

    def ancestors_blocks(name, seen=()):
        text = texts.get(TEMPLATES / name)
        if text is None or name in seen:
            return set()
        parent = extends_of(text)
        return all_blocks.get(name, set()) | (ancestors_blocks(parent, seen + (name,)) if parent else set())

    for path, text in texts.items():
        here = rel(path)
        stack = []
        verbatim = False
        loaded = set()
        for m in TAG.finditer(text):
            body, line = m.group(1), lineno(text, m.start())
            word = body.split()[0] if body.split() else ""
            if verbatim:
                if word == "endverbatim":
                    verbatim = False
                continue
            if word == "verbatim":
                verbatim = True
                stack.append(("verbatim", line))
                continue
            if word == "comment":
                stack.append(("comment", line))
                continue
            if stack and stack[-1][0] == "comment":
                if word == "endcomment":
                    stack.pop()
                continue
            if word in ("blocktrans", "blocktranslate"):
                stack.append(("blocktrans", line))
                continue
            if word in ("endblocktrans", "endblocktranslate"):
                if stack and stack[-1][0] == "blocktrans":
                    stack.pop()
                continue
            if word in BLOCK_TAGS:
                if word == "if" and False:
                    pass
                stack.append((word, line))
            elif word in END_TAGS:
                if not stack or stack[-1][0] != END_TAGS[word]:
                    opener = stack[-1] if stack else None
                    report("templates", f"{here}:{line}", f"{{% {word} %}} does not match {('{% ' + opener[0] + ' %} from line ' + str(opener[1])) if opener else 'any open tag'}")
                else:
                    stack.pop()
            elif word in ("else", "elif"):
                if not stack or stack[-1][0] not in ("if", "for"):
                    report("templates", f"{here}:{line}", f"{{% {word} %}} outside {{% if %}}/{{% for %}}")
            elif word == "empty":
                if not stack or stack[-1][0] != "for":
                    report("templates", f"{here}:{line}", "{% empty %} outside {% for %}")
            elif word == "load":
                for lib in body.split()[1:]:
                    loaded.add(lib)
                    if lib not in BUILTIN_LIBS and lib not in CUSTOM_LIBS:
                        report("templates", f"{here}:{line}", f"{{% load {lib} %}}: no such template library")
            elif word in ("extends", "include"):
                s = STRING.search(body)
                if s and template_exists(s.group(1)[1:-1]) is False:
                    report("templates", f"{here}:{line}", f"{{% {word} %}} target '{s.group(1)[1:-1]}' does not exist")
            elif word == "static":
                s = STRING.search(body)
                if s and not s.group(1)[1:-1].startswith(BUILD_TIME_STATIC) and not static_exists(s.group(1)[1:-1]):
                    report("templates", f"{here}:{line}", f"static file '{s.group(1)[1:-1]}' does not exist")
            elif word == "url":
                s = STRING.match(body[3:].strip())
                if s:
                    name = s.group(1)[1:-1]
                    rest = re.sub(r"\s+as\s+\w+\s*$", "", body[3:].strip()[len(s.group(1)):]).split()
                    kw = {a.split("=")[0] for a in rest if "=" in a}
                    check_url_use(name, None if kw else len(rest), kw or None, f"{here}:{line}")
            elif word not in KNOWN_SIMPLE_TAGS and word not in CUSTOM_TAGS:
                report("templates", f"{here}:{line}", f"unknown template tag '{word}'")
            if word in ("icon", "static") and word not in CUSTOM_TAGS and word not in loaded and word == "icon":
                report("templates", f"{here}:{line}", "{% icon %} used without {% load avelle_ui %}")
            # filters used in any tag expression
            expr = STRING.sub('""', body)
            for f in re.findall(r"\|\s*(\w+)", expr):
                if f not in BUILTIN_FILTERS and f not in CUSTOM_FILTERS:
                    report("templates", f"{here}:{line}", f"unknown filter '{f}'")
        for opener, line in stack:
            report("templates", f"{here}:{line}", f"{{% {opener} %}} is never closed")
        for m in VAR.finditer(text):
            expr = STRING.sub('""', m.group(1))
            for f in re.findall(r"\|\s*(\w+)", expr):
                if f not in BUILTIN_FILTERS and f not in CUSTOM_FILTERS:
                    report("templates", f"{here}:{lineno(text, m.start())}", f"unknown filter '{f}'")
        if "avelle_ui" not in loaded and ("{% icon" in text or "|naira" in text):
            # base.html style templates load it; child templates that extend must load it themselves too
            report("templates", here, "uses icon/naira but never loads avelle_ui (child templates do not inherit {% load %})")
        parent = extends_of(text)
        if parent and template_exists(parent):
            allowed = ancestors_blocks(parent)
            for b in top_level_blocks(text):
                if b not in allowed:
                    report("templates", here, f"block '{b}' is not defined by '{parent}' (or its parents), so it would never render")


# =============================================================================================== python: urls
def check_python_urls():
    for path in sorted(ROOT.glob("apps/**/*.py")) + sorted(ROOT.glob("config/**/*.py")):
        if "migrations" in path.parts or path.name == "tests.py":
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fname = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
            if fname not in ("reverse", "reverse_lazy", "redirect") or not node.args:
                continue
            first = node.args[0]
            if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                continue
            name = first.value
            if "/" in name or "." in name:  # a literal path or a dotted import, not a URL name
                continue
            where = f"{rel(path)}:{node.lineno}"
            kws = {k.arg for k in node.keywords if k.arg}
            if fname == "redirect":
                check_url_use(name, len(node.args) - 1, kws or None, where) if (len(node.args) > 1 or kws) else check_url_use(name, 0, None, where)
            else:
                args_kw = next((k.value for k in node.keywords if k.arg == "args"), None)
                kwargs_kw = next((k.value for k in node.keywords if k.arg == "kwargs"), None)
                if isinstance(kwargs_kw, ast.Dict):
                    check_url_use(name, None, {k.value for k in kwargs_kw.keys if isinstance(k, ast.Constant)}, where)
                elif isinstance(args_kw, (ast.List, ast.Tuple)):
                    check_url_use(name, len(args_kw.elts), None, where)
                elif args_kw is None and kwargs_kw is None:
                    check_url_use(name, 0, None, where)


# =============================================================================================== ORM registry
TIMESTAMPED = {"created_at": ("DateTimeField", None), "updated_at": ("DateTimeField", None)}
ABSTRACT_USER = {n: ("Field", None) for n in "password last_login is_superuser first_name last_name email is_staff is_active date_joined username groups user_permissions".split()}
FIELD_TYPES = {"ForeignKey", "OneToOneField", "ManyToManyField"}
LOOKUPS = set("exact iexact contains icontains in gt gte lt lte startswith istartswith endswith iendswith range isnull regex iregex date year month day week week_day quarter time hour minute second".split())
QS_KEEP = set("filter exclude all order_by select_related prefetch_related distinct annotate alias select_for_update only defer reverse using values values_list none union".split())
QS_END = set("get first last exists count aggregate update delete create get_or_create update_or_create bulk_create bulk_update in_bulk earliest latest iterator".split())
AGG = {"Sum", "Count", "Max", "Min", "Avg", "Coalesce", "F", "Q", "Lower", "Upper", "TruncDate", "Length", "Concat"}


class Model:
    def __init__(self, name, app):
        self.name, self.app, self.fields, self.reverse = name, app, {}, {}


MODELS = {}


def collect_models():
    classes = {}
    for path in sorted(ROOT.glob("apps/*/models.py")):
        app = path.parent.name
        tree = ast.parse(path.read_text())
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                classes[node.name] = (node, app)
    for name, (node, app) in classes.items():
        bases = [b.id if isinstance(b, ast.Name) else getattr(b, "attr", "") for b in node.bases]
        if not any(b in ("Model", "TimeStampedModel", "AbstractUser") or b in classes for b in bases) or name in ("TimeStampedModel",):
            continue
        m = Model(name, app)
        m.fields["id"] = ("AutoField", None)
        m.fields["pk"] = ("AutoField", None)
        if "TimeStampedModel" in bases:
            m.fields.update(TIMESTAMPED)
        if "AbstractUser" in bases:
            m.fields.update(ABSTRACT_USER)
        for b in bases:
            if b in classes and b not in MODELS:
                pass
        for st in node.body:
            if isinstance(st, ast.Assign) and isinstance(st.value, ast.Call) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name):
                f = st.value.func
                ftype = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                if ftype.endswith("Field") or ftype == "ForeignKey":
                    target = None
                    if ftype in FIELD_TYPES and st.value.args:
                        a = st.value.args[0]
                        target = a.value if isinstance(a, ast.Constant) else a.id if isinstance(a, ast.Name) else getattr(a, "attr", None)
                        if target in ("self",):
                            target = name
                        if isinstance(target, str) and "." in target:
                            target = target.split(".")[-1]
                        if target == "AUTH_USER_MODEL" or (isinstance(a, ast.Attribute) and a.attr == "AUTH_USER_MODEL"):
                            target = "CustomUser"
                    m.fields[st.targets[0].id] = (ftype, target)
                    if ftype in ("ForeignKey", "OneToOneField"):
                        m.fields[st.targets[0].id + "_id"] = ("AutoField", None)  # the raw column name Django also accepts
                    if ftype in FIELD_TYPES:
                        rn = next((k.value.value for k in st.value.keywords if k.arg == "related_name" and isinstance(k.value, ast.Constant)), None)
                        m.fields[st.targets[0].id] = (ftype, target, rn)
                elif ftype == "ImageField":
                    m.fields[st.targets[0].id] = ("ImageField", None)
        MODELS[name] = m
    # inherit fields from concrete parents defined in our models
    for name, (node, _) in classes.items():
        if name in MODELS:
            for b in node.bases:
                if isinstance(b, ast.Name) and b.id in MODELS and b.id != name:
                    for k, v in MODELS[b.id].fields.items():
                        MODELS[name].fields.setdefault(k, v)
    # reverse accessors
    for m in list(MODELS.values()):
        for fname, spec in list(m.fields.items()):
            if spec[0] in FIELD_TYPES and len(spec) == 3 and spec[1] in MODELS:
                rn = spec[2] or (m.name.lower() if spec[0] == "OneToOneField" else m.name.lower() + "_set")
                if rn and rn != "+":
                    MODELS[spec[1]].reverse[rn] = m.name
                    MODELS[spec[1]].reverse[m.name.lower()] = m.name  # the default query name for reverse lookups


def resolve_path(model, path, annotations, where, ctx):
    """Validate one 'a__b__c' lookup. Returns nothing; reports problems."""
    parts = path.split("__")
    cur = MODELS.get(model)
    i = 0
    if parts[0] in annotations:
        return
    while i < len(parts):
        part = parts[i]
        if cur is None:
            return  # followed a relation we can't resolve (e.g. User from settings), stop quietly
        if part in cur.fields:
            spec = cur.fields[part]
            if spec[0] in FIELD_TYPES and spec[1] in MODELS:
                cur = MODELS[spec[1]]
                i += 1
                if i < len(parts) and parts[i] in LOOKUPS and parts[i] not in cur.fields and parts[i] not in cur.reverse:
                    return
                continue
            # a plain field: everything after must be a lookup/transform
            rest = parts[i + 1:]
            if any(r not in LOOKUPS for r in rest):
                report("orm", where, f"{ctx}: '{path}': '{rest}' is not a lookup on field {cur.name}.{part}")
            return
        if part in cur.reverse:
            cur = MODELS[cur.reverse[part]]
            i += 1
            continue
        report("orm", where, f"{ctx}: '{path}': {cur.name} has no field or relation '{part}'")
        return


def const_str(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


class ChainChecker(ast.NodeVisitor):
    def __init__(self, path):
        self.path = path
        self.env = [{}]  # variable name -> model name for querysets / instances
        self.returns = {}  # module-level helper name -> kind of the queryset it returns

    def where(self, node):
        return f"{rel(self.path)}:{node.lineno}"

    # -- resolve an expression to ("qs", model, annotations) / ("obj", model) / None
    def kind(self, node):
        if isinstance(node, ast.Name):
            return self.env[-1].get(node.id) or (("cls", node.id) if node.id in MODELS else None)
        if isinstance(node, ast.Attribute):
            base = self.kind(node.value)
            if base and base[0] == "cls" and node.attr == "objects":
                return ("qs", base[1], frozenset())
            return None
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in MODELS:
                return ("obj", f.id)
            if isinstance(f, ast.Name) and f.id in self.returns:
                return self.returns[f.id]
            if isinstance(f, ast.Attribute):
                base = self.kind(f.value)
                if base and base[0] == "qs":
                    if f.attr in QS_KEEP:
                        ann = set(base[2]) | {k.arg for k in node.keywords if k.arg and f.attr in ("annotate", "alias")}
                        return ("qs", base[1], frozenset(ann))
                    if f.attr in ("get", "first", "last", "create", "earliest", "latest"):
                        return ("obj", base[1])
                    if f.attr == "get_or_create" or f.attr == "update_or_create":
                        return None
                    return None
        if isinstance(node, ast.Subscript):
            base = self.kind(node.value)
            if base and base[0] == "qs":
                return ("obj", base[1])
        return None

    def check_args(self, model, ann, call, method):
        w = self.where(call)
        ctx = f"{model}.{method}()"
        if method in ("filter", "exclude", "get"):
            for kw in call.keywords:
                if kw.arg:
                    resolve_path(model, kw.arg, ann, w, ctx)
        elif method in ("get_or_create", "update_or_create"):
            for kw in call.keywords:
                if kw.arg == "defaults":
                    if isinstance(kw.value, ast.Dict):
                        for k in kw.value.keys:
                            if const_str(k):
                                resolve_path(model, const_str(k), ann, w, ctx + " defaults")
                elif kw.arg:
                    resolve_path(model, kw.arg, ann, w, ctx)
        elif method in ("create",):
            for kw in call.keywords:
                if kw.arg and (kw.arg not in MODELS[model].fields):
                    report("orm", w, f"{ctx}: {model} has no field '{kw.arg}'")
        elif method == "update":
            for kw in call.keywords:
                if kw.arg and kw.arg not in MODELS[model].fields:
                    report("orm", w, f"{ctx}: {model} has no field '{kw.arg}'")
        elif method in ("order_by", "select_related", "prefetch_related", "values", "values_list", "only", "defer"):
            for a in call.args:
                s = const_str(a)
                if s and s != "?":
                    resolve_path(model, s.lstrip("-"), ann, w, ctx)
            if method in ("values", "values_list", "annotate"):
                for kw in call.keywords:
                    pass
        elif method in ("annotate", "aggregate", "alias"):
            pass
        # aggregates / F / Q anywhere in the arguments
        for sub in ast.walk(call):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id in AGG and sub is not call:
                if sub.func.id == "Q":
                    for kw in sub.keywords:
                        if kw.arg:
                            resolve_path(model, kw.arg, ann, self.where(sub), "Q()")
                elif sub.args and const_str(sub.args[0]) and sub.func.id != "TruncDate" or (sub.args and const_str(sub.args[0])):
                    resolve_path(model, const_str(sub.args[0]), ann, self.where(sub), f"{sub.func.id}()")
                for kw in sub.keywords:
                    if kw.arg == "filter" and isinstance(kw.value, ast.Call):
                        for q in ast.walk(kw.value):
                            if isinstance(q, ast.Call) and getattr(q.func, "id", "") == "Q":
                                for k2 in q.keywords:
                                    if k2.arg:
                                        resolve_path(model, k2.arg, ann, self.where(q), "Q()")

    def visit_Call(self, node):
        f = node.func
        if isinstance(f, ast.Attribute):
            base = self.kind(f.value)
            if base and base[0] == "qs" and f.attr in (QS_KEEP | QS_END):
                self.check_args(base[1], base[2], node, f.attr)
        elif isinstance(f, ast.Name) and f.id in MODELS and node.keywords:
            for kw in node.keywords:
                if kw.arg and kw.arg not in MODELS[f.id].fields:
                    report("orm", self.where(node), f"{f.id}(...): no field '{kw.arg}'")
        self.generic_visit(node)

    def visit_Assign(self, node):
        self.generic_visit(node)
        k = self.kind(node.value)
        for t in node.targets:
            if isinstance(t, ast.Name):
                if k:
                    self.env[-1][t.id] = k
                else:
                    self.env[-1].pop(t.id, None)

    def visit_FunctionDef(self, node):
        self.env.append({})
        self.generic_visit(node)
        kinds = {self.kind(r.value) for r in ast.walk(node) if isinstance(r, ast.Return) and r.value is not None}
        if len(kinds) == 1 and None not in kinds and len(self.env) == 2:
            self.returns[node.name] = next(iter(kinds))
        self.env.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        # ModelForm Meta: model + fields/exclude
        for st in node.body:
            if isinstance(st, ast.ClassDef) and st.name == "Meta":
                model = fields = None
                for a in st.body:
                    if isinstance(a, ast.Assign) and len(a.targets) == 1 and isinstance(a.targets[0], ast.Name):
                        n = a.targets[0].id
                        if n == "model" and isinstance(a.value, ast.Name):
                            model = a.value.id
                        elif n in ("fields", "exclude") and isinstance(a.value, (ast.List, ast.Tuple)):
                            if model in MODELS:
                                for e in a.value.elts:
                                    s = const_str(e)
                                    if s and s not in MODELS[model].fields:
                                        report("orm", f"{rel(self.path)}:{e.lineno}", f"{node.name}.Meta.{n}: {model} has no field '{s}'")
        self.generic_visit(node)


def check_orm():
    collect_models()
    for path in sorted(ROOT.glob("apps/**/*.py")):
        if "migrations" in path.parts or path.name == "tests.py" or "management" in path.parts and False:
            continue
        ChainChecker(path).visit(ast.parse(path.read_text()))


# =============================================================================================== settings
def check_settings():
    text = (ROOT / "config/settings/base.py").read_text()
    tree = ast.parse(text)
    values = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                values[node.targets[0].id] = ast.literal_eval(node.value)
            except Exception:  # noqa: BLE001
                pass

    def dotted_exists(dotted):
        p = ROOT / dotted.replace(".", "/")
        return p.with_suffix(".py").exists() or (p / "__init__.py").exists()

    for app in values.get("INSTALLED_APPS", []):
        if app.startswith("apps.") and not dotted_exists(app.split(".apps.")[0] if ".apps." in app else app):
            report("settings", "config/settings/base.py", f"INSTALLED_APPS entry '{app}' has no module")
    on_disk = {p.name for p in (ROOT / "apps").iterdir() if (p / "apps.py").exists()}
    listed = {a.split(".")[1] for a in values.get("INSTALLED_APPS", []) if a.startswith("apps.")}
    for missing in sorted(on_disk - listed):
        report("settings", "config/settings/base.py", f"app 'apps/{missing}' exists but is not in INSTALLED_APPS")
    for mw in values.get("MIDDLEWARE", []):
        if mw.startswith("apps.") and not dotted_exists(".".join(mw.split(".")[:-1])):
            report("settings", "config/settings/base.py", f"middleware '{mw}' has no module")
    for tpl in values.get("TEMPLATES", []):
        for cp in tpl.get("OPTIONS", {}).get("context_processors", []):
            if cp.startswith("apps."):
                mod, func = cp.rsplit(".", 1)
                f = ROOT / (mod.replace(".", "/") + ".py")
                if not f.exists() or f"def {func}(" not in f.read_text():
                    report("settings", "config/settings/base.py", f"context processor '{cp}' not found")


def main():
    check_templates()
    check_python_urls()
    check_orm()
    check_settings()
    by_kind = {}
    for kind, where, message in problems:
        by_kind.setdefault(kind, []).append((where, message))
    print(f"URL names known: {len(URLS)} · models: {len(MODELS)} · templates: {len(list(TEMPLATES.rglob('*.html')))}")
    for kind in ("urls", "templates", "orm", "settings"):
        items = by_kind.get(kind, [])
        print(f"\n[{kind}] {'OK' if not items else str(len(items)) + ' problem(s)'}")
        for where, message in items:
            print(f"  {where}: {message}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
