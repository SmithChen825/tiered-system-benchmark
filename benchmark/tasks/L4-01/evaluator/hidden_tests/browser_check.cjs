const { chromium } = require("playwright");

const targetUrl = process.argv[2] || "http://127.0.0.1:8080";
const expectedMode = process.argv[3];
if (!new Set(["blocked", "loaded"]).has(expectedMode)) {
  console.error("Usage: node browser_check.cjs <frontend-url> <blocked|loaded>");
  process.exit(2);
}

async function main() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.BROWSER_EXE || chromium.executablePath(),
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1360, height: 900 } });
    const consoleErrors = [];
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    await page.goto(targetUrl, { waitUntil: "networkidle" });

    const errorVisible = await page.getByTestId("error").isVisible().catch(() => false);
    const tableVisible = await page.getByTestId("user-table").isVisible().catch(() => false);
    const rowCount = tableVisible ? await page.getByTestId("user-row").count() : 0;
    const headers = tableVisible
      ? await page.locator("thead th").allTextContents()
      : [];

    console.log("browser_check_id=browser_schema_cascade");
    console.log(`expected_mode=${expectedMode}`);
    console.log(`error_visible=${errorVisible}`);
    console.log(`table_visible=${tableVisible}`);
    console.log(`row_count=${rowCount}`);
    console.log(`headers=${headers.join(",")}`);
    console.log(`console_error_count=${consoleErrors.length}`);

    const blockedIsCorrect = expectedMode === "blocked" && errorVisible && !tableVisible;
    const loadedIsCorrect =
      expectedMode === "loaded" &&
      !errorVisible &&
      tableVisible &&
      rowCount === 3 &&
      headers.join(",") === "Name,Email,Role";
    if (!blockedIsCorrect && !loadedIsCorrect) {
      console.error(JSON.stringify({ consoleErrors }, null, 2));
      process.exitCode = 1;
    }
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 2;
});
