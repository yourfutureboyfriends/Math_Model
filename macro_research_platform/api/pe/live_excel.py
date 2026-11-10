"""Editable, noncircular annual opening-balance LBO workbook, alongside frozen API results."""
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter as col
from openpyxl.workbook.properties import CalcProperties
from api.pe import lbo, underwriting


def append(wb, inp):
    p = underwriting.prepare(inp)
    reference = lbo.run({**inp, 'interest_on': 'opening'})
    ins = wb.create_sheet('Live inputs')
    mod = wb.create_sheet('Live model')
    ret = wb.create_sheet('Live returns')
    ins.append(['Editable annual model · native currency units'])
    ins.append(['Blue cells are inputs. Opening-balance interest; snapshot sheets keep the API interest method.'])
    values = {3: ('Revenue', p['revenue']), 4: ('Reported EBITDA', inp['ebitda']),
              5: ('Accepted adjustments', 0), 6: ('Underwritten EBITDA', '=B4+B5'),
              7: ('Entry multiple', p['entry_multiple']), 8: ('Exit multiple', p.get('exit_multiple') if p.get('exit_multiple') is not None else p['entry_multiple']),
              9: ('Exit year', reference['exit_year']), 10: ('Transaction fee', p.get('transaction_fee_pct', 0)),
              11: ('Financing fee', p.get('financing_fee_pct', 0)), 12: ('Minimum cash', p.get('min_cash', 0)),
              13: ('Rollover equity', p.get('rollover_equity', 0)), 14: ('Tax rate', p.get('tax_rate', 0)),
              15: ('Interest cap', p.get('interest_cap_pct') if p.get('interest_cap_pct') is not None else 0),
              16: ('Cap enabled (1/0)', int(p.get('interest_cap_pct') is not None)),
              17: ('EBIT basis (1); EBITDA (0)', int(p.get('interest_cap_basis') == 'ebit')),
              18: ('NOL utilization share', p.get('nol_utilization_pct', 1)), 19: ('Opening NOL', p.get('opening_nol', 0)),
              20: ('Opening disallowed interest', p.get('opening_disallowed_interest', 0)),
              21: ('Interest deduction floor', p.get('interest_deduction_floor', 0)),
              22: ('Annual NOL limit', p.get('annual_nol_limit') if p.get('annual_nol_limit') is not None else 1e99),
              23: ('Revolver commitment', (p.get('revolver') or {}).get('commitment', 0)),
              24: ('Revolver spread', (p.get('revolver') or {}).get('spread', 0)),
              25: ('Commitment fee', (p.get('revolver') or {}).get('commitment_fee', 0)),
              26: ('Revolver drawn at close', (p.get('revolver') or {}).get('drawn_at_close', 0)),
              27: ('Revolver maturity year', (p.get('revolver') or {}).get('tenor') or 99),
              28: ('Cash sweep share', p.get('sweep_pct', 1)), 29: ('Exit fee', p.get('exit_fee_pct', 0)),
              30: ('MIP share', p.get('mip_pct', 0)), 31: ('Adjust forecast margins (1/0)', int(bool(p.get('apply_adjustments_to_plan'))))}
    for r, (name, value) in values.items():
        ins.cell(r, 1, name); ins.cell(r, 2, value)
    adj_start = 36
    terms = []
    for i, item in enumerate(p.get('ebitda_adjustments') or []):
        r = adj_start+i
        for j, value in enumerate([item.get('label'), item.get('amount', 0), int(bool(item.get('approved'))), item.get('source')], 1):
            ins.cell(r, j, value)
        terms.append(f'B{r}*C{r}')
    ins['B5'] = '='+('+'.join(terms) or '0')
    tranche_start = max(40, adj_start+len(terms)+3)
    for j, value in enumerate(['Tranche', 'Multiple', 'Fixed amount', 'Use fixed (1/0)', 'Floating (1/0)', 'Spread', 'Coupon', 'Floor', 'Amortization', 'Tenor', 'Sweep (1/0)', 'PIK (1/0)'], 1):
        ins.cell(tranche_start-1, j, value)
    tranches = [t for t in p.get('tranches', []) if (float(t.get('amount', 0)) if t.get('amount') is not None else float(t.get('multiple', 0))*p['ebitda']) > 0]
    for i, t in enumerate(tranches):
        for j, value in enumerate([t['name'], t.get('multiple', 0), t.get('amount', 0), int(t.get('amount') is not None),
                                   int(bool(t.get('floating'))), t.get('spread', 0), t.get('coupon', 0), t.get('floor', 0),
                                   t.get('amort_pct', 0), t.get('tenor') or 99, int(bool(t.get('sweep'))),
                                   int(t.get('kind') == 'mezz' and t.get('pik', True))], 1):
            ins.cell(tranche_start+i, j, value)
    path_start = tranche_start+len(tranches)+4
    path_keys = ['revenue_growth', 'ebitda_margin', 'dna_pct', 'capex_pct', 'nwc_pct', 'base_rate_path', 'interest_income', 'tax_adjustment']
    n = reference['years']
    for i, key in enumerate(path_keys):
        ins.cell(path_start+i, 1, key)
        value = inp.get(key, 0)
        if key == 'base_rate_path': value = inp.get(key) or inp.get('base_rate', 0)
        if key == 'ebitda_margin': value = inp.get(key, inp['ebitda']/inp['revenue'])
        for j, v in enumerate(lbo._path(value, n, key), 3): ins.cell(path_start+i, j, v)
    def I(r, c='B'): return f"'Live inputs'!{c}{r}"
    def M(r, c): return f"'Live model'!{c}{r}"
    mod['A1'] = 'Editable annual model · OPENING-balance interest · native currency units'
    labels = {3:'Revenue',4:'Growth',5:'EBITDA margin',6:'EBITDA',7:'D&A',8:'EBIT',9:'Capex',10:'Change NWC',11:'Base rate',
              12:'Cash interest',13:'PIK interest',14:'Fee amortization',15:'Interest income',16:'Tax adjustment',17:'Interest deduction limit',
              18:'Opening disallowed interest',19:'Interest deductible',20:'Closing disallowed interest',21:'Pretax income for tax',
              22:'Opening NOL',23:'NOL used',24:'Closing NOL',25:'Cash tax',26:'Levered FCF',27:'Mandatory repayment',
              28:'Opening cash',29:'Opening revolver',30:'Cash available before revolver',31:'Revolver draw',32:'Revolver repayment',
              33:'Closing revolver',34:'Available after revolver',35:'Sweep pool',36:'Total sweep',37:'Closing cash',38:'Total debt',
              39:'Net debt',40:'Reserve shortfall',41:'Revolver maturity payment'}
    for r, name in labels.items(): mod.cell(r, 1, name)
    starts = [50+i*10 for i in range(len(tranches))]
    mod['B3'] = '='+I(3); mod['B37'] = '='+I(12); mod['B33'] = '='+I(26)
    for i, t in enumerate(tranches):
        r, ir = starts[i], tranche_start+i
        for offset, name in enumerate(['Opening principal','Rate','Interest','PIK','Mandatory','After mandatory','Cash sweep','Closing principal','Fee amortization','Cash interest']):
            mod.cell(r+offset, 1, f"{t['name']} · {name}")
        mod.cell(r, 2, f'=IF({I(ir,"D")}=1,{I(ir,"C")},{I(ir)}*{I(6)})')
        mod.cell(r+7, 2, f'=B{r}')
    def total(rows, c): return '+'.join(f'{c}{r}' for r in rows) or '0'
    for y in range(1, n+1):
        c, prev = col(y+2), col(y+1)
        mod.cell(2,y+2,y)
        f = lambda r, expression: mod.cell(r,y+2,'='+expression)
        path = lambda key: I(path_start+path_keys.index(key), c)
        f(4,path('revenue_growth')); f(3,f'{prev}3*(1+{c}4)')
        f(5,f'MIN(0.95,{path("ebitda_margin")}+IF({I(31)}=1,{I(5)}/{I(3)},0))')
        f(6,f'{c}3*{c}5');f(7,f'{c}3*{path("dna_pct")}');f(8,f'{c}6-{c}7')
        f(9,f'{c}3*{path("capex_pct")}');f(10,f'({c}3-{prev}3)*{path("nwc_pct")}');f(11,path('base_rate_path'))
        for i, t in enumerate(tranches):
            r, ir = starts[i], tranche_start+i
            f(r,f'{prev}{r+7}')
            f(r+1,f'IF({I(ir,"E")}=1,MAX({c}11,{I(ir,"H")})+{I(ir,"F")},{I(ir,"G")})')
            f(r+2,f'{c}{r}*{c}{r+1}'); f(r+3,f'{c}{r+2}*{I(ir,"L")}')
            annual_amort = '0' if t.get('kind')=='mezz' else f'MIN({c}{r},{I(ir,"I")}*B{r})'
            f(r+4,f'IF({c}2>={I(ir,"J")},{c}{r}+{c}{r+3},{annual_amort})')
            f(r+5,f'{c}{r}+{c}{r+3}-{c}{r+4}')
            prior = total([x+6 for x in starts[:i]],c)
            f(r+6,f'IF({I(ir,"K")}=1,MIN({c}{r+5},MAX(0,{c}35-({prior}))),0)')
            f(r+7,f'{c}{r+5}-{c}{r+6}')
            f(r+8,f'IF({c}2<={I(ir,"J")},{I(11)}*B{r}/{I(ir,"J")},0)')
            f(r+9,f'{c}{r+2}-{c}{r+3}')
        f(29,f'{prev}33');f(28,f'{prev}37')
        f(12,f'({total([r+9 for r in starts],c)})+({c}11+{I(24)})*{c}29+{I(25)}*MAX(0,{I(23)}-{c}29)')
        f(13,total([r+3 for r in starts],c));f(14,total([r+8 for r in starts],c))
        f(15,path('interest_income'));f(16,path('tax_adjustment'))
        f(17,f'IF({I(16)}=1,MAX({I(21)},{I(15)}*MAX(0,IF({I(17)}=1,{c}8,{c}6)+{c}16)+{c}15),1E99)')
        f(18,I(20) if y==1 else f'{prev}20');f(19,f'MIN({c}12+{c}13+{c}18,MAX(0,{c}17))')
        f(20,f'{c}12+{c}13+{c}18-{c}19');f(21,f'{c}8+{c}15+{c}16-{c}19-{c}14')
        f(22,I(19) if y==1 else f'{prev}24');f(23,f'MIN({c}22,MAX(0,{c}21)*{I(18)},{I(22)})')
        f(24,f'{c}22-{c}23+MAX(0,-{c}21)');f(25,f'MAX(0,{c}21-{c}23)*{I(14)}')
        f(26,f'{c}6+{c}15-{c}12-{c}25-{c}9-{c}10')
        f(41,f'IF({c}2>={I(27)},{c}29,0)');f(27,f'({total([r+4 for r in starts],c)})+{c}41')
        f(30,f'{c}28+{c}26-{c}27-{I(12)}')
        f(31,f'IF({c}2<{I(27)},MIN(MAX(0,-{c}30),MAX(0,{I(23)}-{c}29+{c}41)),0)')
        f(32,f'MIN({c}29-{c}41,MAX(0,{c}30))');f(33,f'{c}29-{c}41+{c}31-{c}32')
        f(34,f'{c}30+{c}31-{c}32');f(35,f'MAX(0,{c}34)*{I(28)}');f(36,total([r+6 for r in starts],c))
        f(37,f'{I(12)}+{c}34-{c}36');f(38,f'({total([r+7 for r in starts],c)})+{c}33')
        f(39,f'{c}38-{c}37');f(40,f'MAX(0,{I(12)}-{c}37)')
    ret['A1']='Live returns · opening-balance interest; blue inputs are editable'
    ret['A2']='Snapshot sheets retain the API method. This live model uses opening balances and recalculates without circular references.'
    ret_labels={3:'Entry EV',4:'Closing debt',5:'Transaction fees',6:'Financing fees',7:'Sponsor equity',8:'Exit EV',9:'Exit net debt',10:'Exit equity before MIP',11:'MIP',12:'Sponsor proceeds',13:'MOIC',14:'Sponsor IRR',15:'Opening-method API reference IRR',16:'Formula / reference difference'}
    for r,name in ret_labels.items():ret.cell(r,1,name)
    ret['B3']='='+I(7)+'*'+I(6)
    ret['B4']='='+('+'.join(M(r,'B') for r in starts) or '0')+'+'+I(26)
    ret['B5']='=B3*'+I(10)
    ret['B6']='=(B4-'+I(26)+')*'+I(11)
    ret['B7']='=B3+B5+B6+'+I(12)+'-B4-'+I(13)
    # SUMPRODUCT is unnecessary: a simple IF chain keeps exit-year changes editable.
    def exit_ref(row):
        return '+'.join(f'IF({I(9)}={y},{M(row,col(y+2))},0)' for y in range(1,n+1))
    ret['B8']='=('+exit_ref(6)+')*'+I(8)
    ret['B9']='='+exit_ref(39)
    ret['B10']='=B8*(1-'+I(29)+')-B9'
    ret['B11']='=MAX(0,B10-B7-'+I(13)+')*'+I(30)
    ret['B12']='=(B10-B11)*B7/(B7+'+I(13)+')'
    ret['B13']='=B12/B7'
    ret['B14']='=IF(B12>0,B13^(1/'+I(9)+')-1,-1)'
    ret['B15']=reference['returns']['sponsor_irr']
    ret['B16']='=B14-B15'
    for sheet in (ins,mod,ret):
        sheet.freeze_panes='C3';sheet.column_dimensions['A'].width=46
        for column in range(2, max(sheet.max_column, 4)+1):sheet.column_dimensions[col(column)].width=18
        for row in sheet:
            for cell in row:
                if isinstance(cell.value,(float,int)):cell.number_format='#,##0.00;(#,##0.00)'
                if sheet==ins and cell.column>1 and cell.value is not None and not (isinstance(cell.value,str) and cell.value.startswith('=')):
                    cell.font=Font(color='1767B0');cell.fill=PatternFill('solid',fgColor='EDF5FF')
    ret['B14'].number_format=ret['B15'].number_format=ret['B16'].number_format='0.00%'
    for r in (10,11,14,15,18,24,25,28,29,30): ins.cell(r,2).number_format='0.0%'
    for i in range(len(tranches)):
        for c in ('F','G','H','I'): ins[f'{c}{tranche_start+i}'].number_format='0.0%'
    for i,key in enumerate(path_keys):
        if key not in ('interest_income','tax_adjustment'):
            for y in range(n): ins.cell(path_start+i,y+3).number_format='0.0%'
    from openpyxl.worksheet.datavalidation import DataValidation
    horizon=DataValidation(type='whole',operator='between',formula1=1,formula2=n)
    horizon.errorTitle='Exit year outside exported model';horizon.error='Choose a year within the exported forecast.';horizon.showErrorMessage=True
    ins.add_data_validation(horizon);horizon.add(ins['B9'])
    binary=DataValidation(type='whole',operator='between',formula1=0,formula2=1)
    binary.showErrorMessage=True;ins.add_data_validation(binary)
    for r in (16,17,31):binary.add(ins.cell(r,2))
    wb.calculation=CalcProperties(calcId=191029,fullCalcOnLoad=True,forceFullCalc=True,calcMode='auto')
    return {'irr':'Live returns!B14','moic':'Live returns!B13','cash':f'Live model!{col(reference["exit_year"]+2)}37'}
