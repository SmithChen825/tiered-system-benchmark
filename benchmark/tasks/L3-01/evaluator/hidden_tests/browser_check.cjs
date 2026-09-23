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
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    const consoleErrors = [];
    page.on("console", (message) => {
      if (message.type() === "error") {
        consoleErrors.push(message.text());
      }
    });
    await page.goto(targetUrl, { waitUntil: "networkidle" });

    const errorVisible = await page.getByTestId("error").isVisible().catch(() => false);
    const accountVisible = await page.getByTestId("account-card").isVisible().catch(() => false);
    const name = accountVisible
      ? await page.getByTestId("account-name").textContent()
      : "";
    const role = accountVisible
      ? await page.getByTestId("account-role").textContent()
      : "";

    console.log("browser_check_id=browser_account_cors");
    console.log(`expected_mode=${expectedMode}`);
    console.log(`error_visible=${errorVisible}`);
    console.log(`account_visible=${accountVisible}`);
    console.log(`account_name=${name}`);
    console.log(`account_role=${role}`);
    console.log(`console_error_count=${consoleErrors.length}`);

    const blockedIsCorrect = expectedMode === "blocked" && errorVisible && !accountVisible;
    const loadedIsCorrect =
      expectedMode === "loaded" &&
      !errorVisible &&
      accountVisible &&
      name === "Ada Lovelace" &&
      role === "Platform Engineer";
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
