import { it,expect } from 'vitest';import { parseMarketsHash } from './marketsRoute';
it('recovers malformed escaped security bookmarks and keeps valid international symbols',()=>{
 expect(parseMarketsHash('#mkt/des/%E0%A4%A')).toEqual({fn:'WEI'});expect(parseMarketsHash('#mkt/gp/7203.T')).toEqual({fn:'GP',symbol:'7203.T'});expect(parseMarketsHash('#mkt/gp/%5EGSPC')).toEqual({fn:'GP',symbol:'^GSPC'});
});
