"""
DAILY BUILD.
Reads incoming/data.json + users.csv + directors.json
and writes one locked file per person into docs/data/<date>/ .

Run:   python build.py
Other: python build.py --date 2026-10-30      (force the date label)
       python build.py --random-passwords     (give everyone a strong random password)
       python build.py --keep 90              (how many days stay online, default 90)
"""
import os, sys, json, csv, gzip, hashlib, secrets, shutil, argparse, string
from datetime import datetime
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

USERNAME = "blend2026"        # the common username everyone types
ITERATIONS = 250000           # must match the number inside index.html
DIRECTOR_PW, OTHER_PW = "123", "124"   # starting passwords (change in users.csv!)

ap = argparse.ArgumentParser()
ap.add_argument("--date"); ap.add_argument("--keep", type=int, default=90)
ap.add_argument("--random-passwords", action="store_true")
a = ap.parse_args()

if not os.path.exists("incoming/data.json"):
    sys.exit("incoming/data.json not found.")
data = json.load(open("incoming/data.json", encoding="utf-8"))
dirs = json.load(open("directors.json", encoding="utf-8"))

# ---- which date is this data for? ----
date = a.date
if not date:
    try: date = datetime.strptime(data["RD"], "%d %b %Y").strftime("%Y-%m-%d")
    except Exception: date = datetime.today().strftime("%Y-%m-%d")

# ---- people list ----
execs = sorted({r[2] for r in data["L"]} | {r[2] for r in data["PF"]} |
               {r[3] for r in data["PS"]} | {r[3] for r in data["X"]})
execs = [e for e in execs if e and not e.startswith("<")]
wanted = [("all", "All directors")] + [("director", d) for d in dirs] + [("executive", e) for e in execs]

# ---- users.csv (name, type, password) ----
users = {}
if os.path.exists("users.csv"):
    for r in csv.DictReader(open("users.csv", encoding="utf-8-sig")):
        users[(r["type"].strip(), r["name"].strip())] = r["password"].strip()
rand = lambda: "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(10))
for t, n in wanted:
    if a.random_passwords or (t, n) not in users:
        users[(t, n)] = rand() if a.random_passwords else (OTHER_PW if t == "executive" else DIRECTOR_PW)
        if not a.random_passwords: print("  new login added to users.csv:", t, n)
with open("users.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["type", "name", "password"])
    for t, n in wanted: w.writerow([t, n, users[(t, n)]])

# ---- helpers ----
def subset(allowed):
    L = data["L"]
    keep = [i for i, r in enumerate(L) if allowed is None or r[2] in allowed]
    SO, SI = {}, {}
    for j, i in enumerate(keep):
        if str(i) in data["SO"]: SO[str(j)] = data["SO"][str(i)]
        if str(i) in data["SI"]: SI[str(j)] = data["SI"][str(i)]
    ok = (lambda e: True) if allowed is None else (lambda e: e in allowed)
    PF = [r for r in data["PF"] if ok(r[2])]; PS = [r for r in data["PS"] if ok(r[3])]
    prods = {r[1] for r in PF} | {r[2] for r in PS}
    if allowed is None: D = dirs
    else:
        D = {k: [e for e in v if e in allowed] for k, v in dirs.items()}
        D = {k: v for k, v in D.items() if v}
    return {"L": [L[i] for i in keep], "SO": SO, "SI": SI,
            "X": [x for x in data["X"] if ok(x[3])], "PF": PF, "PS": PS,
            # blank stock values (NaN) are saved as null; the dashboard treats both as 0
            "GS": {k: (None if v != v else v) for k, v in data["GS"].items() if allowed is None or k in prods},
            "RD": data["RD"], "DIRS": D}

def lock(payload, pw):
    raw = gzip.compress(json.dumps(payload, separators=(",", ":")).encode(), 9)
    salt, iv = os.urandom(16), os.urandom(12)
    key = PBKDF2HMAC(hashes.SHA256(), 32, salt, ITERATIONS).derive((USERNAME + "|" + pw).encode())
    return salt + iv + AESGCM(key).encrypt(iv, raw, None)

pid = lambda t, n: hashlib.sha1((t + ":" + n).encode()).hexdigest()[:10]

# ---- write the locked files ----
out = os.path.join("docs", "data", date)
if os.path.isdir(out): shutil.rmtree(out)
os.makedirs(out)
people, total = [], 0
for t, n in wanted:
    allowed = None if t == "all" else (set(dirs[n]) | {n}) if t == "director" else {n}
    p = subset(allowed)
    people.append({"id": pid(t, n), "n": n if t != "director" else n, "t": t})
    if not p["L"] and not p["PF"] and not p["PS"]: continue
    blob = lock(p, users[(t, n)]); total += len(blob)
    open(os.path.join(out, pid(t, n) + ".bin"), "wb").write(blob)
print("Locked files written for %s: %d people, %.1f MB" % (date, len(wanted), total / 1e6))

# ---- manifest (list of names and dates; contains no business data) ----
dd = os.path.join("docs", "data")
dates = sorted([d for d in os.listdir(dd) if os.path.isdir(os.path.join(dd, d))], reverse=True)
for old in dates[a.keep:]: shutil.rmtree(os.path.join(dd, old))
dates = dates[:a.keep]
json.dump({"dates": dates, "people": people}, open(os.path.join(dd, "manifest.json"), "w"), indent=1)

# ---- backup of the input ----
os.makedirs(os.path.join("archive", date), exist_ok=True)
shutil.copy("incoming/data.json", os.path.join("archive", date, "data.json"))

weak = [n for (t, n), p in users.items() if len(p) < 8]
if weak:
    print("\nWARNING: %d logins have a short password (under 8 characters)." % len(weak))
    print("Anyone who downloads the site files can try short passwords very fast and open that data.")
    print("For real protection run:  python build.py --random-passwords   (then share each person's password from users.csv)")
print("Done. Dates online:", len(dates))
