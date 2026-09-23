const fs = require("fs");
const http = require("http");
const path = require("path");
const { chromium } = require("playwright");

const repository = path.resolve(process.argv[2] || "");
const expected = process.argv[3] || "working";
const root = path.resolve(repository, "site");

function contentType(file) {
  if (file.endsWith(".css")) return "text/css";
  if (file.endsWith(".js")) return "text/javascript";
  return "text/html";
}

function serve(request, response) {
  const url = new URL(request.url, "http://127.0.0.1");
  const relative = url.pathname === "/" ? "index.html" : url.pathname.replace(/^\/+/, "");
  const target = path.resolve(root, relative);
  if (!target.startsWith(root + path.sep) || !fs.existsSync(target) || !fs.statSync(target).isFile()) {
    response.writeHead(404).end();
    return;
  }
  response.writeHead(200, { "Content-Type": contentType(target) });
  fs.createReadStream(target).pipe(response);
}

async function submit(page, values) {
  await page.locator("#contact-name").fill(values.name);
  await page.locator("#contact-email").fill(values.email);
  await page.locator("#contact-message").fill(values.message);
  await page.locator('#contact-form button[type="submit"]').click();
  await page.waitForTimeout(250);
  return (await page.locator("#form-status").textContent() || "").trim();
}

async function main() {
  const server = http.createServer(serve);
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const url = `http://127.0.0.1:${server.address().port}`;
  let browser;
  try {
    browser = await chromium.launch({
      headless: true,
      executablePath: process.env.BROWSER_EXE || chromium.executablePath(),
    });
    const page = await browser.newPage({ viewport: { width: 1100, height: 900 } });
    const scriptResponses = {};
    page.on("response", (response) => {
      const pathname = new URL(response.url()).pathname;
      if (pathname.endsWith(".js")) scriptResponses[pathname] = response.status();
    });
    await page.goto(url, { waitUntil: "networkidle" });

    const invalidStatus = await submit(page, {
      name: "Avery",
      email: "not-an-email",
      message: "Please share the project guide.",
    });
    const invalidState = await page.locator("#form-status").getAttribute("data-state");
    const validStatus = await submit(page, {
      name: "Avery",
      email: "avery@example.test",
      message: "Please share the project guide.",
    });
    const validState = await page.locator("#form-status").getAttribute("data-state");
    const fieldsReset = await page.locator("#contact-name").inputValue() === "" &&
      await page.locator("#contact-email").inputValue() === "" &&
      await page.locator("#contact-message").inputValue() === "";

    const working =
      scriptResponses["/assets/contact-form.js"] === 200 &&
      invalidStatus === "Please complete every field with a valid email address." &&
      invalidState === "error" &&
      validStatus === "Thanks, Avery. Your message is ready to send." &&
      validState === "success" && fieldsReset;
    const broken =
      scriptResponses["/assets/contact-validation.js"] === 404 &&
      invalidStatus === "" && invalidState === null &&
      validStatus === "" && validState === null;

    console.log("browser_check_id=contact_form_validation");
    console.log(`loaded_script=${JSON.stringify(scriptResponses)}`);
    console.log(`invalid_status=${invalidStatus}`);
    console.log(`valid_status=${validStatus}`);
    console.log(`fields_reset=${fieldsReset}`);
    if ((expected === "working" && !working) || (expected === "broken" && !broken)) process.exitCode = 1;
  } finally {
    if (browser) await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 2;
});

