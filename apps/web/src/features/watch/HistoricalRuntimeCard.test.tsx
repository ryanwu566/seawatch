import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  getHistoricalRuntimeSummary,
  type HistoricalRuntimeSummary,
} from "../../api/historicalRuntime";
import {
  formatHistoricalCount,
  HistoricalRuntimeCard,
} from "./HistoricalRuntimeCard";


vi.mock("../../api/historicalRuntime", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/historicalRuntime")>();
  return {
    ...actual,
    getHistoricalRuntimeSummary: vi.fn(),
  };
});


const availableSummary = {
  available: true,
  runtime: "SeaWatch_Runtime_Taiwan_2026_v2",
  data_model: "standardized_hourly_vessel_presence",
  date_range: {
    startUtc: "2026-01-01T00:00:00+00:00",
    endUtc: "2026-09-29T23:00:00+00:00",
  },
  row_count: 33_200_000,
  unique_vessel_count: 400_800,
  traffic_cell_count: 2457,
  dataset_hour_buckets: 6528,
  mmsi_join_status_counts: {
    unique_9digit_candidate: 66_043,
    shared_9digit: 12,
  },
  local_path: "D:/private/runtime",
  raw_mmsi: "123456789",
  vesselId: "gfw-vessel-sensitive-001",
  credential: "super-secret-token",
} as HistoricalRuntimeSummary;


describe("HistoricalRuntimeCard", () => {
  beforeEach(() => {
    vi.mocked(getHistoricalRuntimeSummary).mockReset();
  });

  it("renders a calm loading state while the one mount request is pending", () => {
    vi.mocked(getHistoricalRuntimeSummary).mockReturnValue(new Promise(() => {}));

    render(<HistoricalRuntimeCard />);

    expect(screen.getByText("Loading historical context")).toBeInTheDocument();
    expect(getHistoricalRuntimeSummary).toHaveBeenCalledTimes(1);
    expect(getHistoricalRuntimeSummary).toHaveBeenCalledWith(expect.any(AbortSignal));
  });

  it("renders the aggregate hourly-presence contract and compact counts", async () => {
    vi.mocked(getHistoricalRuntimeSummary).mockResolvedValue(availableSummary);

    const { container } = render(<HistoricalRuntimeCard />);

    expect(await screen.findByText("Historical context available")).toBeInTheDocument();
    expect(screen.getByText("Jan 1–Sep 29, 2026 coverage")).toBeInTheDocument();
    expect(screen.getByText("33.2M")).toBeInTheDocument();
    expect(screen.getByText("400.8K")).toBeInTheDocument();
    expect(screen.getByText("2,457")).toBeInTheDocument();
    expect(screen.getByText("6,528")).toBeInTheDocument();
    expect(screen.getByText("66,043")).toBeInTheDocument();
    expect(screen.getByText("historical presence observations")).toBeInTheDocument();
    expect(
      screen.getByText("GFW standardized hourly vessel presence"),
    ).toBeInTheDocument();
    expect(screen.getByText("Not raw/message-level AIS")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Only dataset-internal one-to-one nine-digit MMSI candidates are eligible for conservative cross-source matching.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("66,043").closest("div")).toHaveAttribute(
      "title",
      "Conservative cross-source join candidates",
    );

    const visible = container.textContent ?? "";
    expect(visible).not.toContain("D:/private/runtime");
    expect(visible).not.toContain("123456789");
    expect(visible).not.toContain("gfw-vessel-sensitive-001");
    expect(visible).not.toContain("super-secret-token");
  });

  it("renders the neutral unavailable state from an unavailable payload", async () => {
    vi.mocked(getHistoricalRuntimeSummary).mockResolvedValue({
      available: false,
      reason: "Historical context unavailable",
    });

    render(<HistoricalRuntimeCard />);

    expect(await screen.findByText("Historical context unavailable")).toBeInTheDocument();
    expect(screen.queryByText("33.2M")).not.toBeInTheDocument();
  });

  it("contains request failures without displaying exception details", async () => {
    vi.mocked(getHistoricalRuntimeSummary).mockRejectedValue(
      new Error("D:/private/runtime super-secret-token"),
    );

    const { container } = render(<HistoricalRuntimeCard />);

    expect(await screen.findByText("Historical context unavailable")).toBeInTheDocument();
    expect(container).not.toHaveTextContent("D:/private/runtime");
    expect(container).not.toHaveTextContent("super-secret-token");
  });

  it("does not refetch across ordinary parent rerenders", async () => {
    vi.mocked(getHistoricalRuntimeSummary).mockResolvedValue(availableSummary);

    function Parent({ tick }: { tick: number }) {
      return (
        <div data-tick={tick}>
          <HistoricalRuntimeCard />
        </div>
      );
    }

    const { rerender } = render(<Parent tick={1} />);
    expect(await screen.findByText("Historical context available")).toBeInTheDocument();

    rerender(<Parent tick={2} />);
    rerender(<Parent tick={3} />);

    await waitFor(() => expect(getHistoricalRuntimeSummary).toHaveBeenCalledTimes(1));
  });

  it("keeps incomplete safe aggregate responses renderable", async () => {
    vi.mocked(getHistoricalRuntimeSummary).mockResolvedValue({ available: true });

    render(<HistoricalRuntimeCard />);

    expect(await screen.findByText("Historical context available")).toBeInTheDocument();
    expect(screen.getByText("Coverage unavailable")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });
});


describe("formatHistoricalCount", () => {
  it("formats compact headline and locale-grouped context counts", () => {
    expect(formatHistoricalCount(33_200_000, "compact")).toBe("33.2M");
    expect(formatHistoricalCount(400_800, "compact")).toBe("400.8K");
    expect(formatHistoricalCount(2457, "grouped")).toBe("2,457");
    expect(formatHistoricalCount(null, "grouped")).toBe("—");
  });
});
