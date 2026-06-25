# Run n8n with Docker
docker run -d -p 5678:5678 -v n8n_data:/home/node/.n8n n8nio/n8
docker run -d --name waha -p 3000:3000 -e WAHA_ENV=production -v waha-data:/app/data devlikeapro/waha