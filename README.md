---
title: Multi-Agent Analytics
emoji: 📊
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
license: mit
app_port: 7860
---


# Multi-Agent Analytics System

Multi-agent AI system for querying Google Analytics 4 and SEO data using natural language.

## Quick Start

### Prerequisites

- Python 3.10+
- Git
- Google Cloud service account credentials
- OpenAI API key

### Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd project-name
```

2. **Create virtual environment**
```bash
# Windows
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Linux/Mac
python -m venv .venv
source .venv/bin/activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

### Configuration

1. **Create `.env` file** (copy from template)
```env
# OpenAI API Configuration
OPENAI_API_KEY=sk-your-api-key-here

# Google Cloud Configuration
GOOGLE_CREDENTIALS_PATH=credentials.json

# Google Analytics 4
GA4_PROPERTY_ID=your-property-id

# Google Sheets (SEO Data Source)
SHEET_ID=your-google-sheets-id

# Optional
LOG_LEVEL=INFO
PORT=8080
```

2. **Add Google credentials**

Place your Google Cloud service account `credentials.json` in the project root.

To create service account credentials:
- Go to [Google Cloud Console](https://console.cloud.google.com)
- Create service account
- Grant necessary permissions:
  - Google Analytics Data API
  - Google Sheets API
- Download JSON key as `credentials.json`

3. **Get LiteLLM API Key**

Your API key should be in format: `sk-...`
- Base URL: `http://3.110.18.218`
- Uses OpenAI-compatible SDK



### Run the Server

```bash
python main.py
```

Server starts on: `http://localhost:8080`

## Testing the API

### Health Check
```bash
curl http://localhost:8080/health
```

### Query Example (PowerShell)
```powershell
curl.exe -X POST http://localhost:8080/query `
  -H "Content-Type: application/json" `
  -d '{\"query\": \"What are my top pages this week?\", \"propertyId\": \"123456789\"}'
```

### Query Example (Linux/Mac)
```bash
curl -X POST http://localhost:8080/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What are my top pages this week?", "propertyId": "123456789"}'
```

### API Documentation

Visit `http://localhost:8080/docs` for interactive API documentation.

## Project Structure

```
Hackathon-Spike/
├── main.py                     # API Gateway (FastAPI server)
├── credentials.json            # Google service account (add this)
├── requirements.txt            # Python dependencies
├── .env                        # Environment variables (create this)
├── src/
│   ├── ga4_client.py           # GA4 Data API client
│   ├── analytics_agent.py      # Analytics Agent (Tier 1)
│   ├── llm_client.py           # LiteLLM client with retry logic
│   ├── orchestrator.py         # Multi-agent orchestrator
│   └── response_formatter.py   # Response format handler
├── techinical-documents/
│   ├── prd.md                  # Product requirements
│   ├── original_document.md    # Hackathon problem statement
│   └── COMPLETION_STATUS.md    # Implementation status
```

## Current Status

### ✅ Tier 1 - Analytics Agent (Complete)
- GA4 Client - Service account auth, dynamic propertyId, retry logic
- Analytics Agent - NL parsing, metric/dimension validation, query execution
- API Gateway - POST /query endpoint on port 8080
- LLM Client - LiteLLM proxy with exponential backoff
- Orchestrator - Intent detection, agent routing
- Response Formatter - NL/JSON/Hybrid output modes

### ⏳ Tier 2 - SEO Agent (Pending)
- Sheets Client - Google Sheets API integration
- SEO Agent - Screaming Frog data analysis

### ⚠️ Tier 3 - Multi-Agent (Partial)
- Orchestrator ready, needs SEO Agent for full functionality

See [techinical-documents/COMPLETION_STATUS.md](techinical-documents/COMPLETION_STATUS.md) for details.

## Available Models

- `gemini-2.5-flash` - Fast, cheap (default)
- `gemini-2.5-pro` - Complex reasoning
- `gemini-3-pro-preview` - Latest preview

## Response Formats

The API intelligently determines response format:

1. **Natural Language** (default)
   ```json
   {
     "answer": "Your top 5 pages are...",
     "data": null,
     "agent_used": "analytics"
   }
   ```

2. **JSON** (when requested)
   ```json
   {
     "answer": "Results in JSON format",
     "data": {...},
     "agent_used": "analytics"
   }
   ```

3. **Hybrid** (large datasets)
   ```json
   {
     "answer": "Natural language summary...",
     "data": {...},
     "agent_used": "analytics"
   }
   ```

## Troubleshooting

### Dependencies not installing
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Port 8080 already in use
```bash
# Windows
netstat -ano | findstr :8080

# Linux/Mac
lsof -i :8080
```

### API Key not working
```bash
# Test directly
python test_litellm.py
```

### Import errors
```bash
# Verify components
python test_connections.py
```

## Documentation

- [TESTING.md](TESTING.md) - Comprehensive testing guide
- [CURL_COMMANDS.md](CURL_COMMANDS.md) - Quick reference for cURL
- [CONNECTION_STATUS.md](CONNECTION_STATUS.md) - Component connections
- [COMPLETION_STATUS.md](COMPLETION_STATUS.md) - Implementation status
- [prd.md](prd.md) - Product requirements

## Development

### Running Tests
```bash
pytest
```

### Code Formatting
```bash
black .
flake8 .
```

### Environment Variables

Required:
- `LITELLM_API_KEY` - Your LiteLLM API key

Optional:
- `GA4_PROPERTY_ID` - Default GA4 property
- `SHEET_ID` - Google Sheets ID for SEO data
- `LOG_LEVEL` - Logging level (default: INFO)
- `PORT` - Server port (default: 8080)

## License

[Add your license here]

## Support

For issues or questions, refer to:
- [PRD Documentation](prd.md)
- [API Testing Guide](TESTING.md)
