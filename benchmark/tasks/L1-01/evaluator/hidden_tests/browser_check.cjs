const fs = require("fs");
const http = require("http");
const path = require("path");
const { chromium } = require("playwright");

const repository = path.resolve(process.argv[2] || "");
const siteRoot = path.join(repository, "site");

if (!fs.existsSync(path.join(siteRoot, "index.html"))) {
  console.error(`Not an L1-01 repository: ${repository}`);
  process.exit(2);
}

const mimeTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".svg": "image/svg+xml",
};

function serveFile(request, response) {
  const requestUrl = new URL(request.url, "http://127.0.0.1");
  const relative = requestUrl.pathname === "/"
    ? "index.html"
    : decodeURIComponent(requestUrl.pathname).replace(/^\/+/, "");
  const requestedPath = path.resolve(siteRoot, relative);
  const safePrefix = `${path.resolve(siteRoot)}${path.sep}`;

  if (requestedPath !== path.join(path.resolve(siteRoot), "index.html") && !requestedPath.startsWith(safePrefix)) {
    response.writeHead(403).end("Forbidden");
    return;
  }

  fs.stat(requestedPath, (statError, stats) => {
    if (statError || !stats.isFile()) {
      response.writeHead(404, { "Content-Type": "text/plain" }).end("Not found");
      return;
    }
    const contentType = mimeTypes[path.extname(requestedPath)] || "application/octet-stream";
    response.writeHead(200, { "Content-Type": contentType });
    fs.createReadStream(requestedPath).pipe(response);
  });
}

async function main() {
  const server = http.createServer(serveFile);
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  const baseUrl = `http://127.0.0.1:${address.port}`;
  let browser;

  try {
    browser = await chromium.launch({
      headless: true,
      executablePath: process.env.BROWSER_EXE || chromium.executablePath(),
    });
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    const imageResponses = [];
    page.on("response", (response) => {
      if (response.request().resourceType() === "image") {
        imageResponses.push({ url: response.url(), status: response.status() });
      }
    });

    await page.goto(baseUrl, { waitUntil: "networkidle" });
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

    console.log(`browser_check_id=browser_product_images`);
    console.log(`image_count=${images.length}`);
    console.log(`broken_image_count=${broken.length}`);
    console.log(`failed_image_response_count=${failedResponses.length}`);

    if (images.length !== 3 || broken.length !== 0 || failedResponses.length !== 0) {
      console.error(JSON.stringify({ broken, failedResponses }, null, 2));
      process.exitCode = 1;
    }
  } finally {
    if (browser) {
      await browser.close();
    }
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 2;
});
