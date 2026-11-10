import { expect, it } from 'vitest';
import { AREAS, navigation, navigationFor } from './navigation';
it('keeps dashboard destinations unique and assigns each panel to one workspace', () => {
 const registered = navigation.flatMap(group => group.items.map(item => item.id));
 expect(new Set(registered).size).toBe(registered.length);
 const assigned = AREAS.flatMap(area => area.groups.flatMap(group => group.ids));
 expect(new Set(assigned).size).toBe(assigned.length);
 for (const id of assigned) expect(registered).toContain(id);
 for (const area of AREAS) expect(navigationFor(area.id).flatMap(group => group.items)).toHaveLength(area.groups.flatMap(group => group.ids).length);
});
