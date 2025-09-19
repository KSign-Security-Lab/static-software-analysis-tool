#!/bin/bash

echo "🚀 Setting up Prisma for Static Software Analysis Tool"
echo "====================================================="
echo ""

# Check if .env exists
if [ ! -f "../.env" ]; then
    echo "❌ .env file not found in project root"
    echo "Please create a .env file with your DATABASE_URL"
    echo "Example:"
    echo "DATABASE_URL=\"postgresql://username:password@localhost:5432/database_name?schema=public\""
    exit 1
fi

echo "✅ Found .env file"

# Check if PostgreSQL is running
echo "🔍 Checking if PostgreSQL is running..."
if ! pg_isready -h localhost -p 5432 > /dev/null 2>&1; then
    echo "⚠️  PostgreSQL doesn't seem to be running on localhost:5432"
    echo "Please start PostgreSQL first:"
    echo "  - sudo systemctl start postgresql"
    echo "  - or: brew services start postgresql"
    echo "  - or: pg_ctl start"
    echo ""
    echo "Then run this script again"
    exit 1
fi

echo "✅ PostgreSQL is running"

# Install dependencies
echo "📦 Installing dependencies..."
if command -v yarn > /dev/null 2>&1; then
    yarn install
else
    npm install
fi

# Generate Prisma client
echo "🔧 Generating Prisma client..."
if command -v yarn > /dev/null 2>&1; then
    yarn db:generate
else
    npx prisma generate
fi

# Push schema to database
echo "📊 Pushing schema to database..."
if command -v yarn > /dev/null 2>&1; then
    yarn db:push
else
    npx prisma db push
fi

echo ""
echo "🎉 Setup complete!"
echo ""
echo "Next steps:"
echo "1. Open Prisma Studio: yarn db:studio"
echo "2. Try the example: yarn db:example"
echo "3. Check the documentation in src/README.md"
echo ""
echo "Your database is ready to store graph data!"
