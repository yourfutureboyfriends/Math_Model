import { beforeEach,expect,it } from 'vitest';
import { currentFund } from './fund';
beforeEach(()=>{sessionStorage.clear();localStorage.clear();});
it('keeps a signed-in tab on its own fund when another tab changes the remembered fund',()=>{
 sessionStorage.setItem('macro.fund.session','main');localStorage.setItem('macro.fund','bifs');
 expect(currentFund()).toBe('main');
});
it('uses the remembered fund only when the tab has no selected session fund',()=>{
 localStorage.setItem('macro.fund','bifs');expect(currentFund()).toBe('bifs');
 localStorage.clear();expect(currentFund()).toBe('main');
});
