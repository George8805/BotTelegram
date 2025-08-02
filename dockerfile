FROM python:3.11.9

# Set work directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy restul codului
COPY . .

# Pornire bot
CMD ["python", "main.py"]
