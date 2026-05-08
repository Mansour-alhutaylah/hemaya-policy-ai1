import { QueryClient } from '@tanstack/react-query';


export const queryClientInstance = new QueryClient({
	defaultOptions: {
		queries: {
			// Data fetched within the last 60 s is considered fresh — no background
			// refetch on route change. Explicit invalidateQueries() still fires immediately.
			staleTime: 60_000,
			// Keep unused query results in memory for 5 min before garbage-collecting.
			gcTime: 5 * 60_000,
			refetchOnWindowFocus: false,
			retry: 1,
		},
	},
});