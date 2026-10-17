import { useQuery } from "@tanstack/react-query";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/api/client";
import { renderPage } from "@/test/utils";
import { checkFile, FileDrop } from "./FileDrop";
import { QueryView } from "./states";

const rules = { extensions: [".pdf", ".docx"], maxBytes: 1000 };

describe("checkFile", () => {
  it("accepts allowed types within the size limit", () => {
    expect(checkFile(new File(["x"], "CV.PDF"), rules)).toBeNull();
  });
  it("rejects wrong types, empty files and oversized files", () => {
    expect(checkFile(new File(["x"], "cv.exe"), rules)).toMatch(/Unsupported file type/);
    expect(checkFile(new File([], "cv.pdf"), rules)).toMatch(/empty/);
    expect(checkFile(new File(["x".repeat(1001)], "cv.pdf"), rules)).toMatch(/too large/);
  });
});

describe("FileDrop", () => {
  it("passes valid files on and reports invalid ones", async () => {
    const onFile = vi.fn();
    render(<FileDrop rules={rules} label="Upload" onFile={onFile} />);
    const input = document.querySelector("input[type=file]") as HTMLInputElement;
    await userEvent.upload(input, new File(["x"], "notes.txt"), { applyAccept: false });
    expect(screen.getByRole("alert")).toHaveTextContent(/Unsupported file type/);
    expect(onFile).not.toHaveBeenCalled();
    await userEvent.upload(input, new File(["x"], "cv.docx"));
    expect(onFile).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

function Probe({ fn }: { fn: () => Promise<string> }) {
  const q = useQuery({ queryKey: ["probe"], queryFn: fn });
  return <QueryView query={q}>{(data) => <p>data: {data}</p>}</QueryView>;
}

describe("QueryView", () => {
  it("shows loading, then data", async () => {
    let resolve: (v: string) => void = () => undefined;
    renderPage(<Probe fn={() => new Promise((r) => (resolve = r))} />);
    expect(await screen.findByLabelText("Loading")).toBeInTheDocument();
    resolve("ready");
    expect(await screen.findByText("data: ready")).toBeInTheDocument();
  });

  it("shows the API's error message with a retry", async () => {
    let fail = true;
    renderPage(
      <Probe
        fn={async () => {
          if (fail) throw new ApiError(503, "store_unavailable", "Job database could not be opened.");
          return "recovered";
        }}
      />,
    );
    expect(await screen.findByText("Job database could not be opened.")).toBeInTheDocument();
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: /retry/i }));
    await waitFor(() => expect(screen.getByText("data: recovered")).toBeInTheDocument());
  });

  it("explains network failures as the local app not running", async () => {
    renderPage(<Probe fn={async () => Promise.reject(new ApiError(0, "network_error", "Can't reach the local app."))} />);
    expect(await screen.findByText("Can't reach the local app")).toBeInTheDocument();
  });
});
