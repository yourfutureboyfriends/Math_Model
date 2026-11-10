"""Explicit strategic return building blocks, not next-month trading forecasts."""
def assumptions(data):
    years=data['horizon_years'];fx=data['annual_fx_return'] if not data['hedged'] else -data['annual_hedging_cost']
    components={}
    if data['asset_type']=='equity':
        for k in ('dividend_yield','eps_growth','starting_pe','ending_pe'):
            if data.get(k) is None:raise ValueError(f'Equity assumptions require {k}')
        valuation=(data['ending_pe']/data['starting_pe'])**(1/years)-1
        components={'dividend_reinvestment':data['dividend_yield'],'per_share_earnings_growth':data['eps_growth'],'annualized_valuation_change':valuation}
        local=(1+data['dividend_yield'])*(1+data['eps_growth'])*(1+valuation)-1
        components['compounding_interaction']=local-sum(components.values())
    else:
        for k in ('yield_carry','roll_return','annual_yield_change','duration','convexity','annual_credit_loss'):
            if data.get(k) is None:raise ValueError(f'Bond assumptions require {k}')
        dy=data['annual_yield_change']
        components={'yield_carry':data['yield_carry'],'roll_return':data['roll_return'],
                    'duration_effect':-data['duration']*dy,'convexity_effect':.5*data['convexity']*dy*dy,'credit_loss':-data['annual_credit_loss']}
        local=sum(components.values())
    local-=data['annual_fee'];components['fees']=-data['annual_fee']
    if local<=-1 or fx<=-1:raise ValueError('Assumptions exceed positive wealth/conversion domain')
    nominal=(1+local)*(1+fx)-1
    return {'asset_type':data['asset_type'],'horizon_years':years,'base_currency':data['base_currency'],
            'annual_local_return':local,'annual_base_nominal_return':nominal,'annual_base_real_return':(1+nominal)/(1+data['inflation'])-1,
            'components':components,'fx_or_hedging_return':fx,'fx_interaction':local*fx,
            'note':'Analyst-supplied strategic assumptions, not a next-month signal or copied institutional forecast. Equity assumes constant dividend yield/reinvestment and per-share EPS growth (no separate buyback yield). Bond carry/roll/duration/convexity is an annual local approximation, not a full multi-year term-structure repricing model. All rates are decimals; FX/hedging and inflation bases must match the declared fund currency.'}
