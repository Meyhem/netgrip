import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup, configure } from "@testing-library/react";

// findBy*/waitFor wait up to 3 s, not 1 s: under a loaded full-suite run a screen's first
// fetches can take longer than a second (intermittent Settings failures).
configure({ asyncUtilTimeout: 3000 });

afterEach(() => cleanup());
