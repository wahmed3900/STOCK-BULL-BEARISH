document.addEventListener('DOMContentLoaded', () => {
    const elements = {
        form: document.getElementById('analyzeForm'),
        symbolInput: document.getElementById('symbol'),
        resultCard: document.getElementById('resultCard'),
        resultTicker: document.getElementById('resultTicker'),
        resultStatus: document.getElementById('resultStatus'),
        resultReasoning: document.getElementById('resultReasoning'),
        submitBtn: document.querySelector('#analyzeForm button[type="submit"]')
    };

    // Validate all required elements
    if (Object.values(elements).some(el => !el)) return;

    let evtSource = null;
    let abortController = null;
    let reconnectAttempts = 0;
    const MAX_RECONNECT_ATTEMPTS = 5;

    function closeStream() {
        if (evtSource) {
            evtSource.close();
            evtSource = null;
            reconnectAttempts = 0;
        }
    }

    function connectPriceStream(ticker) {
        closeStream();
        evtSource = new EventSource(`/stream/${encodeURIComponent(ticker)}`);
        let previousPrice = null;

        evtSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (typeof data.price === 'number') {
                    const change = previousPrice ? ((data.price - previousPrice) / previousPrice * 100).toFixed(2) : null;
                    previousPrice = data.price;
                    const changeText = change ? ` (${change > 0 ? '+' : ''}${change}%)` : '';
                    elements.resultStatus.textContent = `Status: Live - $${data.price.toFixed(2)}${changeText}`;
                }
            } catch (_err) {
                elements.resultStatus.textContent = 'Status: Live stream received malformed payload';
            }
        };

        evtSource.onerror = () => {
            if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
                reconnectAttempts++;
                const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
                elements.resultStatus.textContent = `Status: Reconnecting in ${delay/1000}s...`;
                setTimeout(() => connectPriceStream(ticker), delay);
            } else {
                elements.resultStatus.textContent = 'Status: Stream permanently disconnected';
                closeStream();
            }
        };
    }

    function setLoadingState(loading) {
        elements.submitBtn.disabled = loading;
        elements.submitBtn.textContent = loading ? 'Analyzing...' : 'Analyze';
    }

    elements.form.addEventListener('submit', async (event) => {
        event.preventDefault();

        const ticker = elements.symbolInput.value.trim().toUpperCase();
        elements.symbolInput.value = ticker;

        if (!/^[A-Z0-9.-]{1,10}$/.test(ticker)) {
            elements.resultCard.classList.remove('hidden');
            elements.resultTicker.textContent = '---';
            elements.resultStatus.textContent = 'Status: Invalid ticker format';
            elements.resultReasoning.textContent = 'Use 1-10 characters: A-Z, 0-9, dot, or hyphen.';
            return;
        }

        // Cancel any pending request
        if (abortController) abortController.abort();
        
        closeStream();
        setLoadingState(true);

        elements.resultCard.classList.remove('hidden');
        elements.resultTicker.textContent = ticker;
        elements.resultStatus.textContent = 'Status: Analyzing...';
        elements.resultReasoning.textContent = 'Running Gemini analysis...';

        try {
            abortController = new AbortController();
            const response = await fetch(`/api/analyze/${encodeURIComponent(ticker)}`, {
                signal: abortController.signal
            });
            
            const data = await response.json();

            if (!response.ok || data.status === 'error') {
                const message = data.message || data.error || 'Analyze request failed';
                elements.resultStatus.textContent = `Status: Error (${response.status})`;
                elements.resultReasoning.textContent = message;
                return;
            }

            elements.resultStatus.textContent = 'Status: Analysis complete, connecting live feed...';
            elements.resultReasoning.textContent = data.analysis || 'No analysis text returned.';
            connectPriceStream(ticker);
        } catch (err) {
            if (err.name === 'AbortError') {
                // Request was cancelled, ignore
                return;
            }
            elements.resultStatus.textContent = 'Status: Request failed';
            elements.resultReasoning.textContent = 'Could not reach backend. Check Flask server logs.';
        } finally {
            setLoadingState(false);
            abortController = null;
        }
    });

    const beforeUnloadHandler = () => closeStream();
    window.addEventListener('beforeunload', beforeUnloadHandler);
});
