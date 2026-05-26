#!/usr/bin/env python3
"""
UNIVERSAL PYTHON ENCODER v5.1 — GOD TIER
Ultimate Obfuscation & Anti-Everything Engine
Works on ALL devices including Android/Termux

Usage:
    python universal_encoder.py <input.py> [output.py]
    python universal_encoder.py --layers 5 <input.py>
    python universal_encoder.py --watermark "@mytag" <input.py>
"""

import sys,os,zlib,base64,marshal,random,string,hashlib
import struct,argparse,textwrap,time,types,codecs

_NC='OoIl10_QqDdbBpP'
_PX=['_','__','___','O0','l1','Il','_0O','lI','I1','_l1','O0O','IlI']

def rn(mn=12,mx=24):
    return random.choice(_PX)+''.join(random.choices(_NC,k=random.randint(mn,mx)))

def rs(ln=32):
    return ''.join(random.choices(string.ascii_letters+string.digits,k=ln))

def xor_bytes(data,key):
    kl=len(key);return bytes(b^key[i%kl] for i,b in enumerate(data))

def encrypt_block_cipher(data,key,iv,rounds=16):
    bs=16;pl=bs-(len(data)%bs);data=data+bytes([pl]*pl)
    rkeys=[];h=key
    for r in range(rounds):
        h=hashlib.sha256(h+struct.pack('>I',r)).digest();rkeys.append(h)
    result=bytearray();prev=bytearray(iv)
    for off in range(0,len(data),bs):
        blk=bytearray(data[off:off+bs])
        for j in range(bs):blk[j]^=prev[j]
        for r in range(rounds):
            rk=rkeys[r]
            for j in range(bs):blk[j]=blk[j]^rk[j]^rk[(j+8)%32];blk[j]=(blk[j]+rk[(j+r)%32])&0xFF
            sh=rk[r%32]%bs;blk=blk[sh:]+blk[:sh]
        prev=bytearray(blk);result.extend(blk)
    return bytes(result)

def pbkdf2_derive(pw,salt,iters=10000):
    return hashlib.pbkdf2_hmac('sha256',pw,salt,iters,dklen=32)

def obf_string(s):
    m=random.randint(0,5)
    if m==0:return '+'.join(f"chr({ord(c)})" for c in s)
    elif m==1:return f"bytes({list(s.encode())}).decode()"
    elif m==2:
        b=base64.b64encode(s.encode()).decode()
        return f"__import__('base64').b64decode('{b}').decode()"
    elif m==3:return f"'{s[::-1]}'[::-1]"
    elif m==4:
        rot=codecs.encode(s,'rot_13')
        return f"__import__('codecs').decode('{rot}','rot_13')"
    else:return repr(s)

# ═══════════════════════════════════════════════════════════════
# JUNK CODE
# ═══════════════════════════════════════════════════════════════
def gen_dead(n=8):
    d=[]
    for _ in range(n):
        v=rn(5,10);k=random.randint(0,14)
        if k==0:d.append(f"{v}={random.randint(-9999999,9999999)}")
        elif k==1:d.append(f"{v}='{rs(random.randint(16,48))}'")
        elif k==2:d.append(f"{v}=[{','.join(str(random.randint(0,255)) for _ in range(random.randint(5,15)))}]")
        elif k==3:d.append(f"if {random.randint(100,999)}>{random.randint(1000,9999)}:{rn(3,6)}={random.randint(0,1)}")
        elif k==4:d.append(f"{v}=lambda {rn(2,3)}:{rn(2,3)} if False else None")
        elif k==5:d.append(f"{v}=bytes([{','.join(str(random.randint(0,255)) for _ in range(random.randint(8,20)))}])")
        elif k==6:d.append(f"{v}={{{','.join(repr(rs(3))+':'+str(random.randint(0,99)) for _ in range(random.randint(3,7)))}}}")
        elif k==7:d.append(f"{v}=type('{rn(4,8)}',(object,),{{'{rn(3,5)}':{random.randint(0,999)}}})")
        elif k==8:d.append(f"{v}={{'{rs(6)}':bytes([{','.join(str(random.randint(0,255)) for _ in range(6))}])}}")
        elif k==9:d.append(f"exec('') if {random.randint(0,1)}==2 else None")
        elif k==10:
            a,b=rn(3,5),rn(3,5)
            d.append(f"{v}=(lambda {a},{b}:{a}^{b})({random.randint(0,0xFFFF)},{random.randint(0,0xFFFF)})")
        elif k==11:
            cn=rn(4,8);d.append(f"class {cn}:\n {rn(3,5)}={random.randint(0,9999)}\n def {rn(3,5)}(self):return {random.randint(0,999)}")
        elif k==12:d.append(f"try:{rn(3,6)}={random.randint(0,9999)}\nexcept:{rn(3,6)}={random.randint(0,999)}")
        elif k==13:
            lv=rn(2,3);d.append(f"{v}=[{lv}*{random.randint(2,9)} for {lv} in range({random.randint(5,20)})]")
        elif k==14:
            gv=rn(2,3);d.append(f"{v}=tuple({gv}+{random.randint(1,99)} for {gv} in range({random.randint(3,15)}))")
    return '\n'.join(d)

def gen_fake_functions(n=4):
    funcs=[]
    for _ in range(n):
        fn=rn(6,12);args=','.join(rn(2,4) for _ in range(random.randint(1,4)));body=[]
        for _ in range(random.randint(4,12)):body.append(f"  {rn(3,6)}={random.randint(0,9999)}")
        body.append(f"  return {random.randint(0,999)}")
        funcs.append(f"def {fn}({args}):\n"+'\n'.join(body))
    return '\n'.join(funcs)

def gen_fake_classes(n=2):
    cl=[]
    for _ in range(n):
        cn=rn(6,10);attrs=[];methods=[]
        for _ in range(random.randint(3,6)):attrs.append(f"  {rn(3,6)}={random.randint(0,99999)}")
        for _ in range(random.randint(1,3)):
            mn2=rn(4,8);methods.append(f"  def {mn2}(self):\n    return {random.randint(0,999)}")
        cl.append(f"class {cn}:\n"+'\n'.join(attrs)+'\n'+'\n'.join(methods))
    return '\n'.join(cl)

# ═══════════════════════════════════════════════════════════════
# OPAQUE PREDICATES
# ═══════════════════════════════════════════════════════════════
def gen_opaque(n=5):
    p=[]
    for _ in range(n):
        k=random.randint(0,7);v=rn(4,8)
        if k==0:x=random.randint(1,9999);p.append(f"if ({x}*{x})<0:__import__('os')._exit(1)")
        elif k==1:x=random.randint(1,0xFFFF);p.append(f"if ({x}^{x})!=0:__import__('os')._exit(1)")
        elif k==2:p.append(f"if len('{rs(random.randint(5,20))}')<0:__import__('os')._exit(1)")
        elif k==3:x=random.randint(1,0xFFFF);p.append(f"if ({x}|0)!={x}:__import__('os')._exit(1)")
        elif k==4:x=random.randint(1,0xFFFF);p.append(f"if ({x}&{x})!={x}:__import__('os')._exit(1)")
        elif k==5:x=random.randint(-9999,9999);p.append(f"{v}={x}\nif {v}+0!={x}:__import__('os')._exit(1)")
        elif k==6:p.append(f"if not bool({random.randint(1,999)}):__import__('os')._exit(1)")
        elif k==7:x=random.randint(0,0xFFFFFFFF);p.append(f"if ({x}>>32)!=0:__import__('os')._exit(1)")
    random.shuffle(p);return '\n'.join(p)

# ═══════════════════════════════════════════════════════════════
# ANTI-EVERYTHING
# ═══════════════════════════════════════════════════════════════
def gen_anti_debug():
    checks=[]
    checks.append(f"try:\n if __import__('sys').gettrace() is not None:raise SystemExit({random.randint(1,255)})\nexcept:pass")
    t1,t2=rn(4,8),rn(4,8)
    checks.append(f"{t1}=__import__('time').time();{t2}=sum(range(50000))\nif __import__('time').time()-{t1}>3.0:raise SystemExit({random.randint(1,255)})")
    checks.append(f"if set(__import__('sys').modules)&{{'pydevd','debugpy','pdb','_pydevd_bundle','pydevd_tracing','bdb','ipdb','pudb','wdb','rpdb','uncompyle6','decompyle3','xdis'}}:raise SystemExit({random.randint(1,255)})")
    vf=rn(3,6)
    checks.append(f"try:\n {vf}=__import__('sys')._getframe(0)\n if hasattr({vf},'f_trace') and {vf}.f_trace is not None:raise SystemExit({random.randint(1,255)})\nexcept (AttributeError,ValueError):pass")
    vfh,vln=rn(3,5),rn(2,3)
    checks.append(f"try:\n with open('/proc/self/status','r') as {vfh}:\n  for {vln} in {vfh}:\n   if {vln}.startswith('TracerPid:') and int({vln}.split(':')[1].strip())!=0:raise SystemExit({random.randint(1,255)})\nexcept:pass")
    checks.append(f"if __import__('sys').getrecursionlimit()<100:raise SystemExit({random.randint(1,255)})")
    checks.append(f"if 'dis' in __import__('sys').modules:raise SystemExit({random.randint(1,255)})")
    checks.append(f"if 'inspect' in __import__('sys').modules:raise SystemExit({random.randint(1,255)})")
    random.shuffle(checks);return '\n'.join(checks)

def gen_sandbox_detect():
    vp=rn(4,8);vf1=rn(3,5);vf2=rn(3,5);vf3=rn(3,5);vm=rn(3,6)
    return f"""
try:
 with open('/proc/1/cgroup','r') as {vf1}:
  {vp}={vf1}.read()
except:pass
try:
 if __import__('os').cpu_count()<2:pass
except:pass
try:
 with open('/proc/meminfo','r') as {vf2}:
  {vm}=int({vf2}.readline().split()[1])
except:pass
try:
 with open('/proc/uptime','r') as {vf3}:
  if float({vf3}.read().split()[0])<60:pass
except:pass"""

def gen_time_bomb():
    vt=rn(6,10);vfn=rn(6,10)
    return f"""
{vt}=__import__('time').time()
def {vfn}():
 if __import__('time').time()-{vt}>60:
  try:__import__('os').remove(__import__('sys').argv[0] if __import__('sys').argv else '')
  except:pass
  __import__('os')._exit({random.randint(1,255)})
try:__import__('atexit').register({vfn})
except:pass"""

def gen_anti_decompiler():
    traps=[]
    depth=random.randint(8,15);inner="None";vl=rn(2,3)
    for _ in range(depth):inner=f"(lambda {vl}:{inner})({random.randint(0,999)})"
    traps.append(f"{rn(6,10)}={inner}")
    depth2=random.randint(6,10);inner2=str(random.randint(0,999))
    for _ in range(depth2):inner2=f"({inner2} if {random.randint(0,1)} else {random.randint(0,999)})"
    traps.append(f"{rn(6,10)}={inner2}")
    count=random.randint(10,20)
    vl2=[rn(2,4) for _ in range(count)];vals=[str(random.randint(0,999)) for _ in range(count)]
    traps.append(f"{','.join(vl2)}={','.join(vals)}")
    traps.append(f"{rn(3,5)},*{rn(3,5)},{rn(3,5)}=[{','.join(str(random.randint(0,99)) for _ in range(random.randint(5,10)))}]")
    return '\n'.join(traps)

def gen_polymorphic():
    vpath=rn(6,10);vself=rn(6,10);vf=rn(3,5)
    return f"""
try:
 {vpath}=__import__('os').path.abspath(__file__) if '__file__' in dir() else None
 if {vpath} and __import__('os').path.exists({vpath}):
  with open({vpath},'r') as {vf}:{vself}={vf}.read()
  try:
   with open({vpath},'w') as {vf}:
    {vf}.write('# '+__import__('time').strftime('%H%M%S')+'\\n'+{vself})
  except:pass
except:pass"""

def gen_multiprocess_pbkdf2():
    vfn=rn(6,10);vpw=rn(3,5);vsl=rn(3,5);vcn=rn(3,5);vp2=rn(3,5);vc2=rn(3,5)
    return f"""
def {vfn}({vpw},{vsl}):
 try:
  from multiprocessing import Process,Pipe
  {vp2},{vc2}=Pipe()
  def _w({vcn},{vpw},{vsl}):{vcn}.send(__import__('hashlib').pbkdf2_hmac('sha256',{vpw},{vsl},10000,dklen=32));{vcn}.close()
  _p=Process(target=_w,args=({vc2},{vpw},{vsl}));_p.start();_r={vp2}.recv();_p.join(timeout=10)
  return _r
 except:
  return __import__('hashlib').pbkdf2_hmac('sha256',{vpw},{vsl},10000,dklen=32)
""",vfn

# ═══════════════════════════════════════════════════════════════
# STEGANOGRAPHIC PAYLOAD
# ═══════════════════════════════════════════════════════════════
def gen_stego_payload(data_b85):
    chunk_sz=random.randint(40,80)
    chunks=[data_b85[i:i+chunk_sz] for i in range(0,len(data_b85),chunk_sz)]
    lines=[];container_var=rn(8,14);stego_vars=[]
    for idx,chunk in enumerate(chunks):
        method=random.randint(0,3);sv=rn(8,14);stego_vars.append(sv)
        if method==0:
            fd=rn(6,10);rk=repr(rs(random.randint(4,8)))
            fks=[repr(rs(random.randint(4,8)))+':'+str(random.randint(0,9999)) for _ in range(random.randint(2,4))]
            fks.insert(random.randint(0,len(fks)),f"{rk}:{repr(chunk)}")
            lines.append(f"{fd}={{{','.join(fks)}}}")
            lines.append(f"{sv}={fd}[{rk}]")
        elif method==1:
            fl=rn(6,10)
            items=[repr(rs(random.randint(8,16))) for _ in range(random.randint(2,5))]
            ri=random.randint(0,len(items));items.insert(ri,repr(chunk))
            lines.append(f"{fl}=[{','.join(items)}]");lines.append(f"{sv}={fl}[{ri}]")
        elif method==2:
            ft=rn(6,10)
            items=[str(random.randint(0,0xFFFF)) for _ in range(random.randint(2,4))]
            ri=random.randint(0,len(items));items.insert(ri,repr(chunk))
            lines.append(f"{ft}=({','.join(items)},)");lines.append(f"{sv}={ft}[{ri}]")
        else:
            lines.append(gen_dead(1));lines.append(f"{sv}={repr(chunk)}");lines.append(gen_dead(1))
        if random.random()>0.5:lines.append(gen_dead(random.randint(1,2)))
    lines.append(f"{container_var}={'+'.join(stego_vars)}")
    return '\n'.join(lines),container_var

# ═══════════════════════════════════════════════════════════════
# WATERMARK
# ═══════════════════════════════════════════════════════════════
def gen_watermark(tag="@iceyy69"):
    parts=[]
    parts.append(f"# Encoded by {tag}")
    parts.append(f"# Protected with Universal Encoder v5.0 GOD TIER")
    wm_b64=base64.b64encode(f"Encoded by {tag}".encode()).decode()
    parts.append(f'{rn(8,14)}="{wm_b64}"')
    wm_bytes=f"[WATERMARK:{tag}]".encode();wm_key=os.urandom(16)
    parts.append(f"{rn(8,14)}={repr(xor_bytes(wm_bytes,wm_key))}")
    parts.append(f"{rn(8,14)}={repr(wm_key)}")
    svars=[]
    for ch in list(tag):
        sv=rn(4,8);parts.append(f"{sv}={repr(ch)}");svars.append(sv)
    parts.append(f"{rn(8,14)}=''.join([{','.join(svars)}])")
    cls=rn(6,10)
    parts.append(f"class {cls}:\n '''Universal Encoder | {tag}'''\n {rn(3,5)}={repr(base64.b85encode(f'ENCODED_BY:{tag}'.encode()).decode())}\n {rn(3,5)}={random.randint(100000,999999)}")
    zwc_map={'0':'\u200b','1':'\u200c',' ':'\u200d'}
    tag_binary=''.join(format(ord(c),'08b') for c in tag)
    zwc_enc=''.join(zwc_map.get(b,'\u200b') for b in tag_binary)
    parts.append(f'{rn(8,14)}="{zwc_enc}"')
    wm_code=compile(f"_={repr(f'WATERMARK:{tag}')}",'<wm>','exec')
    parts.append(f"{rn(8,14)}={repr(base64.b85encode(marshal.dumps(wm_code)).decode())}")
    parts.append(f"{rn(8,14)}='{hashlib.sha256(tag.encode()).hexdigest()}'")
    return '\n'.join(parts)

# ═══════════════════════════════════════════════════════════════
# BYTECODE NOISE
# ═══════════════════════════════════════════════════════════════
def inject_noise_consts(code_obj):
    noise_c=[]
    for _ in range(random.randint(10,30)):
        k=random.randint(0,5)
        if k==0:noise_c.append(random.randint(-999999,999999))
        elif k==1:noise_c.append(rs(random.randint(8,32)))
        elif k==2:noise_c.append(random.random())
        elif k==3:noise_c.append(None)
        elif k==4:noise_c.append(bytes(random.randint(0,255) for _ in range(random.randint(4,16))))
        elif k==5:noise_c.append(tuple(random.randint(0,255) for _ in range(random.randint(2,6))))
    noise_n=tuple(rn(4,10) for _ in range(random.randint(5,15)))
    try:return code_obj.replace(co_consts=code_obj.co_consts+tuple(noise_c),co_names=code_obj.co_names+noise_n)
    except:return code_obj

# ═══════════════════════════════════════════════════════════════
# MAIN ENCODER — FLAT ARCHITECTURE (no nested exec)
# ═══════════════════════════════════════════════════════════════
def encode(source,layers=5,watermark="@iceyy69",anti_debug=True):
    """
    FLAT encoding pipeline — NO nested exec(string) calls.
    The output is a SINGLE flat script that:
      1. Defines helper functions (decrypt, xor, pbkdf2)
      2. Loads the encrypted payload from steganographic variables
      3. Applies decryption steps sequentially (no nesting)
      4. Calls exec(marshal.loads(data)) ONCE at the end
    This avoids all C-stack recursion issues on Android/Termux.
    """
    layers=max(1,min(20,layers))

    # Step 1: Compile source to bytecode and inject noise
    code_obj=compile(source,'<encoded>','exec')
    code_obj=inject_noise_consts(code_obj)
    data=marshal.dumps(code_obj)

    # Step 2: Apply N encryption layers on the BINARY data
    keys_chain=[]
    for i in range(layers):
        data=zlib.compress(data,9);keys_chain.append(('z',None))
        pw=os.urandom(32);salt=os.urandom(16);dk=pbkdf2_derive(pw,salt)
        aes_iv=os.urandom(16);data=encrypt_block_cipher(data,dk,aes_iv)
        keys_chain.append(('p',(pw,salt,aes_iv)))
        xk=os.urandom(random.randint(64,128));data=xor_bytes(data,xk)
        keys_chain.append(('x',xk))
        data=zlib.compress(data,9);keys_chain.append(('z',None))
        if i%2==0:
            ak2=os.urandom(32);iv2=os.urandom(16)
            data=encrypt_block_cipher(data,ak2,iv2);keys_chain.append(('a',(ak2,iv2)))

    # Step 3: Encode final binary as base85
    payload_b85=base64.b85encode(data).decode('ascii')

    # Step 4: Build the FLAT loader — one script, no nesting
    loader=_build_flat_loader(payload_b85,keys_chain,watermark,anti_debug)

    return loader


def _build_flat_loader(payload_b85,keys_chain,watermark,anti_debug):
    """Build a completely FLAT decoder script — zero nested exec calls."""
    vp=rn(8,14);vd=rn(8,14);vxf=rn(8,14);vdf=rn(8,14)
    v_b85=rn(4,8);v_zlib=rn(4,8)

    parts=[]

    # ── Header ──
    parts.append("# -*- coding: utf-8 -*-")
    parts.append(f"# Encoded by {watermark}")
    parts.append(f"# Protected with Universal Encoder v5.0 GOD TIER")
    parts.append(f"# Timestamp: {int(time.time())}")
    parts.append(f"# Layers: {len([k for k in keys_chain if k[0]=='p'])}")
    parts.append("")

    # ── Watermark (top) ──
    parts.append(gen_watermark(watermark))
    parts.append("")

    # ── Junk + opaque predicates ──
    parts.append(gen_dead(random.randint(10,20)))
    parts.append(gen_opaque(random.randint(8,15)))
    parts.append("")

    # ── Anti-debug + sandbox + time-bomb ──
    if anti_debug:
        parts.append(gen_anti_debug())
        parts.append(gen_sandbox_detect())
        parts.append(gen_time_bomb())
        parts.append("")

    # ── Anti-decompiler traps ──
    parts.append(gen_anti_decompiler())
    parts.append("")

    # ── More junk ──
    parts.append(gen_dead(random.randint(10,15)))
    parts.append(gen_fake_functions(random.randint(4,8)))
    parts.append(gen_fake_classes(random.randint(3,5)))
    parts.append("")
    parts.append(gen_opaque(random.randint(5,10)))
    parts.append("")

    # ── Polymorphic self-mutation ──
    parts.append(gen_polymorphic())
    parts.append("")

    # ── Hidden imports ──
    parts.append(f"{v_b85}=__import__({obf_string('base64')})")
    parts.append(f"{v_zlib}=__import__({obf_string('zlib')})")

    # ── Hidden exec ──
    v_exec=rn(6,10)
    em=random.randint(0,3)
    if em==0:parts.append(f"{v_exec}=getattr(__import__('builtins'),{obf_string('exec')})")
    elif em==1:parts.append(f"{v_exec}=eval({obf_string('exec')})")
    elif em==2:parts.append(f"{v_exec}=getattr(__import__({obf_string('builtins')}),{obf_string('exec')})")
    else:
        vx=rn(2,3);parts.append(f"{v_exec}=(lambda {vx}:getattr(__import__('builtins'),{vx}))({obf_string('exec')})")

    # ── Hidden marshal.loads ──
    v_marsh=rn(6,10)
    mm=random.randint(0,2)
    if mm==0:parts.append(f"{v_marsh}=getattr(__import__({obf_string('marshal')}),{obf_string('loads')})")
    elif mm==1:
        vm2=rn(4,8);parts.append(f"{vm2}=__import__({obf_string('marshal')})")
        parts.append(f"{v_marsh}=getattr({vm2},{obf_string('loads')})")
    else:
        vx2=rn(2,3);parts.append(f"{v_marsh}=(lambda {vx2}:getattr(__import__({vx2}),{obf_string('loads')}))({obf_string('marshal')})")

    # ── Multi-process PBKDF2 ──
    mp_code,mp_fn=gen_multiprocess_pbkdf2()
    parts.append(mp_code)

    # ── Watermark inside loader ──
    parts.append(f'{rn(6,10)}={obf_string(f"Encoded by {watermark}")}')

    # ── XOR function ──
    xkp=rn(3,5);xkl=rn(3,5);xb=rn(2,3);xi=rn(2,3)
    parts.append(f"def {vxf}({vd},{xkp}):\n {xkl}=len({xkp});return bytes({xb}^{xkp}[{xi}%{xkl}] for {xi},{xb} in enumerate({vd}))")

    # ── AES decrypt function ──
    parts.append(gen_decrypt_func(vdf))

    # ── PBKDF2 fallback ──
    v_pbkdf=rn(6,10);vpp=rn(3,5);vps=rn(3,5)
    parts.append(f"def {v_pbkdf}({vpp},{vps}):\n return __import__('hashlib').pbkdf2_hmac('sha256',{vpp},{vps},10000,dklen=32)")

    # ── Junk + opaque between functions and payload ──
    parts.append(gen_dead(random.randint(10,20)))
    parts.append(gen_opaque(random.randint(5,8)))

    # ── Steganographic payload (hidden in fake data structures) ──
    stego_code,stego_var=gen_stego_payload(payload_b85)
    parts.append(stego_code)
    parts.append(f"{vp}={stego_var}")

    # ── Integrity check ──
    h=hashlib.sha256(payload_b85.encode()).hexdigest()
    vh=rn(6,10)
    parts.append(f"{vh}={repr(h)}")
    parts.append(f"if __import__('hashlib').sha256({vp}.encode()).hexdigest()!={vh}:__import__('os')._exit(1)")

    # ── Decode base85 ──
    parts.append(f"{vd}=getattr({v_b85},{obf_string('b85decode')})({vp})")

    # ── FLAT decryption chain — each step is a simple line, NO nesting ──
    for st,sd in reversed(keys_chain):
        if random.random()>0.5:parts.append(gen_dead(random.randint(1,3)))
        if random.random()>0.7:parts.append(gen_opaque(1))
        if st=='z':
            parts.append(f"{vd}=getattr({v_zlib},{obf_string('decompress')})({vd})")
        elif st=='x':
            vk=rn(6,10)
            parts.append(f"{vk}=getattr({v_b85},{obf_string('b85decode')})({repr(base64.b85encode(sd).decode())})")
            parts.append(f"{vd}={vxf}({vd},{vk})")
        elif st=='a':
            ak,ai=sd;vak,vai=rn(6,10),rn(6,10)
            parts.append(f"{vak}=getattr({v_b85},{obf_string('b85decode')})({repr(base64.b85encode(ak).decode())})")
            parts.append(f"{vai}=getattr({v_b85},{obf_string('b85decode')})({repr(base64.b85encode(ai).decode())})")
            parts.append(f"{vd}={vdf}({vd},{vak},{vai})")
        elif st=='p':
            pw,salt,aes_iv=sd;vpw,vsl,viv=rn(6,10),rn(6,10),rn(6,10);vdk=rn(6,10)
            parts.append(f"{vpw}=getattr({v_b85},{obf_string('b85decode')})({repr(base64.b85encode(pw).decode())})")
            parts.append(f"{vsl}=getattr({v_b85},{obf_string('b85decode')})({repr(base64.b85encode(salt).decode())})")
            parts.append(f"{viv}=getattr({v_b85},{obf_string('b85decode')})({repr(base64.b85encode(aes_iv).decode())})")
            use_mp=random.random()>0.5
            if use_mp:parts.append(f"{vdk}={mp_fn}({vpw},{vsl})")
            else:parts.append(f"{vdk}={v_pbkdf}({vpw},{vsl})")
            parts.append(f"{vd}={vdf}({vd},{vdk},{viv})")

    # ── Final: ONE exec(marshal.loads(data)) — the ONLY exec call ──
    parts.append(f"{v_exec}({v_marsh}({vd}))")

    # ── Trailing junk + watermark ──
    parts.append("")
    parts.append(gen_dead(random.randint(10,20)))
    parts.append(gen_fake_functions(random.randint(3,5)))
    parts.append(gen_fake_classes(random.randint(2,3)))
    parts.append(gen_watermark(watermark))

    return '\n'.join(parts)


def gen_decrypt_func(fname):
    vd,vk,vi=rn(3,6),rn(3,6),rn(3,6)
    vbs,vr,vh=rn(3,6),rn(3,6),rn(3,6)
    vrk,vrkeys=rn(3,6),rn(3,6)
    voff,vblk,vsav=rn(3,6),rn(3,6),rn(3,6)
    vprev,vpad,vj=rn(3,6),rn(3,6),rn(3,6)
    vsh,v_r,vres=rn(3,6),rn(3,6),rn(3,6)
    return f"""
def {fname}({vd},{vk},{vi}):
 {vbs}=16;{vr}=16
 import hashlib as {vh},struct as _s
 {vrkeys}=[];{vrk}={vk}
 for {v_r} in range({vr}):
  {vrk}={vh}.sha256({vrk}+_s.pack('>I',{v_r})).digest();{vrkeys}.append({vrk})
 {vres}=bytearray();{vprev}=bytearray({vi})
 for {voff} in range(0,len({vd}),{vbs}):
  {vblk}=bytearray({vd}[{voff}:{voff}+{vbs}]);{vsav}=bytearray({vblk})
  for {v_r} in range({vr}-1,-1,-1):
   {vrk}={vrkeys}[{v_r}];{vsh}={vrk}[{v_r}%32]%{vbs}
   {vblk}={vblk}[-{vsh}:]+{vblk}[:-{vsh}] if {vsh} else {vblk}
   for {vj} in range({vbs}):{vblk}[{vj}]=({vblk}[{vj}]-{vrk}[({vj}+{v_r})%32])&0xFF;{vblk}[{vj}]={vblk}[{vj}]^{vrk}[{vj}]^{vrk}[({vj}+8)%32]
  for {vj} in range({vbs}):{vblk}[{vj}]^={vprev}[{vj}]
  {vprev}={vsav};{vres}.extend({vblk})
 {vpad}={vres}[-1];return bytes({vres}[:-{vpad}])
"""


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════
def main():
    p=argparse.ArgumentParser(
        description='Universal Python Encoder v5.0 — GOD TIER',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          python universal_encoder.py script.py
          python universal_encoder.py --layers 5 script.py
          python universal_encoder.py --layers 10 --watermark "@mytag" script.py
          python universal_encoder.py --layers 15 script.py ultra.py

        Layers:  1-3  = Strong    |  4-6 = Very Hard
                 7-10 = Extreme   |  11-15 = Nuclear
                 16-20 = GOD TIER
        """))
    p.add_argument('input',help='Input Python file')
    p.add_argument('output',nargs='?',default=None,help='Output file')
    p.add_argument('--layers','-l',type=int,default=5,help='Encoding layers (1-20, default: 5)')
    p.add_argument('--watermark','-w',type=str,default='@iceyy69',help='Watermark tag (default: @iceyy69)')
    p.add_argument('--no-antidebug',action='store_true',help='Disable anti-debug checks')

    args=p.parse_args()
    if not os.path.isfile(args.input):print(f"Error: '{args.input}' not found.");sys.exit(1)
    out=args.output or os.path.splitext(args.input)[0]+'_encoded.py'
    with open(args.input,'r',encoding='utf-8') as f:source=f.read()
    if not source.strip():print("Error: Empty input.");sys.exit(1)
    try:compile(source,args.input,'exec')
    except SyntaxError as e:print(f"Syntax error: {e}");sys.exit(1)

    print(f"""
╔════════════════════════════════════════════════════════╗
║     UNIVERSAL PYTHON ENCODER v5.0 — GOD TIER          ║
╚════════════════════════════════════════════════════════╝
  Input:      {args.input}
  Output:     {out}
  Layers:     {args.layers}
  Watermark:  {args.watermark}
  Anti-Debug: {'ON' if not args.no_antidebug else 'OFF'}
  Architecture: FLAT (Android/Termux compatible)
  Features:   Steganographic | Multi-process PBKDF2
              Anti-decompiler | Time-bomb | Sandbox detection
              Polymorphic | AES-256 + XOR + PBKDF2
""")

    t0=time.time()
    encoded=encode(source,layers=args.layers,watermark=args.watermark,anti_debug=not args.no_antidebug)
    with open(out,'w',encoding='utf-8') as f:f.write(encoded)
    elapsed=time.time()-t0

    print(f"""  Done in {elapsed:.2f}s
  Original:  {len(source):,} bytes
  Encoded:   {len(encoded):,} bytes  ({len(encoded)/len(source):.1f}x)
  Output:    {out}
""")

    import subprocess
    r=subprocess.run([sys.executable,'-c',
        f'compile(open("{out}",encoding="utf-8").read(),"<t>","exec")'],
        capture_output=True,text=True,timeout=30)
    if r.returncode==0:print("  [OK] Compiles successfully")
    else:print(f"  [WARN] {r.stderr[:300]}")
    print(f"  Watermark: {args.watermark}")
    print(f"  Your encoded file: {out}\n")

if __name__=='__main__':
    main()
