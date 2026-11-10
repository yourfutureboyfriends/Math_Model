"""Developed-market coverage and valuation context, without fitting to share prices.

FTSE coverage snapshot: 6 October 2026, including Greece's September 2026 change.
Belgium/Luxembourg are reported separately here for company domicile. This is a
valuation coverage registry, not a claim that index providers classify identically.
"""
COUNTRIES={
 'Australia':('AUD','Asia Pacific'),'Austria':('EUR','Europe'),'Belgium':('EUR','Europe'),'Luxembourg':('EUR','Europe'),
 'Canada':('CAD','Americas'),'Denmark':('DKK','Europe'),'Finland':('EUR','Europe'),'France':('EUR','Europe'),
 'Germany':('EUR','Europe'),'Greece':('EUR','Europe'),'Hong Kong':('HKD','Asia Pacific'),'Ireland':('EUR','Europe'),
 'Israel':('ILS','Middle East'),'Italy':('EUR','Europe'),'Japan':('JPY','Asia Pacific'),'Netherlands':('EUR','Europe'),
 'New Zealand':('NZD','Asia Pacific'),'Norway':('NOK','Europe'),'Poland':('PLN','Europe'),'Portugal':('EUR','Europe'),
 'Singapore':('SGD','Asia Pacific'),'South Korea':('KRW','Asia Pacific'),'Spain':('EUR','Europe'),'Sweden':('SEK','Europe'),
 'Switzerland':('CHF','Europe'),'United Kingdom':('GBP','Europe'),'United States':('USD','Americas')}
ALIASES={'us':'United States','usa':'United States','uk':'United Kingdom','korea':'South Korea','republic of korea':'South Korea','korea, republic of':'South Korea','hong kong sar':'Hong Kong'}
SOURCE='https://www.lseg.com/content/dam/ftse-russell/en_us/documents/country-classification/matrix-of-markets.pdf'


def canonical_country(country):
    name=str(country or '').strip()
    return ALIASES.get(name.lower(),next((c for c in COUNTRIES if c.lower()==name.lower()),name))


def context(inp):
    from api.marketdata.dcf import LR_NOMINAL_GROWTH,RF_SERIES
    country=canonical_country(inp.get('country'));profile=COUNTRIES.get(country)
    currency=inp.get('currency');notes=[]
    if currency!=inp.get('price_currency'):notes.append('Financial-statement and quote currencies differ: verify FX, minor units, diluted shares and ADR conversion.')
    if currency=='EUR':notes.append('Use a common euro risk-free curve; issuer-country sovereign and operating risk belong in country exposure, not an added second government-yield spread.')
    if currency in ('JPY','CHF'):notes.append('Low local nominal yields and growth require consistent nominal cash flows. The disclosed equity floor is a model assumption; inspect its valuation effect.')
    if country in ('Japan','South Korea'):notes.append('Review treasury shares, cross-holdings, minority interests and ownership rights individually; no blanket governance haircut is inferred.')
    if country in ('Australia','Canada','Norway'):notes.append('Resource exposure is sector-specific: use through-cycle margins, maintenance investment and finite reserve-life checks where relevant.')
    if country in ('Hong Kong','Singapore'):notes.append('Listing market and operating-country exposure can differ substantially; use operating-country weights where documented.')
    if country in ('Ireland','Luxembourg','Switzerland'):notes.append('International profit mix and tax regimes can differ from the domicile reference; verify the sustainable group tax rate and minimum-tax applicability.')
    if not inp.get('country_risk_available',True):notes.append('Country-risk reference is unavailable; a zero input must not be interpreted as verified zero risk.')
    return {'country':country,'covered_developed_market':profile is not None,'registry_currency':profile[0] if profile else None,
        'region':profile[1] if profile else None,'cashflow_currency':currency,'risk_free_source':inp.get('risk_free_source'),
        'risk_free_basis':inp.get('risk_free_basis'),'country_risk_source':inp.get('country_risk_source'),
        'country_risk_premium':inp.get('country_risk_premium'),'governance_risk_premium':inp.get('governance_risk_premium',0.),
        'marginal_tax':inp.get('tax_marginal'),'tax_source':inp.get('tax_marginal_source'),'tax_reference':inp.get('tax_reference'),
        'terminal_growth_ceiling':LR_NOMINAL_GROWTH.get(currency),'local_rate_series':RF_SERIES.get(currency),'notes':notes,
        'classification_source':SOURCE,'classification_as_of':'2026-10-06',
        'method':'Risk follows the cash-flow currency, operating exposure, industry economics and equity rights. No fixed WACC or valuation discount is assigned merely because a market is developed.'}


def catalogue():
    return {'as_of':'2026-10-06','source':SOURCE,'markets':[{'country':name,'currency':v[0],'region':v[1]} for name,v in COUNTRIES.items()],
        'note':'FTSE-developed coverage snapshot; MSCI classifications can differ. Coverage does not certify current data availability or accuracy for every listed company.'}
