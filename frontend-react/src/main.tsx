import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";
import { createRouter } from "@/app/router";
import { Providers } from "@/app/providers";
import { ConnectionGate } from "@/layouts/ConnectionGate";
import { captureTokenFromUrl } from "@/lib/session";
import "@/styles/index.css";

captureTokenFromUrl();
const router = createRouter();

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <Providers>
      <ConnectionGate>
        <RouterProvider router={router} />
      </ConnectionGate>
    </Providers>
  </StrictMode>,
);
