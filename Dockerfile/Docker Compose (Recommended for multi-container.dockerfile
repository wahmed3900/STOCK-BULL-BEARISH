version: '3.8'
services:
  app:
    image: your-image-name
    env_file:
      - .env
    ports:
      - "3000:3000"while read -r line || [ -n "$line" ]; do [[ "$line" =~ ^[A-Za-z0-9_]+=[^\ ]+ ]] && eval "export $line"; done < .env
