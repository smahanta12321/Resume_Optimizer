import { useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, PlugZap, RefreshCw } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form-controls";
import { Alert, Card, CardBody, Kbd } from "@/components/ui/surface";
import { LoadingRows } from "@/components/shared/states";
import { setToken } from "@/lib/session";
import { API_ORIGIN, errorMessage, isApiError } from "@/services/api/client";
import { api } from "@/services/api/endpoints";
import { SESSION_KEY } from "@/services/api/queries";



function Shell({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <div className="grid min-h-dvh place-items-center bg-background px-4 py-10">
      <Card className="w-full max-w-lg">
        <CardBody className="space-y-5 p-6">
          <div className="flex items-center gap-3">
            <div className="rounded-full bg-primary-soft p-2.5 text-primary">{icon}</div>
            <h1 className="text-lg font-semibold">{title}</h1>
          </div>
          {children}
        </CardBody>
      </Card>
    </div>
  );
}

/**
 * Shows the app only when the local API is reachable and this tab holds a valid session token.
 * Otherwise explains how to start the API or connect, instead of rendering screens that would fail.
 */
export function ConnectionGate({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const health = useQuery({ queryKey: ["health"], queryFn: ({ signal }) => api.health(signal), retry: false });
  const session = useQuery({
    queryKey: SESSION_KEY,
    queryFn: ({ signal }) => api.session(signal),
    enabled: health.isSuccess,
    retry: false,
    staleTime: Infinity,
  });
  const [tokenInput, setTokenInput] = useState("");

  if (health.isPending || (health.isSuccess && session.isPending)) {
    return (
      <div className="mx-auto max-w-lg px-4 py-16">
        <LoadingRows rows={2} />
      </div>
    );
  }

  if (health.isError) {
    return (
      <Shell icon={<PlugZap className="size-5" />} title="Start the local app">
        <p className="text-sm text-muted-foreground">
          This interface talks to the Resume Optimizer running on your computer at <Kbd>{API_ORIGIN}</Kbd>, and it isn't
          answering. In the project folder, with the virtual environment active, run:
        </p>
        <pre className="overflow-x-auto rounded-md border bg-surface-muted px-3 py-2 text-sm">python -m src.api</pre>
        <p className="text-sm text-muted-foreground">
          Then open the link it prints. The Streamlit app (<Kbd>streamlit run app.py</Kbd>) keeps working separately and
          uses the same data.
        </p>
        {!isApiError(health.error, "network_error") && <Alert tone="danger">{errorMessage(health.error)}</Alert>}
        <Button variant="secondary" onClick={() => void health.refetch()} loading={health.isFetching}>
          <RefreshCw /> Try again
        </Button>
      </Shell>
    );
  }

  if (session.isError) {
    const submit = (e: FormEvent) => {
      e.preventDefault();
      if (!tokenInput.trim()) return;
      setToken(tokenInput);
      setTokenInput("");
      void qc.resetQueries({ queryKey: SESSION_KEY });
    };
    const wrongToken = isApiError(session.error, "session_token_invalid");
    return (
      <Shell icon={<KeyRound className="size-5" />} title="Connect this tab">
        <p className="text-sm text-muted-foreground">
          The local app is running, but this tab isn't connected yet. Open the link that <Kbd>python -m src.api</Kbd> printed
          in its terminal, or paste the token from that link below. The token changes each time the app restarts.
        </p>
        {!wrongToken && <Alert tone="danger">{errorMessage(session.error)}</Alert>}
        <form onSubmit={submit} className="space-y-3">
          <Field label="Session token">
            {(p) => (
              <Input {...p} value={tokenInput} onChange={(e) => setTokenInput(e.target.value)} autoComplete="off" spellCheck={false} />
            )}
          </Field>
          <Button type="submit" disabled={!tokenInput.trim()}>
            Connect
          </Button>
        </form>
      </Shell>
    );
  }

  return <>{children}</>;
}
