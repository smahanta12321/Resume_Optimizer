import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Toaster } from "sonner";
import { clearToken } from "@/lib/session";
import { isApiError } from "@/services/api/client";
import { SESSION_KEY } from "@/services/api/queries";

export function createQueryClient(): QueryClient {
  // A token rejected mid-session means the API restarted with a new token: drop it so the
  // ConnectionGate re-checks and asks to reconnect. The session check itself is excluded, or a
  // rejected token would reset it, fail again, and loop.
  const onError = (error: unknown, isSessionCheck = false) => {
    if (!isSessionCheck && isApiError(error, "session_token_invalid")) {
      clearToken();
      void client.resetQueries({ queryKey: SESSION_KEY });
    }
  };
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError: (error, query) => onError(error, query.queryKey[0] === SESSION_KEY[0]) }),
    mutationCache: new MutationCache({ onError: (error) => onError(error) }),
    defaultOptions: {
      queries: {
        staleTime: 10_000,
        // Refetch on focus picks up edits made in the Streamlit app meanwhile.
        refetchOnWindowFocus: true,
        retry: (count, error) => !(isApiError(error) && error.status >= 400 && error.status < 500) && count < 2,
      },
      mutations: { retry: false },
    },
  });
  return client;
}

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(createQueryClient);
  return (
    <QueryClientProvider client={client}>
      {children}
      <Toaster position="bottom-right" richColors closeButton toastOptions={{ duration: 5000 }} />
    </QueryClientProvider>
  );
}
