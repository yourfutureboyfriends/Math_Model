"""Underwriting controls and independent evaluation of the editable Excel cash waterfall."""
import copy
import re
from functools import lru_cache
import pytest
from openpyxl import Workbook
from api.pe import lbo, underwriting, live_excel
from api.tests.test_pe import simple
from api.tests.test_dcf_excel import _ifs


def evaluate(wb, ref):
    @lru_cache(None)
    def cell(sheet, address):
        v = wb[sheet][address].value
        if not isinstance(v, str) or not v.startswith('='):
            return v if v is not None else 0
        refs = []
        def replace(m):
            refs.append(cell(m.group(1) or sheet, m.group(2).replace('$','')))
            return f'__v({len(refs)-1})'
        f = re.sub(r"(?<![A-Za-z0-9_])(?:'([^']+)'!)?(\$?[A-Z]+\$?\d+)", replace, v[1:])
        f = re.sub(r'(?<![<>=!])=(?!=)', '==', f)
        f = _ifs(f).replace('MAX(', 'max(').replace('MIN(', 'min(').replace('^','**')
        return eval(f, {'__builtins__':{},'min':min,'max':max,'__v':lambda i:refs[i]})
    sheet, address = ref.split('!')
    return cell(sheet,address)


@pytest.mark.parametrize('patch', [
    {}, {'interest_on':'average'}, {'interest_cap_basis':'ebit','dna_pct':.1},
    {'opening_nol':100,'nol_utilization_pct':.8,'opening_disallowed_interest':5},
    {'revolver':{'commitment':50,'drawn_at_close':10,'spread':.03,'commitment_fee':.003,'tenor':3}},
    {'ebitda_adjustments':[{'label':'Legal cost','source':'QoE p12','amount':3,'approved':True}], 'apply_adjustments_to_plan':True},
    {'tranches':[{'name':'Mezz','kind':'mezz','multiple':1,'coupon':.12,'floating':False,'pik':True,'tenor':3}]},
    {'tranches':[{'name':'Loan','kind':'tlb','multiple':2,'spread':.03,'floor':.02,'floating':True,'amort_pct':.1,'tenor':4,'sweep':True}], 'base_rate_path':[.01,.03,.04,.05,.06]},
])
def test_editable_excel_matches_opening_engine_and_each_cashflow(patch):
    inp = simple(**patch)
    wb=Workbook();refs=live_excel.append(wb,inp)
    expected=lbo.run({**inp,'interest_on':'opening'})
    assert evaluate(wb,refs['irr'])==pytest.approx(expected['returns']['sponsor_irr'],abs=1e-8)
    assert evaluate(wb,refs['moic'])==pytest.approx(expected['returns']['moic'],abs=1e-8)
    for row in expected['schedule']:
        from openpyxl.utils import get_column_letter
        c=get_column_letter(row['year']+2)
        for r,key in [(26,'fcf'),(25,'tax'),(37,'cash'),(38,'debt'),(27,'mandatory'),(20,'interest_disallowed_cf'),(24,'nol_balance')]:
            assert evaluate(wb,f'Live model!{c}{r}')==pytest.approx(row[key],abs=1e-8)
    before=evaluate(wb,refs['irr']);wb['Live inputs']['B8']=inp.get('exit_multiple',5)*1.2
    assert evaluate(wb,refs['irr'])>before


def test_accepted_adjustments_require_evidence_and_are_not_double_applied():
    inp=simple(ebitda_adjustments=[{'label':'Legal','amount':3,'approved':True,'source':'QoE'}])
    r=lbo.run(inp)
    assert r['entry']['ebitda']==23
    assert r['schedule'][0]['ebitda']==20  # plan is independently underwritten
    assert lbo.run({**inp,'apply_adjustments_to_plan':True})['schedule'][0]['ebitda']==pytest.approx(23)
    assert inp['ebitda']==20
    bad=copy.deepcopy(inp);bad['ebitda_adjustments'][0]['source']=''
    with pytest.raises(lbo.LboError):lbo.run(bad)


def test_loss_utilization_and_interest_cap_basis():
    r=lbo.run(simple(tax_rate=.25,opening_nol=100,nol_utilization_pct=.8))
    assert r['schedule'][0]['nol_used']==pytest.approx(11.2)
    assert r['schedule'][0]['tax']==pytest.approx(.7)
    r=lbo.run(simple(dna_pct=.1,interest_cap_pct=.3,interest_cap_basis='ebit'))
    assert r['schedule'][0]['interest_deductible']==pytest.approx(3)


def test_quarterly_timing_reveals_gap_hidden_by_annual_netting():
    p=simple(ebitda_margin=.8,tranches=[{**simple()['tranches'][0],'tenor':1}],quarterly_cash_weights=[0,0,0,1],quarterly_debt_weights=[1,0,0,0])
    r=lbo.run(p)
    assert r['calculation_checks']['funded_through_exit']
    q=underwriting.liquidity(p,r)
    assert q['first_shortfall']=='Y1 Q1'
    assert q['maximum_reserve_shortfall']==60
    for y in r['schedule']:
        rows=[x for x in q['quarters'] if x['year']==y['year']]
        assert sum(x['fcf'] for x in rows)==pytest.approx(y['fcf'])


@pytest.mark.parametrize('patch', [{'tax_rate':float('nan')},{'years':2.5},{'revenue_growth':-1.1},{'capex_pct':-.1}])
def test_invalid_assumptions_fail_explicitly(patch):
    with pytest.raises(lbo.LboError):lbo.run(simple(**patch))
