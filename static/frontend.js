document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('analyzeForm');
    const symbolInput = document.getElementById('symbol');
    const resultCard = document.getElementById('resultCard');
    const resultTicker = document.getElementById('resultTicker');
    const resultStatus = document.getElementById('resultStatus');
    const resultReasoning = document.getElementById('resultReasoning');

    if (!form || !symbolInput || !resultCard || !resultTicker || !resultStatus || !resultReasoning) {
        return;
    }

    let evtSource = null;

    function closeStream() {
        if (evtSource) {
            evtSource.close();
            evtSource = null;
        }
    }

    function connectPriceStream(ticker) {
        closeStream();
        evtSource = new EventSource(`/stream/${encodeURIComponent(ticker)}`);

        evtSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (typeof data.price === 'number') {
                    resultStatus.textContent = `Status: Live - $${data.price.toFixed(2)}`;
                }
            } catch (_err) {
                resultStatus.textContent = 'Status: Live stream received malformed payload';
            }
        };

        evtSource.onerror = () => {
            resultStatus.textContent = 'Status: Stream disconnected';
            closeStream();
        };
    }

    form.addEventListener('submit', async (event) => {
        event.preventDefault();

        const ticker = symbolInput.value.trim().toUpperCase();
        symbolInput.value = ticker;

        if (!/^[A-Z0-9.-]{1,10}$/.test(ticker)) {
            resultCard.classList.remove('hidden');
            resultTicker.textContent = '---';
            resultStatus.textContent = 'Status: Invalid ticker format';
            resultReasoning.textContent = 'Use 1-10 characters: A-Z, 0-9, dot, or hyphen.';
            return;
        }

        resultCard.classList.remove('hidden');
        resultTicker.textContent = ticker;
        resultStatus.textContent = 'Status: Analyzing...';
        resultReasoning.textContent = 'Running Gemini analysis...';

        try {
            const response = await fetch(`/api/analyze/${encodeURIComponent(ticker)}`);
            const data = await response.json();

            if (!response.ok || data.status === 'error') {
                const message = data.message || data.error || 'Analyze request failed';
                resultStatus.textContent = 'Status: Error';
                resultReasoning.textContent = message;
                closeStream();
                return;
            }

            resultStatus.textContent = 'Status: Analysis complete, connecting live feed...';
            resultReasoning.textContent = data.analysis || 'No analysis text returned.';
            connectPriceStream(ticker);
        } catch (_err) {
            resultStatus.textContent = 'Status: Request failed';
            resultReasoning.textContent = 'Could not reach backend. Check Flask server logs.';
            closeStream();
        }
    });

    window.addEventListener('beforeunload', () => {
        closeStream();
    });
});