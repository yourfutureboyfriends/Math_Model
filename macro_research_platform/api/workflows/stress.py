"""Explicit sensitivity scenarios; unsupported holdings never receive a generic equity beta."""
import math


def european_price(spot,strike,vol,years,rate,dividend,side):
    if spot<=0 or strike<=0 or vol<=0 or years<=0:raise ValueError('Positive spot, strike, volatility and time are required')
    n=lambda x:.5*(1+math.erf(x/math.sqrt(2)))
    d1=(math.log(spot/strike)+(rate-dividend+.5*vol*vol)*years)/(vol*math.sqrt(years));d2=d1-vol*math.sqrt(years)
    if side=='call':return spot*math.exp(-dividend*years)*n(d1)-strike*math.exp(-rate*years)*n(d2)
    return strike*math.exp(-rate*years)*n(-d2)-spot*math.exp(-dividend*years)*n(-d1)


def evaluate(positions, shocks, cash, redemption=0., participation=.1, volume_multiplier=.5, loss_limit=None):
    def scenario(scale):
        rows=[];missing=[];gross=0.;covered=0.
        for p in positions:
            mv=p.get('market_value_base');kind=p.get('instrument_type');reason=None;change=None;option_pnl=None
            if mv is None:reason='Missing base-currency market value'
            else:
                gross+=abs(mv)
                if kind=='equity' and p.get('equity_beta') is not None:change=p['equity_beta']*shocks['equity']*scale
                elif kind=='bond' and p.get('duration') is not None:
                    dy=(shocks['rates']+shocks['credit_spread'])*scale
                    if p.get('convexity') is None:reason='Convexity missing; bond scenario withheld'
                    else:change=-p['duration']*dy+.5*p['convexity']*dy*dy
                elif kind=='option':
                    terms=p.get('option_terms')
                    if not terms:reason='European option terms missing; unsupported options receive no equity substitution'
                    elif terms['quantity']*mv<0:reason='Option quantity and market value have inconsistent signs'
                    else:
                        spot=terms['spot']*(1+terms['underlying_beta']*shocks['equity']*scale)
                        vol=terms['volatility']+shocks.get('volatility',0)*scale
                        if spot<=0 or vol<=0:reason='Option shock exceeds positive spot/volatility domain'
                        else:
                            args=(terms['strike'],terms['volatility'],terms['years'],terms['rate'],terms['dividend_yield'],terms['side'])
                            base=european_price(terms['spot'],*args)
                            stressed=european_price(spot,terms['strike'],vol,terms['years'],terms['rate']+shocks['rates']*scale,terms['dividend_yield'],terms['side'])
                            option_pnl=(stressed-base)*terms['quantity']*terms['multiplier']*terms['fx_to_base']
                            change=0.
                else:reason='Instrument type or sensitivity not supplied'
                if change is not None:
                    if p.get('fx_beta') is None:reason='FX exposure not supplied (use zero only for no exposure)'
                    elif 1+change<0:reason='Scenario exceeds nonnegative price domain of this approximation'
            if reason:
                missing.append({'symbol':p['symbol'],'reason':reason});continue
            change=(1+change)*(1+p['fx_beta']*shocks['fx']*scale)-1
            if 1+change<0:
                missing.append({'symbol':p['symbol'],'reason':'FX scenario exceeds positive conversion domain'});continue
            pnl=mv*change+(option_pnl or 0)*(1+p['fx_beta']*shocks['fx']*scale);covered+=abs(mv)
            adv=p.get('adv_base');days=abs(mv)/(adv*participation*volume_multiplier) if adv and adv>0 else None
            margin=abs(mv+pnl)*p['margin_rate'] if p.get('margin_rate') is not None else None
            rows.append({'symbol':p['symbol'],'instrument_type':kind,'market_value_base':mv,'pnl_base':pnl,
                         'stressed_value_base':mv+pnl,'indicative_liquidation_days':days,'indicative_margin_base':margin})
        complete=not missing;known=sum(r['pnl_base'] for r in rows)
        net=sum(p['market_value_base'] for p in positions if p.get('market_value_base') is not None)
        margins=all(r['indicative_margin_base'] is not None for r in rows) and complete
        margin=sum(r['indicative_margin_base'] for r in rows) if margins else None
        return {'positions':rows,'uncovered':missing,'coverage_complete':complete,'gross_value_base':gross,
                'covered_gross_fraction':covered/gross if gross else None,'unpriced_positions':sum(p.get('market_value_base') is None for p in positions),
                'known_pnl_base':known,'scenario_pnl_base':known if complete else None,
                'stressed_equity_base':cash+net+known if complete else None,
                'indicative_margin_base':margin,'cash_after_redemption_base':cash-redemption,
                'cash_gap_including_margin_base':max(0,redemption+(margin or 0)-cash) if margins else None}
    result=scenario(1.)
    reverse=None
    if loss_limit is not None:
        previous=(0.,scenario(0.));bracket=None
        for i in range(1,101):
            point=(i/100,scenario(i/100))
            if point[1]['scenario_pnl_base'] is None:break
            if -point[1]['scenario_pnl_base']>=loss_limit:
                bracket=(previous[0],point[0]);break
            previous=point
        if bracket:
            lo,hi=bracket
            for _ in range(35):
                mid=(lo+hi)/2;r=scenario(mid)
                if r['scenario_pnl_base'] is None:break
                if -r['scenario_pnl_base']>=loss_limit:hi=mid
                else:lo=mid
            reverse={'path_scale':hi,'shocks':{k:v*hi for k,v in shocks.items()},'loss_limit_base':loss_limit,
                     'basis':'First breach detected on 101 path samples, refined within that bracket; not a globally most probable shock'}
        else:reverse={'path_scale':None,'reason':'No supported breach detected within the supplied scenario path; uncovered holdings prevent a complete reverse stress'}
    return {**result,'reverse_stress':reverse,'shocks':shocks,
            'note':'Analyst-supplied sensitivities: equity beta, bond duration/convexity and multiplicative FX. European vanilla options with explicit terms use full Black–Scholes repricing at unchanged time-to-expiry, including volatility/rate shocks, anchored to the supplied current market value. This is a theoretical model; American/path-dependent contracts remain unsupported. Bond approximation can fail for large shocks, defaults or embedded options. Missing/unknown holdings are withheld. ADV liquidation days are capacity estimates, not executable quotes. Cash excludes assumed proceeds, short-sale collateral and broker-specific netting. No trade is created.'}
