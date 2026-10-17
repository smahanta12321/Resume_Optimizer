import { SearchX } from "lucide-react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/shared/states";

export function NotFound() {
  return (
    <EmptyState
      icon={SearchX}
      title="Page not found"
      action={
        <Button asChild variant="secondary">
          <Link to="/">Go to the dashboard</Link>
        </Button>
      }
    >
      This address doesn't match any screen.
    </EmptyState>
  );
}
