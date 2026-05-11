import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/apiClient';

// Single source of truth for the list of policies across pages.
// QueryKey ['policies'] is shared with existing call sites so React Query
// dedupes the request — no duplicate network calls when multiple pages
// mount.
export function usePolicies(options = {}) {
  const { sort = '-created_at', limit = 100, ...rest } = options;
  return useQuery({
    queryKey: ['policies'],
    queryFn: () => api.entities.Policy.list(sort, limit),
    ...rest,
  });
}
