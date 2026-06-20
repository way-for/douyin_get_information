FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install backend
COPY backend/ ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy frontend and build
COPY frontend/ ./frontend/
WORKDIR /app/frontend
RUN npm install && npm run build

# Go back to backend for serving
WORKDIR /app

# Expose port
EXPOSE 8000

# Run backend (which also serves frontend static files)
CMD ["sh", "-c", "cd backend && uvicorn app:app --host 0.0.0.0 --port 8000"]
