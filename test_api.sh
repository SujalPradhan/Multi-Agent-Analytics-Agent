#!/bin/bash
# Test script for Spike AI API
# This script tests the API endpoints

echo "==========================================="
echo "Spike AI API Test Suite"
echo "==========================================="
echo ""

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# API base URL
BASE_URL="http://localhost:8080"

# Test 1: Health Check
echo -e "${YELLOW}Test 1: Health Check${NC}"
curl -s -X GET "$BASE_URL/health" | jq '.' || echo -e "${RED}Failed${NC}"
echo ""

# Test 2: Root Endpoint
echo -e "${YELLOW}Test 2: Root Endpoint${NC}"
curl -s -X GET "$BASE_URL/" | jq '.' || echo -e "${RED}Failed${NC}"
echo ""

# Test 3: Simple Analytics Query (will fail without agents implemented)
echo -e "${YELLOW}Test 3: Analytics Query (Expected to fail - agents not implemented)${NC}"
curl -s -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are my top pages this week?",
    "propertyId": "123456789"
  }' | jq '.' || echo -e "${RED}Failed${NC}"
echo ""

# Test 4: SEO Query
echo -e "${YELLOW}Test 4: SEO Query (Expected to fail - agents not implemented)${NC}"
curl -s -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Show me URLs with missing meta descriptions"
  }' | jq '.' || echo -e "${RED}Failed${NC}"
echo ""

# Test 5: JSON Format Request
echo -e "${YELLOW}Test 5: JSON Format Request${NC}"
curl -s -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Show me top pages in JSON format",
    "propertyId": "123456789"
  }' | jq '.' || echo -e "${RED}Failed${NC}"
echo ""

# Test 6: Invalid Request (empty query)
echo -e "${YELLOW}Test 6: Invalid Request - Empty Query${NC}"
curl -s -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "",
    "propertyId": "123456789"
  }' | jq '.' || echo -e "${RED}Failed${NC}"
echo ""

echo "==========================================="
echo "Tests Complete"
echo "==========================================="
