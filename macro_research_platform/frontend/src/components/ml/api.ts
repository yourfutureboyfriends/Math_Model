/** ML data layer on TanStack Query: cached per key, background refetch, polling while a task trains, retry with
 *  backoff while the server restarts. */
import { QueryClient, useQuery } from '@tanstack/react-query';

export const mlQueryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 4, retryDelay: (n) => Math.min(8000, 1000 * 2 ** n), refetchOnWindowFocus: false } },
});

async function get(url: string) {
  const r = await fetch(url);
  const j = await r.json().catch(() => null);
  if (!r.ok) throw new Error(j?.detail ? String(j.detail) : r.status === 404 ? 'The server does not have this endpoint yet — restart the backend' : `HTTP ${r.status}`);
  return j;
}

export function useTasksQ() {
  return useQuery({
    queryKey: ['ml', 'tasks'], queryFn: () => get('/api/v1/ml/tasks').then((j) => j.tasks as any[]),
    refetchInterval: (q) => ((q.state.data as any[] | undefined)?.some((t) => !t.ready) ? 10_000 : 120_000),
  });
}

export function useTaskQ(name: string) {
  return useQuery({
    queryKey: ['ml', 'task', name], queryFn: () => get(`/api/v1/ml/tasks/${name}`),
    refetchInterval: (q) => ((q.state.data as any)?.training ? 4_000 : false),
  });
}

export function useHistoryQ(name: string, enabled: boolean) {
  return useQuery({ queryKey: ['ml', 'history', name], queryFn: () => get(`/api/v1/ml/tasks/${name}/history`), enabled, retry: 2 });
}

/** The task's monthly input history (for replaying the network through time); loaded once per task. */
export function useInputsQ(name: string, enabled: boolean) {
  return useQuery({ queryKey: ['ml', 'inputs', name], queryFn: () => get(`/api/v1/ml/tasks/${name}/inputs`), enabled, staleTime: 6 * 3600_000, retry: 2 });
}

export const useRegistryQ = () => useQuery({ queryKey: ['ml', 'registry'], queryFn: () => get('/api/v1/ml/registry'), refetchInterval: 60_000 });
export const useFeaturesQ = () => useQuery({ queryKey: ['ml', 'features'], queryFn: () => get('/api/v1/ml/features'), staleTime: 10 * 60_000 });
export const useKnowledgeQ = () => useQuery({ queryKey: ['ml', 'knowledge'], queryFn: () => get('/api/v1/ml/knowledge') });

export async function send(url: string, method: 'POST' | 'DELETE') {
  const r = await fetch(url, { method });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j?.detail ?? `HTTP ${r.status}`);
  await mlQueryClient.invalidateQueries({ queryKey: ['ml'] });
  return j;
}


export function useVisualizerQ(name:string) {
 return useQuery({queryKey:['ml','visualizer',name],queryFn:()=>get(`/api/v1/ml/tasks/${name}/visualizer`),refetchInterval:q=>(q.state.data as any)?.training?2000:60000});
}
export const useDeepStatusQ=()=>useQuery({queryKey:['ml','deep-status'],queryFn:()=>get('/api/v1/ml/deep/status'),refetchInterval:10000});

export function useLiveStateQ(){return useQuery({queryKey:['ml','live-state'],queryFn:()=>get('/api/v1/ml/deep/live'),refetchInterval:2000});}
export async function refreshLiveState(){
 const response=await fetch('/api/v1/ml/deep/live/refresh',{method:'POST'});
 if(!response.ok)throw new Error('Could not refresh measured network state');
 return response.json();
}

export const useOnlineStatusQ=()=>useQuery({queryKey:['ml','online-status'],queryFn:()=>get('/api/v1/ml/online/status'),refetchInterval:30000});

export const useResearchGraphQ=()=>useQuery({queryKey:['ml','research-graph'],queryFn:()=>get('/api/v1/ml/research/graph'),refetchInterval:30000});

/** `live` stops the poll while the pushed stream is delivering this panel's frames. */
export const useAutonomousStatusQ=(live=false)=>useQuery({queryKey:['ml','autonomous-status'],queryFn:()=>get('/api/v1/ml/autonomous/status'),refetchInterval:live?false:5000});
