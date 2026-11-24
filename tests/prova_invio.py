# Prova di invio su stampanti finte, senza Home Assistant: python3 -m venv v; v/bin/pip install aiohttp; v/bin/python tests/prova_invio.py
import asyncio,sys,types,struct,time,importlib.util,os
B=os.environ.get('SRC',os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'custom_components', 'stampa_remota'))
def mod(n,**k):
    m=types.ModuleType(n);m.__dict__.update(k);sys.modules[n]=m;return m
mod('homeassistant');mod('homeassistant.core',HomeAssistant=object);mod('homeassistant.helpers')
SESS=[None]
mod('homeassistant.helpers.aiohttp_client',async_get_clientsession=lambda h,verify_ssl=True:SESS[0])
class Store:
    def __init__(s,*a):pass
    async def async_load(s):return []
    async def async_save(s,x):pass
mod('homeassistant.helpers.storage',Store=Store)
P=mod('sr');P.__path__=[B]
class Doc:
    pages=1;fmt='image/urf';copies_in_data=True;original=False;selected=None
    def __init__(s):s.parts=[b'DATI'*2000]
class Opt:
    copies=1;mono=True;fit=True;layout=None;paper='A4'
C=mod('sr.convert',PAPER_IPP={'A4':'iso_a4_210x297mm'},DEFAULT_MARGIN_PT=10,Document=Doc,Options=Opt,Printer=lambda *a:None,ConvertError=type('CE',(Exception,),{}),Source=object,build=lambda *a:Doc(),paper_pt=lambda p:(595,842))
mod('sr.const',EVENT='stampa_remota_evento')
def load(n):
    sp=importlib.util.spec_from_file_location('sr.'+n,f'{B}/{n}.py');m=importlib.util.module_from_spec(sp);sys.modules['sr.'+n]=m;sp.loader.exec_module(m);return m
ipp=load('ipp');M=load('manager')
import aiohttp;from aiohttp import web
M.RETRY_BUSY=.15;M.RETRY_OFFLINE=.2;
if hasattr(M,'VERIFY_WAIT'):M.VERIFY_WAIT=.1
_s=asyncio.sleep
async def fast(t,*a):await _s(min(t,.2))
M.asyncio=types.SimpleNamespace(**{k:getattr(asyncio,k) for k in dir(asyncio) if not k.startswith('__')});M.asyncio.sleep=fast
_rf=M.PrintHub.refresh
async def rf(s,c,max_age=0):return await _rf(s,c,0)
M.PrintHub.refresh=rf
class FP: # stampante finta
    def __init__(s):s.jobs={};s.n=0;s.prints=0;s.state=3;s.reasons=['none'];s.mode='ok';s.getjobs=True;s.keep=True;s.first=True;s.cancelled=[];s.busy=0;s.hang=asyncio.Event()
    def add(s,name,st=9):s.n+=1;s.jobs[s.n]=[name,st];return s.n
    async def h(s,r):
        b=await r.read();op=struct.unpack('>H',b[2:4])[0];g=ipp.decode_response(b);o=g.group(1)
        def resp(st,groups=()):
            x=struct.pack('>HHI',0x101,st,1)+b'\x01'+ipp._attr(0x47,'attributes-charset','utf-8')
            for t,a in groups:
                x+=bytes([t])
                for tag,n,v in a:x+=ipp._attrs(tag,n,v if isinstance(v,list) else [v])
            return web.Response(body=x+b'\x03',content_type='application/ipp')
        if op==0xB:return resp(0,[(4,[(0x23,'printer-state',s.state),(0x44,'printer-state-reasons',s.reasons)])])
        if op==0xA:
            if not s.getjobs:return resp(0x501)
            w=o['which-jobs'][0];l=[(i,v) for i,v in s.jobs.items() if (v[1]>=7)==(w=='completed') and (s.keep or v[1]<7)]
            return resp(0,[(2,[(0x21,'job-id',i),(0x42,'job-name',v[0])]) for i,v in l])
        if op==9:
            j=s.jobs.get(o['job-id'][0])
            return resp(0,[(2,[(0x23,'job-state',j[1]),(0x44,'job-state-reasons','none')])]) if j else resp(0x406)
        if op==8:
            i=o['job-id'][0];s.cancelled.append(i);s.jobs[i][1]=7;return resp(0)
        if op==2:
            n=o['job-name'][0]
            if s.busy>0:s.busy-=1;return resp(0x507)
            m=s.mode
            if m!='ok' and s.first:
                s.first=False
                if m=='lost':r.transport.close();return web.Response() # non ricevuto
                i=s.add(n,9 if m=='done' else 6);s.prints+=1
                if m=='slow_ok':
                    await s.hang.wait();s.jobs[i][1]=9;return resp(0,[(2,[(0x21,'job-id',i)])])
                r.transport.close();return web.Response()
            i=s.add(n);s.prints+=1;return resp(0,[(2,[(0x21,'job-id',i)])])
class Hass:
    def __init__(s):s.ev=[];s.bus=types.SimpleNamespace(async_fire=lambda e,d:s.ev.append((d['stato'],d['errore'],d['avviso'])))
    def async_create_background_task(s,c,n):return asyncio.ensure_future(c)
    async def async_add_executor_job(s,f,*a):return f(*a)
async def caso(nome,setup,attesa,mid=None,avvia=True):
    fp=FP();setup(fp);app=web.Application(client_max_size=10**8);app.router.add_post('/ipp/print',fp.h);rn=web.AppRunner(app);await rn.setup()
    sk=__import__('socket').socket();sk.bind(('127.0.0.1',0));port=sk.getsockname()[1];sk.close()
    async def su():
        st=web.TCPSite(rn,'127.0.0.1',port);await st.start()
    if avvia:await su()
    async with aiohttp.ClientSession() as se:
        SESS[0]=se;h=Hass();hub=M.PrintHub(h);await hub.async_load();c=await hub.add_printer('e','Canon',f'ipp://127.0.0.1:{port}/ipp/print','A4',True)
        j=await hub.submit('prova.pdf',b'x',Opt(),'utente')
        if mid:await mid(fp,hub,j,su)
        t=time.time()
        while j['stato'] in M.ACTIVE and time.time()-t<6:await _s(.05)
        await _s(.4)
        ok=attesa(fp,j,h)
        print('OK ' if ok else 'NO ',nome,'| stato',j['stato'],'| copie',fp.prints,'|',j['errore'][:70],'|',[e[2] for e in h.ev if e[2]][:1]);c.worker.cancel();await hub.async_stop()
    await rn.cleanup();return ok
async def main():
    R=[]
    R.append(await caso('normale',lambda f:None,lambda f,j,h:j['stato']=='fatto' and f.prints==1))
    R.append(await caso('ricevuto, poi silenzio, già stampato',lambda f:setattr(f,'mode','done'),lambda f,j,h:j['stato']=='fatto' and f.prints==1))
    async def carta(f,hub,j,su):
        await _s(1.2);f.state=3;f.reasons=['none']
        for k in f.jobs.values():k[1]=9
    def s1(f):f.mode='stop';f.add('vecchio.pdf')
    async def ferma(f,hub,j,su):
        await _s(.1);f.state=5;f.reasons=['media-empty-error'];await carta(f,hub,j,su)
    R.append(await caso('carta non pescata a metà invio',s1,lambda f,j,h:j['stato']=='fatto' and f.prints==1 and any('Carta' in e[2] for e in h.ev),ferma))
    def s2(f):f.state=5;f.reasons=['media-empty-error']
    R.append(await caso('carta finita prima di inviare',s2,lambda f,j,h:j['stato']=='fatto' and f.prints==1 and j['avviso']=='' and any('Carta' in e[2] for e in h.ev),carta))
    def s3(f):f.mode='lost';f.add('vecchio.pdf')
    R.append(await caso('non ricevuto (storico presente): rimanda',s3,lambda f,j,h:j['stato']=='fatto' and f.prints==1))
    R.append(await caso('non ricevuto, stampante senza storico: incerto',lambda f:setattr(f,'mode','lost'),lambda f,j,h:j['stato']=='errore' and 'incerto' in j['errore'] and f.prints==0))
    def s4(f):f.mode='done';f.getjobs=False
    R.append(await caso('Get-Jobs non supportato: incerto',s4,lambda f,j,h:j['stato']=='errore' and f.prints==1 and 'incerto' in j['errore']))
    def s5(f):f.mode='done';f.keep=False
    R.append(await caso('storico dimenticato: incerto, nessuna copia doppia',s5,lambda f,j,h:j['stato']=='errore' and f.prints==1))
    async def acc(f,hub,j,su):await _s(.8);await su()
    R.append(await caso('stampante spenta, poi accesa',lambda f:None,lambda f,j,h:j['stato']=='fatto' and f.prints==1,acc,False))
    R.append(await caso('occupata 3 volte',lambda f:setattr(f,'busy',3),lambda f,j,h:j['stato']=='fatto' and f.prints==1))
    def s6(f):f.mode='slow_ok'
    async def ann(f,hub,j,su):
        while not f.prints:await _s(.02)
        await hub.cancel(j['id']);f.hang.set();await _s(.5)
    R.append(await caso('annullata durante l invio: tolta dalla stampante',s6,lambda f,j,h:j['stato']=='annullato' and f.cancelled==[1],ann))
    def s7(f):f.mode='done';f.add('prova.pdf')
    R.append(await caso('stesso nome già stampato ieri',s7,lambda f,j,h:j['stato']=='fatto' and f.prints==1 and j['job_id']==2))
    print(sum(R),'/',len(R))
asyncio.run(main())
