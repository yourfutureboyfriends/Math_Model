import { expect, it } from 'vitest';
import { earningsInsights } from './earningsInsights';
it('keeps revision direction meaningful for loss estimates', () => {
 const [r] = earningsInsights({eps:[{period:'0q',avg:-2,low:-3,high:-1,numberOfAnalysts:3}],eps_trend:[{period:'0q',current:-1,'30daysAgo':-2}],eps_revisions:[{period:'0q',upLast30days:3,downLast30days:1}]});
 expect(r.change).toBe(50);expect(r.breadth).toBe(50);expect(r.dispersion).toBe(100);
});
it('handles missing data and zero denominators', () => {
 const [r] = earningsInsights({eps:[{period:'0q',avg:0}],eps_trend:[{period:'0q',current:1,'30daysAgo':0}]});
 expect(r.change).toBeNull();expect(r.breadth).toBeNull();expect(r.dispersion).toBeNull();expect(earningsInsights(null)).toEqual([]);
});
