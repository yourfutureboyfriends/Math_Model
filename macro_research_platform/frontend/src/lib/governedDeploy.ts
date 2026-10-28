// A fund with governance on paper-trades only governed models (approved at G2): the deployment becomes the model's
// G3 shadow-trading record. Returns {} when the fund has no governance, {model_id} when chosen, null if cancelled.
import type { AskOptions } from '@/components/ui/ConfirmDialog';

export async function modelForDeploy(ask: (o: AskOptions) => Promise<any>): Promise<{ model_id?: number } | null> {
  const g = await fetch('/api/v1/governance').then((r) => (r.ok ? r.json() : null)).catch(() => null);
  if (!g?.settings?.enabled) return {};
  const ms = await fetch('/api/v1/governance/models').then((r) => (r.ok ? r.json() : { models: [] })).catch(() => ({ models: [] }));
  const ok = (ms.models ?? []).filter((m: any) => m.status === 'active' && ['G2', 'G3', 'G4', 'G5'].includes(m.gate));
  if (!ok.length) {
    throw new Error(`${g.settings.fund_name} paper-trades only governed models, and none has an approved backtest (G2) yet — see Fund Governance → Models.`);
  }
  const raw = await ask({
    title: 'Which governed model does this deployment shadow-trade?',
    body: ok.map((m: any) => `#${m.id} ${m.name} (${m.gate})`).join('\n') + '\n\nIts paper record becomes the model’s G3 evidence.',
    confirmLabel: 'Deploy for this model', input: { label: 'Model id', defaultValue: String(ok[0].id), type: 'number' },
  });
  if (!raw) return null;
  return { model_id: Number(raw) };
}
