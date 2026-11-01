import { act } from 'react';import { createRoot } from 'react-dom/client';import { it,expect,vi } from 'vitest';import { LiveTV } from './LiveTV';
vi.mock('./shared',()=>({useJSON:(url:string)=>({data:url.includes('clips')?{clips:[]}:{channels:[{channel_id:'test',channel:'Test News',focus:'business',countries:['*'],region:'global',live:true,video_id:'abcdefghijk',title:'Live'}]},loading:false})}));
it('requests autoplay with sound and delegates autoplay permission to the player',async()=>{
 vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);const host=document.createElement('div');const root=createRoot(host);
 try{await act(async()=>root.render(<LiveTV iso={null} name={null}/>));const iframe=host.querySelector('iframe')!;const params=new URL(iframe.src).searchParams;expect(params.get('autoplay')).toBe('1');expect(params.get('mute')).toBe('0');expect(iframe.getAttribute('allow')).toContain('autoplay');expect(host.textContent).toContain('sound on by default');}finally{act(()=>root.unmount());vi.unstubAllGlobals();}
});
