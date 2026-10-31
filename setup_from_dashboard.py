"""
ONE-TIME SETUP.
Reads your original dashboard HTML and makes three things:
  1. incoming/data.json   -> the data that is inside the dashboard today
  2. directors.json       -> which executives sit under which director (edit this file to change teams)
  3. docs/index.html      -> the same dashboard, with a login screen added

Run:  python setup_from_dashboard.py Blend_Dashborad_Final_all_directors.html
"""
import sys, re, json, os

if len(sys.argv) < 2:
    sys.exit("Usage: python setup_from_dashboard.py <your dashboard html file>")

src = open(sys.argv[1], encoding="utf-8").read()

# ---- split the original file: top part | data script | logic script ----
plain = [m for m in re.finditer(r"<script>", src)]
if len(plain) < 2:
    sys.exit("Could not find the two <script> blocks in the dashboard file.")
d_start = plain[0].start()
d_end = src.index("</script>", d_start)
l_start = plain[1].start()
l_end = src.index("</script>", l_start)
top = src[:d_start]
data_js = src[d_start + 8:d_end]
logic = src[l_start + 8:l_end]

# ---- 1. data ----
i = data_js.index("const DATA=") + len("const DATA=")
data, _ = json.JSONDecoder().raw_decode(data_js[i:])
os.makedirs("incoming", exist_ok=True)
json.dump(data, open("incoming/data.json", "w", encoding="utf-8"), separators=(",", ":"))
print("Saved incoming/data.json  (%d rows)" % len(data["L"]))

# ---- 2. directors ----
m = re.search(r"const DIRS=\{(.*?)\};", logic, re.S)
dirs = {}
for k, v in re.findall(r"'([^']+)':\[(.*?)\]", m.group(1), re.S):
    dirs[k] = re.findall(r"'([^']*)'", v)
json.dump(dirs, open("directors.json", "w", encoding="utf-8"), indent=2)
print("Saved directors.json      (%d directors)" % len(dirs))
# the dashboard will now take the team list from the (filtered) data it receives
logic = logic.replace(m.group(0), "const DIRS=DATA.DIRS;")

# ---- 3. index.html with login ----
extra_css = """
body.lock .app{display:none}
body:not(.lock) #lg{display:none}
#lg{position:fixed;inset:0;z-index:100;background:#f8fafc;display:flex;align-items:center;justify-content:center;padding:16px}
#lg .bx{background:#fff;border:1px solid var(--bd);border-radius:14px;padding:26px;width:100%;max-width:390px;box-shadow:0 10px 30px rgba(15,23,42,.08)}
#lg img{display:block;max-width:170px;margin:0 auto 14px}
#lg h1{font-size:18px;text-align:center;margin:0 0 16px}
#lg label{display:block;font-size:12px;color:var(--mu);margin:10px 0 4px}
#lg select,#lg input{width:100%;padding:9px 10px}
#lg button{width:100%;margin-top:16px;padding:10px;background:var(--brand);color:#fff;border:0;font-weight:600}
#lg .err{color:#b91c1c;font-size:12px;min-height:16px;margin-top:10px;text-align:center}
#me{position:fixed;right:12px;bottom:12px;z-index:40;background:#fff;border:1px solid var(--bd);border-radius:20px;padding:5px 8px 5px 12px;font-size:12px;display:flex;gap:8px;align-items:center;box-shadow:0 4px 14px rgba(15,23,42,.15)}
#me select,#me button{font-size:12px;padding:3px 8px}
"""
overlay = """
<div id="lg"><div class="bx">
<img id="lgimg" alt="Blend">
<h1>FSO to SO to Sales Dashboard</h1>
<label>Username</label><input id="lu" type="text" autocomplete="username">
<label>Who are you</label><select id="lw"></select>
<label>Password</label><input id="lp" type="password" autocomplete="current-password">
<label>Data as on</label><select id="ld"></select>
<button id="lb">Open dashboard</button>
<div class="err" id="le"></div>
</div></div>
<div id="me" hidden><span id="mn"></span><select id="md" title="Data as on"></select><button id="mo">Log out</button></div>
"""
login_js = r"""
(function(){
const IT=250000,G=i=>document.getElementById(i);
let MAN=null;
const fmt=d=>new Date(d+'T00:00:00').toLocaleDateString('en-GB',{day:'2-digit',month:'short',year:'numeric'});
const err=t=>G('le').textContent=t||'';
async function dec(buf,u,p){
  const b=new Uint8Array(buf),salt=b.slice(0,16),iv=b.slice(16,28),ct=b.slice(28);
  const km=await crypto.subtle.importKey('raw',new TextEncoder().encode(u+'|'+p),'PBKDF2',false,['deriveKey']);
  const key=await crypto.subtle.deriveKey({name:'PBKDF2',salt,iterations:IT,hash:'SHA-256'},km,{name:'AES-GCM',length:256},false,['decrypt']);
  const pt=await crypto.subtle.decrypt({name:'AES-GCM',iv},key,ct);
  const s=new Response(new Blob([pt]).stream().pipeThrough(new DecompressionStream('gzip')));
  return JSON.parse(await s.text());
}
async function attempt(u,p,id,date){
  err('Checking...');
  let r;
  try{r=await fetch('data/'+date+'/'+id+'.bin',{cache:'no-store'})}catch(e){err('Could not reach the server.');return false}
  if(!r.ok){err('No data for this person on '+fmt(date)+'.');return false}
  let data;
  try{data=await dec(await r.arrayBuffer(),u,p)}catch(e){err('Wrong username or password.');return false}
  sessionStorage.setItem('bd',JSON.stringify({u,p,id,date}));
  const who=MAN.people.find(x=>x.id==id);
  window.DATA=data;
  document.body.classList.remove('lock');
  G('mn').textContent=who.n;G('me').hidden=false;
  G('md').innerHTML=MAN.dates.map(d=>'<option value="'+d+'">'+fmt(d)+'</option>').join('');G('md').value=date;
  const s=document.createElement('script');s.textContent=G('logic').textContent;document.body.appendChild(s);
  return true;
}
async function init(){
  G('lgimg').src=document.querySelector('nav .logo').src;
  try{MAN=await (await fetch('data/manifest.json',{cache:'no-store'})).json()}catch(e){err('Could not load the dashboard list. Open this page through its web link.');return}
  const grp={all:'Admin',director:'Directors',executive:'Executives'};
  let h='';
  ['all','director','executive'].forEach(t=>{const l=MAN.people.filter(x=>x.t==t);if(l.length)h+='<optgroup label="'+grp[t]+'">'+l.map(x=>'<option value="'+x.id+'">'+x.n+'</option>').join('')+'</optgroup>'});
  G('lw').innerHTML=h;
  G('ld').innerHTML=MAN.dates.map(d=>'<option value="'+d+'">'+fmt(d)+'</option>').join('');
  G('lb').onclick=()=>attempt(G('lu').value.trim(),G('lp').value,G('lw').value,G('ld').value);
  G('lp').onkeydown=e=>{if(e.key=='Enter')G('lb').click()};
  G('md').onchange=()=>{const o=JSON.parse(sessionStorage.getItem('bd'));o.date=G('md').value;sessionStorage.setItem('bd',JSON.stringify(o));location.reload()};
  G('mo').onclick=()=>{sessionStorage.removeItem('bd');location.reload()};
  const sv=sessionStorage.getItem('bd');
  if(sv){const o=JSON.parse(sv);if(!MAN.dates.includes(o.date))o.date=MAN.dates[0];if(!await attempt(o.u,o.p,o.id,o.date))sessionStorage.removeItem('bd')}
}
init();
})();
"""
assert top.count("<body>") == 1 and "</style></head>" in top
top = top.replace("</style></head>", extra_css + "</style></head>", 1)
top = top.replace("<body>", '<body class="lock">' + overlay, 1)
logic_tag = '<script type="text/plain" id="logic">' + logic + "</script>\n"
assert "</script" not in logic
html = top + logic_tag + "<script>" + login_js + "</script></body></html>\n"
os.makedirs("docs", exist_ok=True)
open("docs/index.html", "w", encoding="utf-8").write(html)
print("Saved docs/index.html     (%d KB, contains NO data)" % (len(html) // 1024))
