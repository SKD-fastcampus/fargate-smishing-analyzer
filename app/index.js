const { chromium } = require('playwright-extra');
const stealth = require('puppeteer-extra-plugin-stealth')();
const { S3Client, PutObjectCommand } = require('@aws-sdk/client-s3');
const fs = require('fs');
const path = require('path');

// Apply stealth plugin
chromium.use(stealth);

const s3Client = new S3Client({ region: process.env.AWS_REGION || 'ap-northeast-2' });

async function uploadToS3(bucket, key, body, contentType) {
    try {
        const command = new PutObjectCommand({
            Bucket: bucket,
            Key: key,
            Body: body,
            ContentType: contentType
        });
        await s3Client.send(command);
        console.log(`Successfully uploaded: ${key}`);
    } catch (err) {
        console.error(`Error uploading ${key}:`, err);
    }
}

(async () => {
    const targetUrl = process.env.TARGET_URL;
    const bucketName = process.env.S3_BUCKET_NAME;

    if (!targetUrl) {
        console.error("Error: TARGET_URL environment variable is not set.");
        process.exit(1);
    }

    if (!bucketName) {
        console.warn("Warning: S3_BUCKET_NAME is not set. Results will not be uploaded.");
    }

    console.log(`Starting analysis for: ${targetUrl}`);

    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const safeUrl = targetUrl.replace(/[^a-zA-Z0-9]/g, '_').substring(0, 50);
    const artifactPrefix = `analysis/${timestamp}_${safeUrl}`;

    // Launch with stealth options (playwright-extra handles this)
    const browser = await chromium.launch({
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
    });

    const context = await browser.newContext({
        recordHar: { path: 'network.har', mode: 'full', content: 'embed' },
        ignoreHTTPSErrors: true,
        userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1'
    });

    const page = await context.newPage();

    // Trace Redirects (including JS redirects)
    const redirectChain = [];
    page.on('response', res => {
        if (res.status() >= 300 && res.status() <= 399) {
            redirectChain.push({
                url: res.url(),
                status: res.status(),
                target: res.headers()['location']
            });
        }
    });

    // Also capture main frame navigations for JS redirects
    const navigationLog = [];
    page.on('framenavigated', frame => {
        if (frame === page.mainFrame()) {
            navigationLog.push(frame.url());
        }
    });

    try {
        const response = await page.goto(targetUrl, { waitUntil: 'networkidle', timeout: 30000 });

        console.log(`Page loaded. Status: ${response ? response.status() : 'Unknown'}`);
        const finalUrl = page.url();
        console.log(`Final URL: ${finalUrl}`);

        // 1. Capture Screenshot
        const screenshotBuffer = await page.screenshot({ fullPage: true });

        // 2. Capture HTML Content
        const htmlContent = await page.content();

        // 3. Form & Input Field Detection
        const inputFields = await page.$$eval('input, textarea, select', elements =>
            elements.map(el => ({
                tagName: el.tagName,
                type: el.type,
                name: el.name,
                id: el.id,
                placeholder: el.placeholder,
                isVisible: el.offsetParent !== null // Check visibility
            }))
        );
        const hasPasswordField = inputFields.some(i => i.type === 'password');
        const hasCreditCardField = inputFields.some(i =>
            (i.name && i.name.match(/card|cc|cvv/i)) ||
            (i.placeholder && i.placeholder.match(/card|credit|cvv/i))
        );

        // 4. Cookies & LocalStorage
        const cookies = await context.cookies();
        const localStorageData = await page.evaluate(() => {
            const data = {};
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                data[key] = localStorage.getItem(key);
            }
            return data;
        });

        // 5. Build Metadata Report
        const report = {
            targetUrl,
            finalUrl,
            timestamp,
            status: response ? response.status() : 'Unknown',
            title: await page.title(),
            redirectChain: redirectChain,
            navigationLog: navigationLog,
            riskAssessment: {
                hasPasswordField,
                hasCreditCardField,
                inputCount: inputFields.length
            },
            inputFields,
            cookies,
            localStorage: localStorageData
        };

        // Close context for HAR
        await context.close();
        const harContent = fs.readFileSync('network.har');

        // Upload to S3
        if (bucketName) {
            console.log(`Uploading results to S3 bucket: ${bucketName}`);

            await uploadToS3(bucketName, `${artifactPrefix}/screenshot.png`, screenshotBuffer, 'image/png');
            await uploadToS3(bucketName, `${artifactPrefix}/source.html`, htmlContent, 'text/html');
            await uploadToS3(bucketName, `${artifactPrefix}/network.har`, harContent, 'application/json');
            await uploadToS3(bucketName, `${artifactPrefix}/report.json`, JSON.stringify(report, null, 2), 'application/json');

            console.log("Upload complete.");
        } else {
            console.log("S3 Bucket not provided. Dumping report locally:");
            console.log(JSON.stringify(report, null, 2));
        }

    } catch (error) {
        console.error("An error occurred during analysis:", error);
    } finally {
        await browser.close();
    }
})();
