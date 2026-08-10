x@app.route('/chart', methods=['GET', 'HEAD'])
@limiter.limit("30 per minute")
@log_request
def chart():
    symbol = request.args.get('symbol', '').strip().upper()
    period = request.args.get('period', '1mo')
    interval = request.args.get('interval', '1d')

    if not symbol or not validate_symbol_format(symbol):
        return jsonify({'error': 'Invalid symbol'}), 400
    try:
        MarketPeriod(period)
    except ValueError:
        return jsonify({'error': f'Invalid period. Options: {[p.value for p in MarketPeriod]}'}), 400
    if not validate_interval(interval):
        return jsonify({'error': 'Invalid interval'}), 400

    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, interval=interval)
        if hist.empty:
            return jsonify({'error': 'No data found'}), 404

        data = {
            'symbol': symbol,
            'period': period,
            'interval': interval,
            'data': convert_timestamps(hist.reset_index().to_dict('records')),
        }
        return jsonify(data), 200
    except Exception as e:
        logger.error("chart_error", symbol=symbol, error=str(e))
        return jsonify({'error': 'Failed to fetch chart data'}), 500
