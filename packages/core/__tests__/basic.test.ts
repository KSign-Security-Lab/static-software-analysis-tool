describe("basic setup", () => {
  it("runs a simple assertion", () => {
    expect(true).toBe(true);
  });

  it("does math correctly", () => {
    expect(1 + 2).toBe(3);
  });

  it("handles async code", async () => {
    const value = await Promise.resolve("ok");
    expect(value).toBe("ok");
  });
});
