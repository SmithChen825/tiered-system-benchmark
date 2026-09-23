const { chromium } = require("playwright");

const targetUrl = process.argv[2];
if (!targetUrl || !/^https?:\/\//.test(targetUrl)) {
  console.error("Usage: node browser_url_check.cjs <http-url>");
  process.exit(2);
}

async function main() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.BROWSER_EXE || chromium.executablePath(),
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    const imageResponses = [];
    page.on("response", (response) => {
      if (response.request().resourceType() === "image") {
        imageResponses.push({ url: response.url(), status: response.status() });
      }
    });
    await page.goto(targetUrl, { waitUntil: "networkidle" });
    const images = await page.locator(".product-card img").evaluateAll((elements) =>
      elements.map((element) => ({
        src: element.getAttribute("src"),
        complete: element.complete,
        naturalWidth: element.naturalWidth,
        naturalHeight: element.naturalHeight,
      }))
    );
    const broken = images.filter(
      (image) => !image.complete || image.naturalWidth === 0 || image.naturalHeight === 0
    );
    const failedResponses = imageResponses.filter((response) => response.status !== 200);
    console.log("browser_check_id=browser_product_images_nginx");
    console.log(`image_count=${images.length}`);
    console.log(`broken_image_count=${broken.length}`);
    console.log(`failed_image_response_count=${failedResponses.length}`);
    if (images.length !== 3 || broken.length !== 0 || failedResponses.length !== 0) {
      console.error(JSON.stringify({ broken, failedResponses }, null, 2));
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
