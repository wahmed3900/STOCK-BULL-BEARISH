// Wait for DOM to load
document.addEventListener('DOMContentLoaded', function() {
    const symbolInput = document.getElementById('symbol');
    const statusDiv = document.getElementById('symbol-status');
    const suggestionsDiv = document.getElementById('symbol-suggestions');

    if (!symbolInput) return;

    // Common tickers for suggestions (could be fetched from API)
    const commonTickers = [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA',
        'JPM', 'VTI', 'SPY', 'QQQ', 'BND', 'VOO', 'BTC-USD',
        'ETH-USD', 'DOGE-USD', 'GME', 'AMC', 'NIO', 'PLTR'
    ];

    // Debounce function to prevent too many API calls
    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    // Handle input changes
    const handleInput = debounce(function(e) {
        const input = this;
        let value = input.value.toUpperCase().replace(/\s/g, '');
        input.value = value;

        // Clear previous status
        statusDiv.textContent = '';
        suggestionsDiv.innerHTML = '';
        suggestionsDiv.classList.remove('active');

        if (value.length === 0) {
            return;
        }

        // Validate format
        const isValid = /^[A-Z]{1,5}$/.test(value);

        if (!isValid) {
            statusDiv.textContent = '❌ Please enter 1-5 letters only';
            statusDiv.className = 'symbol-status error';
            return;
        }

        // Show suggestions for partial matches (2+ chars)
        if (value.length >= 2) {
            const matches = commonTickers.filter(t => t.startsWith(value)).slice(0, 8);

            if (matches.length > 0) {
                // Fetch company names from API
                showSuggestions(matches);
            }
        }

        // If complete ticker, validate it
        if (value.length >= 2 && value.length <= 5) {
            validateTicker(value);
        }

    }, 300);

    symbolInput.addEventListener('input', handleInput);

    // Show suggestions
    function showSuggestions(tickers) {
        suggestionsDiv.innerHTML = '';

        // Check if we have company names cached
        tickers.forEach(ticker => {
            const item = document.createElement('div');
            item.className = 'suggestion-item';

            const symbolSpan = document.createElement('span');
            symbolSpan.className = 'symbol';
            symbolSpan.textContent = ticker;

            const nameSpan = document.createElement('span');
            nameSpan.className = 'name';
            nameSpan.textContent = 'Click to select';

            item.appendChild(symbolSpan);
            item.appendChild(nameSpan);

            item.addEventListener('click', function() {
                symbolInput.value = ticker;
                suggestionsDiv.innerHTML = '';
                suggestionsDiv.classList.remove('active');
                validateTicker(ticker);
            });

            suggestionsDiv.appendChild(item);
        });

        suggestionsDiv.classList.add('active');
    }

    // Validate ticker with server
    async function validateTicker(symbol) {
        try {
            const response = await fetch(`/api/validate-ticker?symbol=${symbol}`);
            const data = await response.json();

            if (data.valid) {
                statusDiv.innerHTML = `✅ ${data.name || 'Valid ticker'}`;
                statusDiv.className = 'symbol-status success';
                symbolInput.style.borderColor = '#4CAF50';
            } else {
                statusDiv.textContent = '❌ Unknown ticker';
                statusDiv.className = 'symbol-status error';
                symbolInput.style.borderColor = '#f44336';
            }
        } catch (error) {
            // Silent fail - don't block user
            console.log('Validation service unavailable');
            statusDiv.textContent = '⚠️ Validation unavailable';
            statusDiv.className = 'symbol-status info';
        }
    }

    // Close suggestions when clicking outside
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.symbol-input-group')) {
            suggestionsDiv.innerHTML = '';
            suggestionsDiv.classList.remove('active');
        }
    });

    // Handle Enter key for quick submission
    symbolInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            const value = this.value.trim();
            if (value && /^[A-Z]{1,5}$/.test(value)) {
                // Auto-submit form or trigger search
                const form = this.closest('form');
                if (form) {
                    form.submit();
                }
            } else {
                statusDiv.textContent = '❌ Please enter a valid ticker';
                statusDiv.className = 'symbol-status error';
            }
        }
    });
});