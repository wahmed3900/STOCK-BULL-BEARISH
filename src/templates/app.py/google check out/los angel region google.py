gcloud run deploy stock-validator \
  --image gcr.io/stock-bull-bearish-onrender/stock-validator \
  --platform managed \
  --region us-west2 \
  --allow-unauthenticated \
  --set-env-vars "SECRET_KEY=your-secret,FLASK_ENV=production,MONGO_URI=...,LEMON_SQUEEZY_API_KEY=...,LEMON_SQUEEZY_STORE_ID=1,LEMON_SQUEEZY_VARIANT_ID=...,LEMON_SQUEEZY_WEBHOOK_SECRET=...,OPENROUTER_API_KEY=...,TOGETHER_API_KEY=..."