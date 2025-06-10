/**
 * API Authentication Helper
 *
 * This script adds authentication headers to API requests
 * It works by intercepting fetch requests and adding the Authorization header
 */

// Store the original fetch function
const originalFetch = window.fetch;

// Override the fetch function
window.fetch = async function(url, options = {}) {
    // Only intercept API requests
    if (url.startsWith('/api/')) {
        // Create headers if they don't exist
        if (!options.headers) {
            options.headers = {};
        }

        // Get the access token from the session cookie or localStorage
        // First try to get it from the data attribute on the body
        const accessToken = document.body.getAttribute('data-access-token');

        // Add the Authorization header if we have a token
        if (accessToken) {
            options.headers['Authorization'] = `Bearer ${accessToken}`;
        }
    }

    // Call the original fetch with our modified options
    return originalFetch.call(this, url, options);
};
