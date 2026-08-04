import re, os, base64, hashlib, sys

SRC = r"C:\Users\Admin\Desktop\Peacekeeping Documents\Sổ tay\peacekeeper-app.html"
BASE = os.path.dirname(os.path.abspath(__file__))

print("Reading source HTML ...")
with open(SRC, "r", encoding="utf-8") as f:
    content = f.read()

print("Source size: %.2f MB" % (len(content) / 1024 / 1024))

def write_file(relpath, data):
    full = os.path.join(BASE, relpath)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb") as f:
        f.write(data)
    return len(data)

stats = {}

# ---------- 1. AUDIO ----------
print("\nExtracting AUDIO ...")
audio_count = 0

def audio_repl(m):
    global audio_count
    audio_count += 1
    b64 = m.group(1)
    try:
        data = base64.b64decode(b64)
    except Exception:
        print("  ! audio decode FAILED at #%d" % audio_count)
        return m.group(0)
    name = "audio%04d.mp3" % audio_count
    write_file(os.path.join("audio", name), data)
    return '"audio/%s"' % name

content, n = re.subn(r'"data:audio/mpeg;base64,([^"]+)"', audio_repl, content)
print("  audio extracted: %d" % audio_count)
stats['audio'] = audio_count

# ---------- 2. IMAGES ----------
print("\nExtracting IMAGES ...")
img_count = 0

def img_repl(m):
    global img_count
    img_count += 1
    ext = m.group(1)
    b64 = m.group(2)
    try:
        data = base64.b64decode(b64)
    except Exception:
        print("  ! image decode FAILED at #%d" % img_count)
        return m.group(0)
    name = "img%04d.%s" % (img_count, ext)
    write_file(os.path.join("img", name), data)
    return '"img/%s"' % name

content, n = re.subn(r'"data:image/(webp|png);base64,([^"]+)"', img_repl, content)
print("  images extracted: %d" % img_count)
stats['images'] = img_count

# ---------- 3. PDFs ----------
print("\nExtracting PDFs ...")
pdf_count = 0

pdf_script_re = re.compile(r'<script type="text/plain" id="(pdf-[a-z0-9]+)">([\s\S]*?)</script>')

def pdf_repl(m):
    global pdf_count
    pid = m.group(1)
    b64 = re.sub(r'\s+', '', m.group(2))
    try:
        data = base64.b64decode(b64)
    except Exception:
        print("  ! PDF decode FAILED for %s" % pid)
        return m.group(0)
    name = pid + ".pdf"
    write_file(os.path.join("pdfs", name), data)
    pdf_count += 1
    md5 = hashlib.md5(data).hexdigest()
    print("  %s -> %s (%.2f MB, md5 %s)" % (pid, name, len(data)/1024/1024, md5))
    return ""

content, n = pdf_script_re.subn(pdf_repl, content)
print("  pdf scripts replaced: %d" % n)
stats['pdfs'] = pdf_count

# ---------- 4. MARKDOWN ----------
print("\nExtracting MARKDOWN (doc-sotay) ...")
md_re = re.compile(r'<script type="text/markdown" id="doc-sotay">([\s\S]*?)</script>')
md_m = md_re.search(content)
if md_m:
    mdtext = md_m.group(1)
    mdtext = mdtext.lstrip('\n')
    write_file(os.path.join("docs", "sotay.md"), mdtext.encode("utf-8"))
    print("  sotay.md written: %.2f KB (%d chars)" % (len(mdtext)/1024, len(mdtext)))
    content = md_re.sub("", content, count=1)
    stats['markdown'] = len(mdtext)
else:
    print("  ! markdown block NOT FOUND")
    stats['markdown'] = 0

# ---------- 5. PDF.JS core + worker ----------
print("\nExtracting PDF.js ...")
core_re = re.compile(r'<script type="text/plain" id="pdfjs-core">([\s\S]*?)</script>')
worker_re = re.compile(r'<script type="text/plain" id="pdfjs-worker">([\s\S]*?)</script>')

core_m = core_re.search(content)
if core_m:
    js = core_m.group(1).lstrip('\n')
    write_file(os.path.join("js", "pdfjs-core.js"), js.encode("utf-8"))
    print("  pdfjs-core.js written: %.2f KB" % (len(js)/1024))
    content = core_re.sub("", content, count=1)
    stats['pdfjs-core'] = len(js)
else:
    print("  ! pdfjs-core NOT FOUND")
    stats['pdfjs-core'] = 0

worker_m = worker_re.search(content)
if worker_m:
    js = worker_m.group(1).lstrip('\n')
    write_file(os.path.join("js", "pdfjs-worker.js"), js.encode("utf-8"))
    print("  pdfjs-worker.js written: %.2f KB" % (len(js)/1024))
    content = worker_re.sub("", content, count=1)
    stats['pdfjs-worker'] = len(js)
else:
    print("  ! pdfjs-worker NOT FOUND")
    stats['pdfjs-worker'] = 0

# ---------- write index.html ----------
print("\nWriting index.html ...")
out = os.path.join(BASE, "index.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(content)
print("  index.html written: %.2f KB" % (len(content)/1024))
stats['index'] = len(content)

# ---------- 6. JS patches (pdf loader / markdown loader) ----------
print("\nApplying JS patches ...")

OLD_PDFINIT = """  pdfInit:function(){
    if(this._pdfInit)return this._pdfInit;
    var self=this;
    this._pdfInit=new Promise(function(res){
      if(window.pdfjsLib){self._pdfWorker();res();return;}
      // indirect eval → global scope; runs once, cached
      (0,eval)(document.getElementById('pdfjs-core').textContent);
      self._pdfWorker();
      res();
    });
    return this._pdfInit;
  },
  _pdfWorker:function(){
    if(this._workerUrl)return;
    var w=document.getElementById('pdfjs-worker').textContent;
    this._workerUrl=URL.createObjectURL(new Blob([w],{type:'text/javascript'}));
    pdfjsLib.GlobalWorkerOptions.workerSrc=this._workerUrl;
  },"""
NEW_PDFINIT = """  pdfInit:function(){
    if(this._pdfInit)return this._pdfInit;
    var self=this;
    this._pdfInit=new Promise(function(res){
      if(window.pdfjsLib){self._pdfWorker();res();return;}
      // fetch pdf.js core then indirect eval → global scope; runs once, cached
      fetch('js/pdfjs-core.js').then(function(r){return r.text();}).then(function(js){
        (0,eval)(js);
        return self._pdfWorker();
      }).then(function(){res();}).catch(function(e){
        if(window.LOG)LOG.error('pdf core load failed: '+e.message);
        res();
      });
    });
    return this._pdfInit;
  },
  _pdfWorker:function(){
    if(this._workerUrl)return Promise.resolve();
    var self=this;
    return fetch('js/pdfjs-worker.js').then(function(r){return r.text();}).then(function(w){
      self._workerUrl=URL.createObjectURL(new Blob([w],{type:'text/javascript'}));
      pdfjsLib.GlobalWorkerOptions.workerSrc=self._workerUrl;
    });
  },"""
if OLD_PDFINIT in content:
    content = content.replace(OLD_PDFINIT, NEW_PDFINIT)
    print("  patched pdfInit+_pdfWorker")
else:
    print("  ! pdfInit/_pdfWorker pattern NOT FOUND")

OLD_PDFOPEN = """      var b64=self.docTxt(id),bin=atob(b64),arr=new Uint8Array(bin.length);
      for(var i=0;i<bin.length;i++)arr[i]=bin.charCodeAt(i);
      return pdfjsLib.getDocument({data:arr}).promise;"""
NEW_PDFOPEN = """      return pdfjsLib.getDocument({url:'pdfs/'+id+'.pdf'}).promise;"""
if OLD_PDFOPEN in content:
    content = content.replace(OLD_PDFOPEN, NEW_PDFOPEN)
    print("  patched pdfOpen")
else:
    print("  ! pdfOpen pattern NOT FOUND")

OLD_MD = "h+='<div class=\"mdd\">'+self.md2html(self.docTxt(doc.id))+'</div></details>';"
NEW_MD = "h+='<div class=\"mdd\" id=\"mdd-'+doc.id+'\"></div></details>';\n        self.loadDocMarkdown(doc.id);"
if OLD_MD in content:
    content = content.replace(OLD_MD, NEW_MD)
    print("  patched rDocs markdown")
else:
    print("  ! rDocs markdown pattern NOT FOUND")

MD_LOADER = """  loadDocMarkdown:function(id){
    var self=this;
    if(this._mdCache)return this._mdFill(id);
    fetch('docs/sotay.md').then(function(r){return r.text();}).then(function(txt){
      self._mdCache=txt;
      self._mdFill(id);
    }).catch(function(e){
      var el=document.getElementById('mdd-'+id);
      if(el)el.textContent='Markdown load error: '+e.message;
    });
  },
  _mdFill:function(id){
    if(!this._mdCache)return;
    var el=document.getElementById('mdd-'+id);
    if(el)el.innerHTML=this.md2html(this._mdCache);
  },
"""
ANCHOR = "  // PDF.js reader (the \"view\" feature"
if "  loadDocMarkdown:function(id){" in content:
    print("  loadDocMarkdown already present")
elif ANCHOR in content:
    content = content.replace(ANCHOR, MD_LOADER + "\n" + ANCHOR, 1)
    print("  added loadDocMarkdown helper")
else:
    print("  ! loadDocMarkdown anchor NOT FOUND")

with open(out, "w", encoding="utf-8") as f:
    f.write(content)
print("  index.html rewritten: %.2f KB" % (len(content)/1024))

# sanity: no remaining data: URIs
remaining = re.findall(r'data:(audio|image)/[a-z]+;base64,[^"]+', content)
print("\nRemaining data: URIs (should be 0):", len(remaining))

print("\n=== SUMMARY ===")
for k, v in stats.items():
    print("  %-12s %s" % (k, v))
print("\nDONE")
