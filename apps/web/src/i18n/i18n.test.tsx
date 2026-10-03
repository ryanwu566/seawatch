import { describe, expect, it, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { I18nProvider, useI18n } from "./I18nContext";
import { DEFAULT_LANG, DICTIONARIES } from "./dictionaries";

function Probe() {
  const { t, lang, toggleLang } = useI18n();
  return (
    <div>
      <span data-testid="lang">{lang}</span>
      <span data-testid="vessels-now">{t.vesselsNow}</span>
      <span data-testid="review">{t.reviewPriority}</span>
      <button onClick={toggleLang}>toggle</button>
    </div>
  );
}

describe("i18n", () => {
  beforeEach(() => {
    window.localStorage?.clear();
  });

  it("defaults to English", () => {
    expect(DEFAULT_LANG).toBe("en");
    render(
      <I18nProvider>
        <Probe />
      </I18nProvider>,
    );
    expect(screen.getByTestId("lang").textContent).toBe("en");
    expect(screen.getByTestId("vessels-now").textContent).toBe("Vessels Now");
    expect(screen.getByTestId("review").textContent).toBe("Review Priority");
  });

  it("toggles to Traditional Chinese instantly without reload", () => {
    render(
      <I18nProvider>
        <Probe />
      </I18nProvider>,
    );
    fireEvent.click(screen.getByText("toggle"));
    expect(screen.getByTestId("lang").textContent).toBe("zh-Hant");
    expect(screen.getByTestId("vessels-now").textContent).toBe(
      DICTIONARIES["zh-Hant"].vesselsNow,
    );
    expect(screen.getByTestId("review").textContent).toBe(
      DICTIONARIES["zh-Hant"].reviewPriority,
    );
  });

  it("persists the chosen language", () => {
    render(
      <I18nProvider>
        <Probe />
      </I18nProvider>,
    );
    fireEvent.click(screen.getByText("toggle"));
    expect(window.localStorage.getItem("seawatch.lang")).toBe("zh-Hant");
  });

  it("ships exact bilingual resilience labels without replacement characters", () => {
    expect(DICTIONARIES["zh-Hant"].modeCloud).toBe("雲端即時 AIS");
    expect(DICTIONARIES["zh-Hant"].modeEdge).toBe("本地 AIS 接收");
    expect(DICTIONARIES.en.modeReplay).toBe("EDGE REPLAY");
    expect(DICTIONARIES.en.edgeCoverageNote).toBe(
      "Shows only vessels receivable by the local antenna.",
    );
    expect(JSON.stringify(DICTIONARIES)).not.toContain("�");
  });

  it("keeps the default English dictionary free of Chinese interface labels", () => {
    expect(JSON.stringify(DICTIONARIES.en)).not.toMatch(/[\u3400-\u9fff]/u);
  });
});
