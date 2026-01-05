FROM mcr.microsoft.com/playwright:v1.57.0-noble

# Set working directory
WORKDIR /app

# Copy package.json and package-lock.json (if available)
COPY package.json ./

# Install dependencies
# We use npm ci if package-lock.json exists, otherwise npm install
# Base image already includes browsers, so we skip downloading them again
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
RUN npm install

# Copy source code
COPY index.js .

# Default command
CMD ["node", "index.js"]
