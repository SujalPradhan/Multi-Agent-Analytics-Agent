#!/bin/bash
# =============================================================================
# Spike AI Multi-Agent Analytics API - Test Suite
# =============================================================================
# This script tests all API endpoints and tiers
# Usage: bash test_curl.sh [property_id]
# =============================================================================

# Configuration
BASE_URL="https://sujalrp-multi-analytics-agent.hf.space"
PROPERTY_ID="${1:-516820017}"  # Use argument or default

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Counters
PASSED=0
FAILED=0

# =============================================================================
# Helper Functions
# =============================================================================

print_header() {
    echo ""
    echo -e "${CYAN}==========================================${NC}"
    echo -e "${CYAN}$1${NC}"
    echo -e "${CYAN}==========================================${NC}"
}

print_test() {
    echo ""
    echo -e "${YELLOW}▶ Test: $1${NC}"
    echo -e "${BLUE}  Description: $2${NC}"
}

print_success() {
    echo -e "${GREEN}✓ PASSED${NC}"
    ((PASSED++))
}

print_failure() {
    echo -e "${RED}✗ FAILED: $1${NC}"
    ((FAILED++))
}

# =============================================================================
# SECTION 1: Basic Endpoints
# =============================================================================

print_header "SECTION 1: Basic Endpoints"

# Test 1.1: Health Check
print_test "1.1 Health Check" "Verify server is running"
RESPONSE=$(curl -s -w "\n%{http_code}" -X GET "$BASE_URL/health")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    print_success
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
else
    print_failure "HTTP $HTTP_CODE"
fi

# Test 1.2: Root Endpoint
print_test "1.2 Root Endpoint" "Get API information"
RESPONSE=$(curl -s -w "\n%{http_code}" -X GET "$BASE_URL/")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    print_success
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
else
    print_failure "HTTP $HTTP_CODE"
fi

# Test 1.3: OpenAPI Docs
print_test "1.3 OpenAPI Docs" "Check docs endpoint exists"
RESPONSE=$(curl -s -w "\n%{http_code}" -X GET "$BASE_URL/docs")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

if [ "$HTTP_CODE" == "200" ]; then
    print_success
    echo "  Docs available at: $BASE_URL/docs"
else
    print_failure "HTTP $HTTP_CODE"
fi

# =============================================================================
# SECTION 2: Tier 1 - Analytics Agent (GA4)
# =============================================================================

print_header "SECTION 2: Tier 1 - Analytics Agent (GA4)"

# Test 2.1: Simple Page Views Query
print_test "2.1 Page Views Query" "Get page views for last 7 days"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"What are my total page views this week?\",
    \"propertyId\": \"$PROPERTY_ID\"
  }")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    print_success
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
else
    print_failure "HTTP $HTTP_CODE"
    echo "$BODY"
fi

# Test 2.2: Top Pages Query
print_test "2.2 Top Pages Query" "Get top 5 pages by views"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"What are my top 5 pages by views this week?\",
    \"propertyId\": \"$PROPERTY_ID\"
  }")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    print_success
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
else
    print_failure "HTTP $HTTP_CODE"
    echo "$BODY"
fi

# Test 2.3: Users and Sessions
print_test "2.3 Users and Sessions" "Get active users and sessions"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"How many users and sessions did I have in the last 14 days?\",
    \"propertyId\": \"$PROPERTY_ID\"
  }")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    print_success
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
else
    print_failure "HTTP $HTTP_CODE"
    echo "$BODY"
fi

# Test 2.4: Device Category Breakdown
print_test "2.4 Device Categories" "Get users by device type"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"Show me users by device category for the last 7 days\",
    \"propertyId\": \"$PROPERTY_ID\"
  }")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    print_success
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
else
    print_failure "HTTP $HTTP_CODE"
    echo "$BODY"
fi

# Test 2.5: Traffic Sources
print_test "2.5 Traffic Sources" "Get top traffic sources"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"What are my top 5 traffic sources driving users in the last 30 days?\",
    \"propertyId\": \"$PROPERTY_ID\"
  }")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    print_success
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
else
    print_failure "HTTP $HTTP_CODE"
    echo "$BODY"
fi

# Test 2.6: Daily Breakdown (from PRD sample)
print_test "2.6 Daily Breakdown" "Daily page views, users, sessions for /pricing"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"Give me a daily breakdown of page views, users, and sessions for the /pricing page over the last 14 days and summarize trends.\",
    \"propertyId\": \"$PROPERTY_ID\"
  }")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    print_success
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
else
    print_failure "HTTP $HTTP_CODE"
    echo "$BODY"
fi

# Test 2.7: Country Breakdown
print_test "2.7 Country Breakdown" "Users by country"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"Show me users by country for the last week\",
    \"propertyId\": \"$PROPERTY_ID\"
  }")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    print_success
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
else
    print_failure "HTTP $HTTP_CODE"
    echo "$BODY"
fi

# =============================================================================
# SECTION 3: Tier 2 - SEO Agent (Google Sheets)
# =============================================================================

print_header "SECTION 3: Tier 2 - SEO Agent (Google Sheets)"

# Test 3.1: Summary of All Pages
print_test "3.1 All Pages Summary" "Get summary of all pages with their status"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "List all pages showing their Address, Status Code, and Content Type"
  }')
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    print_success
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
else
    print_failure "HTTP $HTTP_CODE"
    echo "$BODY"
fi

# Test 3.2: List All URLs
print_test "3.2 All URLs" "List all URLs in the data"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "List all URLs from the Address column"
  }')
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    print_success
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
else
    print_failure "HTTP $HTTP_CODE"
    echo "$BODY"
fi

# Test 3.3: Status Code Breakdown
print_test "3.3 Status Code Breakdown" "What status codes exist and how many pages for each"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the different status codes in my data and how many pages have each status code?"
  }')
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    print_success
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
else
    print_failure "HTTP $HTTP_CODE"
    echo "$BODY"
fi

# Test 3.4: Pages with 200 Status
print_test "3.4 Healthy Pages" "Find pages with 200 OK status"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Show me all pages that have status code 200"
  }')
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    print_success
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
else
    print_failure "HTTP $HTTP_CODE"
    echo "$BODY"
fi

# Test 3.5: Content Type Analysis
print_test "3.5 Content Types" "Group pages by content type"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Group pages by content type and show counts"
  }')
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    print_success
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
else
    print_failure "HTTP $HTTP_CODE"
    echo "$BODY"
fi

# Test 3.6: Broken Links (4xx status)
print_test "3.6 Broken Links" "Find pages with 4xx status codes"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Which URLs have 4xx status codes?"
  }')
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    print_success
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
else
    print_failure "HTTP $HTTP_CODE"
    echo "$BODY"
fi

# Test 3.7: Site Health Summary
print_test "3.7 Site Health" "Overall site health summary"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Give me an overall summary of my site health based on the crawl data. How many total pages, what are the status codes, and are there any issues?"
  }')
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    print_success
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
else
    print_failure "HTTP $HTTP_CODE"
    echo "$BODY"
fi

# =============================================================================
# SECTION 4: Tier 3 - Multi-Agent Queries
# =============================================================================

print_header "SECTION 4: Tier 3 - Multi-Agent Queries"

# Test 4.1: Top Pages with Crawl Status
print_test "4.1 Top Pages with Crawl Data" "Top pages by views with their crawl status"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"What are my top 5 pages by views, and check if they exist in my SEO crawl data with their status codes\",
    \"propertyId\": \"$PROPERTY_ID\"
  }")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    print_success
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
else
    print_failure "HTTP $HTTP_CODE"
    echo "$BODY"
fi

# Test 4.2: Traffic and Crawl Analysis
print_test "4.2 Traffic + Crawl Analysis" "Compare traffic with crawl data"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"Compare my top traffic pages from analytics with my SEO crawl data. Are all my high-traffic URLs returning 200 status?\",
    \"propertyId\": \"$PROPERTY_ID\"
  }")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    print_success
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
else
    print_failure "HTTP $HTTP_CODE"
    echo "$BODY"
fi

# Test 4.3: Combined Site Analysis
print_test "4.3 Combined Site Analysis" "Full site analysis combining traffic and crawl"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"Give me a combined analysis of my website. Show traffic metrics from analytics and technical health from the crawl data.\",
    \"propertyId\": \"$PROPERTY_ID\"
  }")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    print_success
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
else
    print_failure "HTTP $HTTP_CODE"
    echo "$BODY"
fi

# =============================================================================
# SECTION 5: JSON Format Requests
# =============================================================================

print_header "SECTION 5: JSON Format Requests"

# Test 5.1: Analytics with JSON
print_test "5.1 Analytics JSON Output" "Request JSON format explicitly"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"Show me users by device category, return as JSON\",
    \"propertyId\": \"$PROPERTY_ID\"
  }")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    print_success
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
else
    print_failure "HTTP $HTTP_CODE"
    echo "$BODY"
fi

# Test 5.2: SEO with JSON
print_test "5.2 SEO JSON Output" "Request SEO data in JSON format"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Return all pages with their Address, Status Code, and Content Type in JSON format"
  }')
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    print_success
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
else
    print_failure "HTTP $HTTP_CODE"
    echo "$BODY"
fi

# Test 5.3: Multi-Agent JSON Output
print_test "5.3 Multi-Agent JSON Output" "Top pages with crawl data in JSON"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"Give me my top 5 pages by views and their corresponding crawl status in JSON format\",
    \"propertyId\": \"$PROPERTY_ID\"
  }")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    print_success
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
else
    print_failure "HTTP $HTTP_CODE"
    echo "$BODY"
fi

# =============================================================================
# SECTION 6: Error Handling Tests
# =============================================================================

print_header "SECTION 6: Error Handling Tests"

# Test 6.1: Empty Query
print_test "6.1 Empty Query" "Should return 400/422 error"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": ""
  }')
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "400" ] || [ "$HTTP_CODE" == "422" ]; then
    print_success
    echo "  Expected error received (HTTP $HTTP_CODE)"
else
    print_failure "Expected 400/422, got HTTP $HTTP_CODE"
    echo "$BODY"
fi

# Test 6.2: Missing Query Field
print_test "6.2 Missing Query Field" "Should return 422 error"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d '{
    "propertyId": "123456789"
  }')
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "422" ]; then
    print_success
    echo "  Expected error received (HTTP $HTTP_CODE)"
else
    print_failure "Expected 422, got HTTP $HTTP_CODE"
    echo "$BODY"
fi

# Test 6.3: Invalid Property ID Format
print_test "6.3 Invalid Property ID" "Should handle gracefully"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Show me page views",
    "propertyId": "invalid-id"
  }')
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "400" ] || [ "$HTTP_CODE" == "422" ]; then
    print_success
    echo "  Expected error received (HTTP $HTTP_CODE)"
else
    print_failure "Expected 400/422, got HTTP $HTTP_CODE"
    echo "$BODY"
fi

# Test 6.4: Invalid JSON Body
print_test "6.4 Invalid JSON Body" "Should return 422 error"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d 'not valid json')
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "422" ]; then
    print_success
    echo "  Expected error received (HTTP $HTTP_CODE)"
else
    print_failure "Expected 422, got HTTP $HTTP_CODE"
    echo "$BODY"
fi

# Test 6.5: Analytics without Property ID
print_test "6.5 Analytics without Property ID" "Should use default or error gracefully"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are my page views?"
  }')
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ] || [ "$HTTP_CODE" == "400" ]; then
    print_success
    echo "  Response received (HTTP $HTTP_CODE)"
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
else
    print_failure "Unexpected HTTP $HTTP_CODE"
    echo "$BODY"
fi

# =============================================================================
# SECTION 7: Edge Cases
# =============================================================================

print_header "SECTION 7: Edge Cases"

# Test 7.1: Very Long Query
print_test "7.1 Long Query" "Handle long query string"
LONG_QUERY="Tell me about my website analytics including page views, users, sessions, bounce rate, and also give me information about the traffic sources and device categories and countries and cities for the last 30 days and summarize the trends"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"$LONG_QUERY\",
    \"propertyId\": \"$PROPERTY_ID\"
  }")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    print_success
    echo "$BODY" | jq '.answer' 2>/dev/null || echo "$BODY"
else
    print_failure "HTTP $HTTP_CODE"
    echo "$BODY"
fi

# Test 7.2: Query with Special Characters
print_test "7.2 Special Characters" "Handle special characters in query"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What pages have URLs containing /blog/2024?"
  }')
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    print_success
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
else
    print_failure "HTTP $HTTP_CODE"
    echo "$BODY"
fi

# Test 7.3: Whitespace-only Query
print_test "7.3 Whitespace Query" "Should reject whitespace-only query"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "   "
  }')
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "400" ] || [ "$HTTP_CODE" == "422" ]; then
    print_success
    echo "  Expected error received (HTTP $HTTP_CODE)"
else
    print_failure "Expected 400/422, got HTTP $HTTP_CODE"
    echo "$BODY"
fi

# =============================================================================
# Summary
# =============================================================================

print_header "TEST SUMMARY"

TOTAL=$((PASSED + FAILED))
echo ""
echo -e "Total Tests: ${CYAN}$TOTAL${NC}"
echo -e "Passed:      ${GREEN}$PASSED${NC}"
echo -e "Failed:      ${RED}$FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}✗ Some tests failed${NC}"
    exit 1
fi
