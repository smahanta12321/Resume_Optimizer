import { isRouteErrorResponse, Link, useRouteError } from "react-router";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/surface";

/** Last-resort boundary for render errors and failed chunk loads. */
export function RouteError() {
  const error = useRouteError();
  const message = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : "Unknown error";
  return (
    <div className="mx-auto max-w-xl space-y-4 px-4 py-16">
      <Alert tone="danger" title="This screen hit an unexpected error">
        <p>{message}</p>
        <p>Your saved data is not affected. Reload the page or go back to the dashboard.</p>
      </Alert>
      <div className="flex gap-2">
        <Button onClick={() => window.location.reload()}>Reload</Button>
        <Button variant="secondary" asChild>
          <Link to="/">Dashboard</Link>
        </Button>
      </div>
    </div>
  );
}
