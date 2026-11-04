import {useState} from 'react';
import {useAuth} from '@/context/AuthContext';
import {saveServerObservation} from '@/lib/serverResearch';
export function ValuationCapture({symbol,payload,disabled}:{symbol:string;payload:any;disabled:boolean}){
 const {user}=useAuth();const [status,setStatus]=useState(''),[saving,setSaving]=useState(false);
 return <div className="p-3 border border-border rounded-lg text-xs flex flex-wrap items-center gap-3"><button disabled={disabled||saving||!user||user.role==='viewer'} className="text-bloomberg disabled:opacity-40" onClick={async()=>{if(!user)return;setSaving(true);try{await saveServerObservation(symbol,'valuation',{...payload,captureSchema:2});setStatus('Valuation inputs, outputs and assumptions saved to server records.');}catch(e:any){setStatus(e.message);}finally{setSaving(false);}}}>{saving?'Saving…':'Save valuation snapshot'}</button><a href="#mkt/rdesk">Compare saved research</a><span role="status">{status||(disabled?'Wait for the selected valuation to finish loading.':'Saves a computed result with account/fund access controls and version history.')}</span></div>;
}
