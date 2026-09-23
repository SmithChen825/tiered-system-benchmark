const { chromium } = require("playwright");

const target = process.argv[2] || "http://127.0.0.1:8080";
const expected = process.argv[3] || "loaded";

async function main() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.BROWSER_EXE || chromium.executablePath(),
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    const apiRequests = [];
    const apiResponses = [];
    page.on("request", (request) => {
      if (request.url().endsWith("/api/dashboard")) apiRequests.push(request.url());
    });
    page.on("response", (response) => {
      if (response.url().endsWith("/api/dashboard")) {
        apiResponses.push({ url: response.url(), status: response.status() });
      }
    });
    await page.goto(target, { waitUntil: "networkidle" });
    await page.waitForTimeout(700);

    const error = await page.getByTestId("dashboard-error").textContent().catch(() => "");
    const system = await page.getByTestId("system-status").textContent().catch(() => "");
    const database = await page.getByTestId("database-status").textContent().catch(() => "");
    const cards = await page.getByTestId("metric-card").allTextContents().catch(() => []);
    const requestedDirectly = apiRequests[0] === "http://127.0.0.1:8000/api/dashboard";
    const broken = requestedDirectly && error === "Dashboard unavailable." && !system && cards.length === 0;
    const loaded = requestedDirectly && apiResponses[0]?.status === 200 && !error &&
      system === "operational" && database === "reachable" &&
      JSON.stringify(cards) === JSON.stringify(["Jobs processed128", "Active workers4", "Pending alerts0"]);

    console.log("browser_check_id=operations_dashboard");
    console.log(`request_url=${apiRequests[0] || ""}`);
    console.log(`response_status=${apiResponses[0]?.status || "none"}`);
    console.log(`error_text=${error || ""}`);
    console.log(`system_status=${system || ""}`);
    console.log(`database_status=${database || ""}`);
    console.log(`metric_cards=${JSON.stringify(cards)}`);
    if ((expected === "broken" && !broken) || (expected === "loaded" && !loaded)) process.exitCode = 1;
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 2;
});

