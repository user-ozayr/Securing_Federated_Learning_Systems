import csv,json,os,shutil,sys,threading,time,_thread
from pathlib import Path
import torch
from fl_security.smpc import local_demo,mp_spdz

OUT=Path('/home/ubuntu/gemini/fl-security-research-spdz2k-thesis/research_output/runtime_optimization')

def profiled_serve_party(*args,**kwargs):
 import fl_security.smpc.mp_spdz_party_service as service
 original_run=service.subprocess.run;original_popen=service.subprocess.Popen
 mode=os.environ.get('MP_PROFILE_MEM_ORDER','off');profile=Path(os.environ['FL_MPSPDZ_PROFILE_DIR']);party_id=kwargs['party_id']
 def profiled_run(command,*a,**kw):
  if isinstance(command,(list,tuple)) and len(command)>1 and Path(command[1]).name=='compile.py':
   command=list(command)
   if mode=='on' and '-M' not in command:command.insert(4,'-M')
   started=time.monotonic();result=original_run(command,*a,**kw);elapsed=time.monotonic()-started
   record={'party_id':party_id,'compile_seconds':elapsed,'preserve_mem_order':mode=='on','returncode':result.returncode,'warning_present':'Order of memory instructions not preserved' in (result.stdout or '')}
   with (profile/f'compile_party_{party_id}.jsonl').open('a') as f:f.write(json.dumps(record)+'\n')
   (profile/f'compiler_party_{party_id}.log').write_text(result.stdout or '')
   return result
  return original_run(command,*a,**kw)
 def profiled_popen(command,*a,**kw):
  if isinstance(command,(list,tuple)) and command and Path(command[0]).name=='spdz2k-party.x':
   command=list(command);command.insert(1,'-v')
  return original_popen(command,*a,**kw)
 service.subprocess.run=profiled_run;service.subprocess.Popen=profiled_popen
 try:return service.serve_party(*args,**kwargs)
 finally:service.subprocess.run=original_run;service.subprocess.Popen=original_popen

def read_net():
 try:
  for line in Path('/proc/net/dev').read_text().splitlines():
   if line.strip().startswith('lo:'):
    v=line.split(':',1)[1].split();return int(v[0]),int(v[8])
 except Exception:pass
 return 0,0

def party_snapshot():
 result={}
 for proc in Path('/proc').iterdir():
  if not proc.name.isdigit():continue
  try:
   cmd=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='ignore')
   if 'spdz2k-party.x' not in cmd:continue
   args=cmd.split();party=int(args[args.index('-p')+1])
   st=(proc/'status').read_text();hwm=0
   for ln in st.splitlines():
    if ln.startswith('VmHWM:'):hwm=int(ln.split()[1])*1024
   stat=(proc/'stat').read_text().split();cpu=int(stat[13])+int(stat[14])
   io={}
   for ln in (proc/'io').read_text().splitlines():
    k,v=ln.split(':');io[k]=int(v)
   entry=result.setdefault(party,{'peak_rss':0,'cpu_ticks':0,'read_bytes':0,'write_bytes':0})
   entry['peak_rss']=max(entry['peak_rss'],hwm);entry['cpu_ticks']=max(entry['cpu_ticks'],cpu)
   entry['read_bytes']=max(entry['read_bytes'],io.get('read_bytes',0));entry['write_bytes']=max(entry['write_bytes'],io.get('write_bytes',0))
  except (FileNotFoundError,ProcessLookupError,ValueError,IndexError):continue
 return result

def probe(config):
 n=int(os.environ['MP_PROFILE_PARAMETERS']);mode=os.environ.get('MP_PROFILE_MEM_ORDER','off');run_dir=Path(os.environ['FL_MPSPDZ_PROFILE_DIR'])
 counts=[1,2,3];selected=[0,1,2];total=n+1;port=mp_spdz.client_port_base();parties=mp_spdz.load_party_configuration(3);hosts=[p.client_host for p in parties];round_id=f'profile-{n}-{mode}-{int(time.time())}'
 base={'weight':torch.zeros(n,dtype=torch.float32),'integer_buffer':torch.tensor(7,dtype=torch.int64)}
 encoder=__import__('fl_security.smpc.fixed_point',fromlist=['FixedPointEncoder']).FixedPointEncoder(100000)
 enc_times=[];orig_encode=mp_spdz._encode_weighted_model
 def encode_timer(*a,**kw):
  t=time.monotonic();ret=orig_encode(*a,**kw);enc_times.append(time.monotonic()-t);return ret
 mp_spdz._encode_weighted_model=encode_timer
 phases={};round_started=time.monotonic();active=True
 try:
  t=time.monotonic();mp_spdz.start_round(parties,round_id,selected,total,counts,3,port);phases['start_round_control_compile_party_launch_seconds']=time.monotonic()-t
  mp_spdz.check_round_running(parties,round_id)
  submit_times=[];input_wire_bytes=0
  for cid,count in enumerate(counts):
   state={'weight':torch.full((n,),cid*.01,dtype=torch.float32),'integer_buffer':torch.tensor(7,dtype=torch.int64)}
   t=time.monotonic()
   input_wire_bytes+=mp_spdz.submit_client_update(state,count,cid,hosts=hosts,port_base=port,credentials_dir=os.environ['FL_MPSPDZ_CLIENT_CREDENTIALS_DIR'],mp_spdz_home=os.environ['FL_MPSPDZ_HOME'],encoder=encoder,max_clients=3)
   submit_times.append(time.monotonic()-t)
  phases['client_encode_seconds_sum']=sum(enc_times);phases['client_submit_wall_seconds_sum']=sum(submit_times);phases['client_transfer_and_helper_overhead_seconds_sum']=max(0,sum(submit_times)-sum(enc_times))
  phases['client_wire_bytes_per_client_all_parties']=input_wire_bytes
  t=time.monotonic();mp_spdz.check_round_running(parties,round_id);phases['post_input_status_check_seconds']=time.monotonic()-t
  t=time.monotonic();result=mp_spdz.receive_weighted_average(base,hosts=hosts,port_base=port,credentials_dir=os.environ['FL_MPSPDZ_CLIENT_CREDENTIALS_DIR'],mp_spdz_home=os.environ['FL_MPSPDZ_HOME'],output_client_id=3,encoder=encoder,expected_total_examples=sum(counts));phases['aggregate_output_receive_seconds']=time.monotonic()-t
  expected=torch.full((n,),(.01*2+.02*3)/6,dtype=torch.float32);error=float((result['weight']-expected).abs().max().item())
  if not torch.equal(result['integer_buffer'],base['integer_buffer']):raise AssertionError('non-floating output ordering/buffer check failed')
  if error>0.00003:raise AssertionError(f'aggregate error {error}')
  t=time.monotonic();mp_spdz.finish_round(parties,round_id);phases['party_completion_cleanup_seconds']=time.monotonic()-t;active=False
  profile={'status':'PASS','parameter_count':n,'clients':3,'parties':3,'memory_order_flag':mode,'max_abs_error':error,'sample_counts':counts,'input_count':total,'phases':phases,'mpc_api_elapsed_seconds':time.monotonic()-round_started}
  (run_dir/'phase_profile.json').write_text(json.dumps(profile,indent=2))
  print(json.dumps(profile),flush=True)
 except BaseException:
  if active:
   try:mp_spdz.abort_round(parties,round_id)
   except Exception:pass
  raise
 finally:mp_spdz._encode_weighted_model=orig_encode

def main():
 n=int(sys.argv[1]);mode=sys.argv[2]
 run_id=f'params_{n}_memorder_{mode}_attempt_{int(time.time())}';run_dir=OUT/'raw'/run_id;run_dir.mkdir(parents=True,exist_ok=True)
 os.environ['FL_MPSPDZ_HOME']='/home/ubuntu/gemini/MP-SPDZ-v0.4.3';os.environ['MP_PROFILE_PARAMETERS']=str(n);os.environ['MP_PROFILE_MEM_ORDER']=mode;os.environ['FL_MPSPDZ_PROFILE_DIR']=str(run_dir)
 local_demo.run_flower_simulation=probe;local_demo.serve_party=profiled_serve_party
 real_rmtree=shutil.rmtree
 def keep_logs(path,*a,**kw):
  p=Path(path)
  if p.name.startswith('fl-mp-spdz-'):
   for src in p.glob('party-*/logs/*.log'):
    dst=run_dir/'party_logs'/f'{src.parent.parent.name}_{src.name}';dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
  return real_rmtree(path,*a,**kw)
 local_demo.shutil.rmtree=keep_logs
 stop=threading.Event();samples=[];net0=read_net();ticks=os.sysconf('SC_CLK_TCK');started=time.monotonic();failure={'reason':None}
 def monitor():
  while not stop.wait(.05):
   snap=party_snapshot()
   for pid,item in snap.items():
    if not any(x['party_id']==pid for x in samples):samples.append({'party_id':pid,'peak_rss':0,'cpu_ticks':0,'read_bytes':0,'write_bytes':0})
    dst=next(x for x in samples if x['party_id']==pid)
    for key in ('peak_rss','cpu_ticks','read_bytes','write_bytes'):dst[key]=max(dst[key],item[key])
   mem={}
   try:
    for line in Path('/proc/meminfo').read_text().splitlines():
     k,v=line.split(':',1);mem[k]=int(v.strip().split()[0])*1024
    if any(x['peak_rss']>6*1024**3 for x in samples):failure['reason']='party exceeded 6GiB RSS';_thread.interrupt_main();return
    if mem.get('MemAvailable',0)<5*1024**3:failure['reason']='MemAvailable below 5GiB';_thread.interrupt_main();return
    if shutil.disk_usage('/home/ubuntu').free<3*1024**3:failure['reason']='free disk below 3GiB';_thread.interrupt_main();return
    if time.monotonic()-started>300:failure['reason']='300-second benchmark cap';_thread.interrupt_main();return
   except Exception:pass
 thread=threading.Thread(target=monitor,daemon=True);thread.start();status='FAILED';msg='';err=''
 try:
  t=time.monotonic();local_demo.run_with_local_mp_spdz({'experiment':{'name':run_id,'rounds':1,'seed':121},'federated_learning':{'num_clients':3},'smpc':{'enabled':True,'backend':'mp_spdz_spdz2k','fixed_point_scale':100000,'num_aggregation_parties':3}});cleanup=time.monotonic()-t;status='PASS';msg='run completed'
 except KeyboardInterrupt:cleanup=time.monotonic()-started;status='ABORTED';msg=failure['reason'] or 'interrupt'
 except BaseException as exc:cleanup=time.monotonic()-started;status='FAILED';msg=repr(exc);err=__import__('traceback').format_exc()
 finally:
  stop.set();thread.join(timeout=2);local_demo.shutil.rmtree=real_rmtree
  net1=read_net();row={'parameter_count':n,'clients':3,'parties':3,'mem_order':mode,'status':status,'detail':msg,'cleanup_and_total_seconds':round(cleanup,3),'loopback_rx_delta':net1[0]-net0[0],'loopback_tx_delta':net1[1]-net0[1],'party_samples_json':json.dumps(samples,sort_keys=True),'cpu_seconds_estimate':round(sum(x['cpu_ticks'] for x in samples)/ticks,3),'party_disk_read_bytes_maxsum':sum(x['read_bytes'] for x in samples),'party_disk_write_bytes_maxsum':sum(x['write_bytes'] for x in samples)}
  with (OUT/'PROGRESSIVE_MPC_EXECUTION.csv').open('a',newline='') as f:
   w=csv.DictWriter(f,fieldnames=list(row));exists=OUT.joinpath('PROGRESSIVE_MPC_EXECUTION.csv').stat().st_size>0 if OUT.joinpath('PROGRESSIVE_MPC_EXECUTION.csv').exists() else False
   if not exists:w.writeheader()
   w.writerow(row)
  (run_dir/'runner_summary.json').write_text(json.dumps({'status':status,'detail':msg,'total_seconds':cleanup,'samples':samples,'error':err},indent=2))
  print(json.dumps({'status':status,'detail':msg,'total_seconds':cleanup,'samples':samples}),flush=True)
if __name__=='__main__':main()
