# 📧 Smart Follow-up Agent API

A FastAPI-based service that validates lead data, enriches it, and generates personalized follow-up emails using an AI model (e.g., DeepSeek deployed via Azure AI Foundry).

---

## 🚀 Features

- Accepts structured lead JSON
- Validates mandatory fields
- Enriches lead context (persona, pain points, urgency)
- Generates personalized follow-up emails
- Returns structured JSON response
- Fully Dockerized for deployment

---

## 🧱 Project Structure
.
├── api/
│ ├── main.py # FastAPI entrypoint
│ ├── routes/
│ │ └── agent.py # Agent logic (LLM call)
│ ├── schemas.py # Request/Response models
├── requirements.txt
├── Dockerfile
└── README.md


---

## ⚙️ Prerequisites

- Docker (recommended)
- Python 3.12 (for local run)
- Azure AI Foundry model endpoint
- API key for model access

---

## 🔐 Environment Variables

Create a `.env` file in the root directory:
AZURE_API_KEY=your_api_key
AZURE_ENDPOINT=your_endpoint


---

## 🐳 Run with Docker

### 1. Build Docker Image
docker build -t followup-agent .


### 2. Run Container
docker run -p 8000:8000 --env-file .env followup-agent


App will be available at:  
👉 http://localhost:8000

---

## 💻 Run Locally

### 1. Create Virtual Environment
python -m venv venv
source venv/bin/activate # Mac/Linux
venv\Scripts\activate # Windows

### 2. Install Dependencies
pip install -r requirements.txt


### 3. Start Server
uvicorn api.main:app --host 0.0.0.0 --port 8000


---

## 🧪 API Testing

### Health Check
GET /health
curl http://localhost:8000/health
Response:
{ "status": "ok" }


---

### Generate Follow-up Email
curl -X POST http://localhost:8000/agent/follow-up

-H "Content-Type: application/json"
-d '{
"lead_id": "L-1001",
"created_at": "2026-03-06T10:15:00Z",
"source": "website_form",
"contact": {
"first_name": "Ava",
"email": "ava.johnson@kestrelfoods.com
"
},
"company": {
"name": "Kestrel Foods"
},
"intent": {
"use_case": "Automated follow-up"
}
}'

{
"status": "success",
"lead_id": "L-1001",
"email": {
"subject": "...",
"body": "..."
},
"enrichment": {
"persona": "...",
"pain_points": ["..."],
"urgency": "medium",
"industry_context": "..."
},
"confidence_score": 0.85
}


### Server Errors

| Status Code | Description |
|------------|-------------|
| 502 | Invalid model response |
| 503 | Model unavailable |
| 500 | Internal server error |

---

## 🧠 Notes

- Ensure your LLM returns **strict JSON output**
- Add retry logic for malformed responses (recommended for OSS models like DeepSeek)
- Designed for CRM integrations (HubSpot, Salesforce, etc.)

---

## 📌 Future Improvements

- Add authentication (JWT / API keys)
- Add logging & monitoring
- Add retry/guardrail layer for LLM output
- Multi-agent pipeline (validator + writer + critic)
- Deploy to Azure Container Apps / Kubernetes

---

## 👨‍💻 Author

Built for agentic AI workflows using FastAPI + Azure AI Foundry.