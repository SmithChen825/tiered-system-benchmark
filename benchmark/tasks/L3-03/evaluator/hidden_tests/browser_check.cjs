const { chromium } = require("playwright");

const target = process.argv[2] || "http://127.0.0.1:8080";
const expected = process.argv[3] || "working";

async function main() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.BROWSER_EXE || chromium.executablePath(),
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    const requests = [];
    const responses = [];
    page.on("request", (request) => {
      if (request.url().includes("/auth/password-reset")) {
        requests.push({ url: request.url(), method: request.method(), postData: request.postData() });
      }
    });
    page.on("response", (response) => {
      if (response.url().includes("/auth/password-reset")) {
        responses.push({ url: response.url(), status: response.status() });
      }
    });

    await page.goto(target, { waitUntil: "networkidle" });
    await page.getByTestId("reset-email").fill("maya@example.test");
    await page.getByTestId("reset-submit").click();
    await page.waitForTimeout(700);

    const error = await page.getByTestId("reset-error").textContent().catch(() => "");
    const success = await page.getByTestId("reset-success").textContent().catch(() => "");
    const request = requests[0] || {};
    const response = responses[0] || {};
    const body = request.postData ? JSON.parse(request.postData) : {};
    const broken =
      request.url === "http://127.0.0.1:8000/api/v1/auth/password-reset" &&
      request.method === "POST" && body.email === "maya@example.test" &&
      response.status === 404 && error === "Unable to submit password reset." && !success;
    const working =
      request.url === "http://127.0.0.1:8000/api/v2/auth/password-reset" &&
      request.method === "POST" && body.email === "maya@example.test" &&
      response.status === 202 && !error &&
      success === "If an account exists for maya@example.test, reset instructions are on the way.";

    console.log("browser_check_id=password_reset_network");
    console.log(`request_url=${request.url || ""}`);
    console.log(`request_method=${request.method || ""}`);
    console.log(`response_status=${response.status || ""}`);
    console.log(`error_text=${error || ""}`);
    console.log(`success_text=${success || ""}`);
    if ((expected === "broken" && !broken) || (expected === "working" && !working)) process.exitCode = 1;
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 2;
});

