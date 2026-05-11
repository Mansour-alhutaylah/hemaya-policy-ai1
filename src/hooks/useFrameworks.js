import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/apiClient';

// Single source of truth for the list of frameworks across pages.
// Shares queryKey ['frameworks'] with any other call sites so React Query
// dedupes.
export function useFrameworks(options = {}) {
  const { sort = 'name', limit = 100, ...rest } = options;
  return useQuery({
    queryKey: ['frameworks'],
    queryFn: () => api.entities.Framework.list(sort, limit),
    ...rest,
  });
}
