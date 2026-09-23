const { chromium } = require("playwright");

const target = process.argv[2];
const expected = process.argv[3] || "working";
if (!target || !/^https?:\/\//.test(target)) {
  console.error("Usage: node browser_url_check.cjs <http-url> <broken|working>");
  process.exit(2);
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
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.BROWSER_EXE || chromium.executablePath(),
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1100, height: 900 } });
    const scriptResponses = {};
    page.on("response", (response) => {
      const pathname = new URL(response.url()).pathname;
      if (pathname.endsWith(".js")) scriptResponses[pathname] = response.status();
    });
    await page.goto(target, { waitUntil: "networkidle" });
    const invalidStatus = await submit(page, {
      name: "Avery", email: "not-an-email", message: "Please share the project guide.",
    });
    const invalidState = await page.locator("#form-status").getAttribute("data-state");
    const validStatus = await submit(page, {
      name: "Avery", email: "avery@example.test", message: "Please share the project guide.",
    });
    const validState = await page.locator("#form-status").getAttribute("data-state");
    const fieldsReset = await page.locator("#contact-name").inputValue() === "" &&
      await page.locator("#contact-email").inputValue() === "" &&
      await page.locator("#contact-message").inputValue() === "";
    const working = scriptResponses["/assets/contact-form.js"] === 200 &&
      invalidStatus === "Please complete every field with a valid email address." &&
      invalidState === "error" &&
      validStatus === "Thanks, Avery. Your message is ready to send." &&
      validState === "success" && fieldsReset;
    const broken = scriptResponses["/assets/contact-validation.js"] === 404 &&
      invalidStatus === "" && invalidState === null && validStatus === "" && validState === null;
    console.log("browser_check_id=contact_form_validation_nginx");
    console.log(`loaded_script=${JSON.stringify(scriptResponses)}`);
    console.log(`invalid_status=${invalidStatus}`);
    console.log(`valid_status=${validStatus}`);
    console.log(`fields_reset=${fieldsReset}`);
    if ((expected === "working" && !working) || (expected === "broken" && !broken)) process.exitCode = 1;
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 2;
});

