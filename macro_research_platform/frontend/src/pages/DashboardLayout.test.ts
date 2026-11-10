import{it,expect}from'vitest';import{foldPanel}from'./DashboardPage';
it('folds without losing inputs and does not repeatedly replace the fold button',()=>{
 const section=document.createElement('div');section.id='regime';section.innerHTML='<div class="section-header"><h2>Signal Regime</h2></div><div><input value="kept"></div>';document.body.append(section);const input=section.querySelector('input');
 try{foldPanel(section,true);const button=section.querySelector('[data-fold-toggle]')!;expect(button.getAttribute('aria-expanded')).toBe('false');expect(section.querySelector('[data-fold]')).not.toBeNull();const text=button.firstChild;foldPanel(section,true);expect(button.firstChild).toBe(text);foldPanel(section,false);expect(section.querySelector('input')).toBe(input);expect(section.querySelector('[data-fold]')).toBeNull();expect(button.getAttribute('aria-expanded')).toBe('true');}finally{section.remove();}
});
