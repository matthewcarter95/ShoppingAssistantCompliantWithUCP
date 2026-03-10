#!/bin/bash
set -e

echo "🚀 Setting up E2E tests..."

# Install npm dependencies
echo "📦 Installing dependencies..."
npm install

# Install Playwright browsers
echo "🌐 Installing Playwright browsers..."
npx playwright install chromium

# Check for .env file
if [ ! -f .env ]; then
    echo ""
    echo "⚠️  No .env file found!"
    echo "📝 Please create .env file from .env.example:"
    echo "   cp .env.example .env"
    echo "   # Then edit .env and add your TEST_USER_PASSWORD"
    echo ""
else
    echo "✅ .env file found"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "To run tests:"
echo "  npm test              # Headless mode"
echo "  npm run test:headed   # See the browser"
echo "  npm run test:debug    # Step-by-step debugging"
echo ""
