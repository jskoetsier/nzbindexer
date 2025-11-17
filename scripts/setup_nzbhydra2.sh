#!/bin/bash

# NZBHydra2 Setup and API Key Retrieval Script

echo "=================================="
echo "NZBHydra2 Setup Assistant"
echo "=================================="
echo ""

SERVER_IP="192.168.1.153"
HYDRA_PORT="5076"
HYDRA_URL="http://${SERVER_IP}:${HYDRA_PORT}"

echo "✓ NZBHydra2 is running at: ${HYDRA_URL}"
echo ""
echo "STEP 1: Complete Initial Setup"
echo "-------------------------------"
echo "1. Open your web browser and go to:"
echo ""
echo "   ${HYDRA_URL}"
echo ""
echo "2. Complete the setup wizard:"
echo "   - Create admin username: admin"
echo "   - Create admin password: (choose a secure password)"
echo "   - Click through the setup wizard"
echo ""
echo "3. Once you reach the main dashboard, continue to STEP 2"
echo ""
read -p "Press ENTER when you've completed the setup wizard..."

echo ""
echo "STEP 2: Retrieve API Key"
echo "------------------------"
echo "1. In NZBHydra2 web interface, click the ⚙️ gear icon (top right)"
echo "2. Go to: Config → Main"
echo "3. Find the 'API key' field"
echo "4. Copy the API key"
echo ""
read -p "Press ENTER when you have your API key ready..."

echo ""
echo "STEP 3: Enter API Key"
echo "---------------------"
read -p "Paste your NZBHydra2 API key here: " API_KEY

if [ -z "$API_KEY" ]; then
    echo "❌ No API key provided. Exiting."
    exit 1
fi

echo ""
echo "STEP 4: Test API Connection"
echo "----------------------------"
TEST_URL="${HYDRA_URL}/api?apikey=${API_KEY}&t=caps&o=json"

echo "Testing API endpoint..."
RESPONSE=$(curl -s -w "\n%{http_code}" "${TEST_URL}")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

if [ "$HTTP_CODE" = "200" ]; then
    echo "✓ API key is valid!"
    echo ""
    echo "=================================="
    echo "SUCCESS! Your NZBHydra2 Setup:"
    echo "=================================="
    echo ""
    echo "URL: ${HYDRA_URL}"
    echo "API Key: ${API_KEY}"
    echo ""
    echo "Add these to your indexer configuration:"
    echo ""
    echo "  NZBHYDRA_URL=${HYDRA_URL}"
    echo "  NZBHYDRA_API_KEY=${API_KEY}"
    echo ""

    # Save to .env if it exists
    if [ -f ".env" ]; then
        echo "NZBHYDRA_URL=${HYDRA_URL}" >> .env
        echo "NZBHYDRA_API_KEY=${API_KEY}" >> .env
        echo "✓ Saved to .env file"
    fi

    echo ""
    echo "Next steps:"
    echo "1. Add indexers to NZBHydra2 (DrunkenSlug, NZBGeek, etc.)"
    echo "2. Integrate NZBHydra2 into your deobfuscation pipeline"
    echo "3. Start seeing improved hash lookups!"
    echo ""
else
    echo "❌ API key test failed. HTTP code: ${HTTP_CODE}"
    echo "Please verify the API key and try again."
    exit 1
fi
