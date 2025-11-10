#!/bin/bash
# Quick fix script to update .env for Neo4j

echo "🔧 Fixing .env for Neo4j..."
echo ""

if [ ! -f .env ]; then
    echo "❌ .env file not found!"
    exit 1
fi

# Backup current .env
BACKUP_FILE=".env.backup.$(date +%Y%m%d_%H%M%S)"
cp .env "$BACKUP_FILE"
echo "📋 Backed up .env to $BACKUP_FILE"
echo ""

# Update Neo4j settings
sed -i 's/^DB_USER=.*/DB_USER=neo4j/' .env
sed -i 's/^DB_PASSWORD=.*/DB_PASSWORD=neo4jpassword/' .env
sed -i 's/^DB_PORT=.*/DB_PORT=7687/' .env

# Ensure NEO4J_HTTP_PORT exists
if ! grep -q "^NEO4J_HTTP_PORT=" .env; then
    echo "NEO4J_HTTP_PORT=7474" >> .env
fi

echo "✅ Updated .env with Neo4j credentials:"
echo "   DB_USER=neo4j"
echo "   DB_PASSWORD=neo4jpassword"
echo "   DB_PORT=7687"
echo "   NEO4J_HTTP_PORT=7474"
echo ""
echo "🎉 You can now run: docker compose -f docker/docker-compose.neo4j.yml up"
