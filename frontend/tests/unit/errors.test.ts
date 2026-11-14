import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api-client";
import { errorMessage } from "@/lib/errors";

describe("errorMessage", () => {
  it("shows the backend's message and keeps the code and request id", () => {
    const err = new ApiError(409, { detail: "This UTR was already submitted.", code: "duplicate_utr", request_id: "req-1" });
    expect(errorMessage(err)).toBe("This UTR was already submitted.");
    expect(err.code).toBe("duplicate_utr");
    expect(err.requestId).toBe("req-1");
  });
  it("falls back when the response had no body", () => {
    expect(errorMessage(new ApiError(502, null))).toBe("Request failed");
    expect(errorMessage("weird")).toBe("Something went wrong");
    expect(errorMessage(new Error("Network down"))).toBe("Network down");
  });
});
