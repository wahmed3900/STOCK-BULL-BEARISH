import logging
logging.basicConfig(level=logging.INFO)

@app.before_request
def log_request_info():
    logging.info(f'Request: {request.method} {request.path}')
    logging.info(f'Headers: {dict(request.headers)}')