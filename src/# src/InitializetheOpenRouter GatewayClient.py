from openai import OpenAI

# Determine which configuration profile to load
env = os.environ.get('FLASK_ENV', 'development').lower()
if env == 'production':
    app_config = ProductionConfig
elif env == 'testing':
    app_config = TestingConfig
else:
    app_config = DevelopmentConfig

# Initialize the Unified OpenRouter / OpenAI client gateway
openrouter_client = None
if app_config.OPENROUTER_API_KEY:
    try:
        openrouter_client = OpenAI(
            base_url=app_config.OPENROUTER_BASE_URL,
            api_key=app_config.OPENROUTER_API_KEY
        )
        logger.info("openrouter_client_initialized", base_url=app_config.OPENROUTER_BASE_URL)
    except Exception as e:
        logger.error("openrouter_initialization_failed", error=str(e))
else:
    logger.warning("openrouter_api_key_missing", message="AI features will be disabled.")
