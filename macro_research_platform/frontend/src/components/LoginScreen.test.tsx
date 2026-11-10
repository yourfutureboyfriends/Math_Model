import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { beforeEach,afterEach,it,expect,vi } from 'vitest';
import { LoginScreen } from './LoginScreen';
const mocks=vi.hoisted(()=>({login:vi.fn().mockResolvedValue(undefined)}));
vi.mock('@/context/AuthContext',()=>({useAuth:()=>({login:mocks.login})}));
let host:HTMLDivElement;let root:ReturnType<typeof createRoot>;
beforeEach(()=>{
 vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);localStorage.clear();sessionStorage.clear();mocks.login.mockClear();
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>({ok:true,json:async()=>url==='/api/auth/funds'?{funds:[{id:'main',name:'Alpha Capital',logo:true,logo_version:1,brand:{tagline:'Long-term research'}},{id:'beta',name:'Beta Partners',logo:true,logo_version:2,brand:{}}]}:{default_credentials_active:false}})));
 host=document.createElement('div');document.body.append(host);root=createRoot(host);
});
afterEach(()=>{act(()=>root.unmount());host.remove();vi.unstubAllGlobals();});
it('shows the selected fund identity and passes that fund to login',async()=>{
 await act(async()=>{root.render(<LoginScreen/>);});
 expect(host.querySelector('h1')?.textContent).toBe('Alpha Capital');expect(host.querySelector('img')?.getAttribute('src')).toContain('/api/auth/funds/main/logo');
 const select=host.querySelector('select')!;
 act(()=>{select.value='beta';select.dispatchEvent(new Event('change',{bubbles:true}));});
 expect(host.querySelector('h1')?.textContent).toBe('Beta Partners');expect(localStorage.getItem('macro.fund')).toBeNull(); // Selection does not switch another signed-in tab.
 const setValue=(label:string,text:string)=>{const input=host.querySelector(`[aria-label="${label}"]`)!;Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')!.set!.call(input,text);input.dispatchEvent(new Event('input',{bubbles:true}));};
 act(()=>{setValue('Username','analyst');setValue('Password','Example-password-123!');});
 await act(async()=>{host.querySelector('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));});
 expect(mocks.login).toHaveBeenCalledWith('analyst','Example-password-123!',undefined,'beta');
});
it('toggles password visibility without persisting the password',async()=>{
 await act(async()=>root.render(<LoginScreen/>));
 const password=host.querySelector('[aria-label="Password"]') as HTMLInputElement;
 expect(password.type).toBe('password');
 act(()=>{(host.querySelector('[aria-label="Show password"]') as HTMLButtonElement).click();});
 expect(password.type).toBe('text');
 act(()=>{(host.querySelector('[aria-label="Hide password"]') as HTMLButtonElement).click();});
 expect(password.type).toBe('password');
 expect(localStorage.getItem('password')).toBeNull();
});
it('shows a failed branding refresh as a retryable state',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new Error('offline')));
 await act(async()=>root.render(<LoginScreen/>));
 expect(host.textContent).toContain('Could not refresh fund details');
 expect(Array.from(host.querySelectorAll('button')).some(button=>button.textContent==='Try again')).toBe(true);
});
